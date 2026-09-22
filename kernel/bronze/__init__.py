"""Public Bronze contracts and local, source-preserving file ingestion."""

from collections.abc import Mapping
import csv
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType, TracebackType
from typing import Literal, Self
from uuid import uuid4


# The declared header of `danske-csv-v1`, in order. A payload is split against
# exactly this, and no other field name is ever interpreted.
_DANSKE_HEADER = (
    "Dato",
    "Kategori",
    "Underkategori",
    "Tekst",
    "Beløb",
    "Saldo",
    "Status",
    "Afstemt",
)


def _split_danske_csv(content: bytes) -> tuple[list[dict[str, str]], str | None]:
    """Split one payload into source records, or name why it does not match.

    The verdict is deterministic and describes the payload as a whole; it never
    repeats source content, so a failure reason stays safe to show or log.
    """
    try:
        text = content.decode("cp1252", errors="strict")
    except UnicodeDecodeError:
        return [], "payload is not strict Windows-1252"
    if not text:
        return [], "payload is empty"
    try:
        rows = list(
            csv.reader(
                StringIO(text, newline=""),
                delimiter=",",
                quotechar='"',
                strict=True,
            )
        )
    except csv.Error:
        return [], "payload is not well-formed CSV"
    if not rows:
        return [], "payload is empty"
    header, *data = rows
    if tuple(header) != _DANSKE_HEADER:
        return [], "payload header does not match danske-csv-v1"
    records = []
    for ordinal, values in enumerate(data, start=1):
        if len(values) != len(_DANSKE_HEADER):
            return [], (
                f"record {ordinal} has {len(values)} fields, "
                f"expected {len(_DANSKE_HEADER)}"
            )
        records.append(dict(zip(_DANSKE_HEADER, values, strict=True)))
    return records, None


def _danske_last_transaction_date(
    records: list[dict[str, str]],
) -> tuple[date | None, str | None]:
    """Read Dato for one purpose only: bounding a covers_through declaration.

    Every record counts, whatever its row order or Status, and the value is
    never stored anywhere: the source record keeps its original string. A
    payload whose Dato cannot be read yields a verdict instead, so a missing
    bound can never pass for a satisfied one.
    """
    last: date | None = None
    for ordinal, fields in enumerate(records, start=1):
        try:
            value = datetime.strptime(fields["Dato"], "%d-%m-%Y").date()
        except (KeyError, ValueError):
            return None, f"record {ordinal} has an unreadable transaction date"
        if last is None or value > last:
            last = value
    return last, None


def _parse_danske_payload(
    content: bytes,
) -> tuple[list[dict[str, str]], date | None, str | None]:
    """Return the payload's source records, its last transaction date, or why."""
    records, failure_reason = _split_danske_csv(content)
    if failure_reason is not None:
        return [], None, failure_reason
    last_transaction_date, failure_reason = _danske_last_transaction_date(records)
    if failure_reason is not None:
        return [], None, failure_reason
    return records, last_transaction_date, None


@dataclass(frozen=True)
class RawPayload:
    payload_id: str
    byte_length: int
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class ImportRun:
    import_run_id: str
    payload_id: str
    declared_account_id: str
    source_format: str
    original_filename: str = field(repr=False)
    exported_on: date
    exported_on_source: Literal["filename", "declared"]
    covers_through: date
    covers_through_source: Literal["declared", "exported_on"]
    started_at: datetime
    outcome: Literal["stored", "repeat", "refused"]
    repeat_of: str | None


@dataclass(frozen=True)
class SourceRecord:
    payload_id: str
    record_ordinal: int
    fields: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class FormatFailure:
    payload_id: str
    source_format: str
    reason: str


