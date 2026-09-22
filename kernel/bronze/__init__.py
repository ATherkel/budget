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
            raise NotImplementedError("Only danske-csv-v1 is supported")

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

        reader = csv.reader(
            StringIO(content.decode("cp1252", errors="strict"), newline=""),
            delimiter=",",
            quotechar='"',
            strict=True,
        )
        header = next(reader)
        records = [dict(zip(header, values, strict=True)) for values in reader]
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

            if repeat_of is None:
                self._connection.execute(
                    "INSERT INTO raw_payloads (payload_id, byte_length, content) VALUES (?, ?, ?)",
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
                    "repeat" if repeat_of is not None else "stored",
                    repeat_of,
                ),
            )
            if repeat_of is None:
                self._connection.executemany(
                    "INSERT INTO source_records (payload_id, record_ordinal, fields) VALUES (?, ?, ?)",
                    (
                        (payload_id, ordinal, json.dumps(fields))
                        for ordinal, fields in enumerate(records, start=1)
                    ),
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