class BronzeStore:
    """Import and retrieve Bronze provenance in a local SQLite store."""

    def __init__(self, database: str | Path) -> None:
        self._connection = sqlite3.connect(database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_payloads (
                payload_id TEXT PRIMARY KEY,
                byte_length INTEGER NOT NULL,
                content BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS import_runs (
                import_run_id TEXT PRIMARY KEY,
                payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
                declared_account_id TEXT NOT NULL,
                source_format TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                exported_on TEXT NOT NULL,
                exported_on_source TEXT NOT NULL,
                covers_through TEXT NOT NULL,
                covers_through_source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                outcome TEXT NOT NULL,
                repeat_of TEXT REFERENCES import_runs(import_run_id)
            );
            CREATE TABLE IF NOT EXISTS source_records (
                payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
                record_ordinal INTEGER NOT NULL,
                fields TEXT NOT NULL,
                PRIMARY KEY (payload_id, record_ordinal)
            );
            CREATE TABLE IF NOT EXISTS format_failures (
                payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
                source_format TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY (payload_id, source_format)
            );
            """
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release resources when the store is closed."""
        self._connection.close()

    def import_file(
        self,
        path: str | Path,
        *,
        declared_account_id: str,
        source_format: str,
        exported_on: date | None = None,
        covers_through: date | None = None,
    ) -> ImportRun:
        """Retain a file's bytes, provenance, and decoded source records."""
        started_at = datetime.now(UTC)
        if source_format != "danske-csv-v1":
            raise ValueError(f"Unsupported source format: {source_format}")

        source = Path(path)
        content = source.read_bytes()
        payload_id = sha256(content).hexdigest()

        exported_on_source = "declared"
        if exported_on is None:
            suffix = re.search(r"-([0-9]{8})\.csv$", source.name, re.IGNORECASE)
            if suffix is None:
                raise ValueError("Declare exported_on when the filename has no date suffix")
            exported_on = datetime.strptime(suffix.group(1), "%Y%m%d").date()
            exported_on_source = "filename"

        if covers_through is None:
            raise NotImplementedError("Coverage-date inference is not implemented")

        records, last_transaction_date, failure_reason = _parse_danske_payload(content)
        # A declared covers_through is bounded by the payload's own evidence: it
        # can neither truncate a transaction the export shows nor reach past the
        # day the bank produced it. Outside that range the run is refused and the
        # declaration is recorded as made, never clamped to the nearest date.
        declaration_refused = covers_through > exported_on or (
            last_transaction_date is not None
            and covers_through < last_transaction_date
        )
        import_run_id = uuid4().hex

        # Commit the payload, provenance, and derived records together.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            original_run = self._connection.execute(
                """
                SELECT import_run_id FROM import_runs
                WHERE payload_id = ? AND declared_account_id = ? AND outcome = 'stored'
                ORDER BY started_at, import_run_id
                LIMIT 1
                """,
                (payload_id, declared_account_id),
            ).fetchone()
            repeat_of = original_run["import_run_id"] if original_run is not None else None

            # Bytes already stored for another account are refused: the
            # payload has one owner, and only a manual decision may move it.
            account_conflict = None
            if repeat_of is None:
                account_conflict = self._connection.execute(
                    """
                    SELECT import_run_id FROM import_runs
                    WHERE payload_id = ? AND outcome = 'stored' AND declared_account_id <> ?
                    ORDER BY started_at, import_run_id
                    LIMIT 1
                    """,
                    (payload_id, declared_account_id),
                ).fetchone()
            refused = declaration_refused or account_conflict is not None
            if refused:
                # A refused run is nobody's original: it is never the run a
                # later presentation of these bytes repeats.
                repeat_of = None

            self._connection.execute(
                """
                INSERT INTO raw_payloads (payload_id, byte_length, content)
                VALUES (?, ?, ?)
                ON CONFLICT (payload_id) DO NOTHING
                """,
                (payload_id, len(content), content),
            )
            self._connection.execute(
                """
                INSERT INTO import_runs (
                    import_run_id, payload_id, declared_account_id, source_format,
                    original_filename, exported_on, exported_on_source,
                    covers_through, covers_through_source, started_at, outcome, repeat_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_run_id,
                    payload_id,
                    declared_account_id,
                    source_format,
                    source.name,
                    exported_on.isoformat(),
                    exported_on_source,
                    covers_through.isoformat(),
                    "declared",
                    started_at.isoformat(),
                    "refused" if refused else ("repeat" if repeat_of is not None else "stored"),
                    repeat_of,
                ),
            )
            # Source records and format failures are deterministic functions of
            # the payload and its format, so they are stored once per payload and
            # re-derived by any later run, whatever its outcome.
            if failure_reason is None:
                self._connection.executemany(
                    """
                    INSERT INTO source_records (payload_id, record_ordinal, fields)
                    VALUES (?, ?, ?)
                    ON CONFLICT (payload_id, record_ordinal) DO NOTHING
                    """,
                    (
                        (payload_id, ordinal, json.dumps(fields))
                        for ordinal, fields in enumerate(records, start=1)
                    ),
                )
            else:
                self._connection.execute(
                    """
                    INSERT INTO format_failures (payload_id, source_format, reason)
                    VALUES (?, ?, ?)
                    ON CONFLICT (payload_id, source_format) DO NOTHING
                    """,
                    (payload_id, source_format, failure_reason),
                )

        return self.get_import_run(import_run_id)

    def get_import_run(self, import_run_id: str) -> ImportRun:
        row = self._connection.execute(
            "SELECT * FROM import_runs WHERE import_run_id = ?", (import_run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(import_run_id)
        return ImportRun(
            import_run_id=row["import_run_id"],
            payload_id=row["payload_id"],
            declared_account_id=row["declared_account_id"],
            source_format=row["source_format"],
            original_filename=row["original_filename"],
            exported_on=date.fromisoformat(row["exported_on"]),
            exported_on_source=row["exported_on_source"],
            covers_through=date.fromisoformat(row["covers_through"]),
            covers_through_source=row["covers_through_source"],
            started_at=datetime.fromisoformat(row["started_at"]),
            outcome=row["outcome"],
            repeat_of=row["repeat_of"],
        )

    def get_payload(self, payload_id: str) -> RawPayload:
        row = self._connection.execute(
            "SELECT * FROM raw_payloads WHERE payload_id = ?", (payload_id,)
        ).fetchone()
        if row is None:
            raise KeyError(payload_id)
        return RawPayload(
            payload_id=row["payload_id"],
            byte_length=row["byte_length"],
            content=row["content"],
        )

    def get_source_records(self, payload_id: str) -> tuple[SourceRecord, ...]:
        rows = self._connection.execute(
            "SELECT * FROM source_records WHERE payload_id = ? ORDER BY record_ordinal",
            (payload_id,),
        )
        return tuple(
            SourceRecord(
                payload_id=row["payload_id"],
                record_ordinal=row["record_ordinal"],
                fields=MappingProxyType(json.loads(row["fields"])),
            )
            for row in rows
        )

    def get_format_failures(self, payload_id: str) -> tuple[FormatFailure, ...]:
        rows = self._connection.execute(
            "SELECT * FROM format_failures WHERE payload_id = ? ORDER BY source_format",
            (payload_id,),
        )
        return tuple(
            FormatFailure(
                payload_id=row["payload_id"],
                source_format=row["source_format"],
                reason=row["reason"],
            )
            for row in rows
        )
