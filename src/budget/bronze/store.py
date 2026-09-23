# Copyright 2026 Therkel
"""Bronze persistence: retain exact bytes, provenance, and source records.

The store is source-agnostic. It reads a file's bytes, resolves the export
date, asks the declared parser for that format to split the payload, and bounds
the declared coverage. It names no bank, no source field, no encoding, and no
date syntax: those belong to the parser the registry selects for the operator's
declared `source_format`.
"""

import json
import sqlite3
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType, TracebackType
from typing import Literal, Self
from uuid import uuid4

from budget.bronze.coverage import covers_through_for
from budget.bronze.models import FormatFailure, ImportRun, RawPayload, SourceRecord
from budget.bronze.parsers.registry import source_parser


class MissingExportDateError(ValueError):
    """The declared format reads no export date from the filename."""

    def __init__(self, source_format: str) -> None:
        """Name the format whose filename carries no usable export date."""
        super().__init__(
            "Declare exported_on: the declared source format "
            f"{source_format} reads no export date from this filename"
        )


def _outcome_for(
    *,
    refused: bool,
    repeat_of: str | None,
) -> Literal["stored", "repeat", "refused"]:
    """Name the run's outcome: a refusal first, then a repeat, then a store."""
    if refused:
        return "refused"
    if repeat_of is not None:
        return "repeat"
    return "stored"


class BronzeStore:
    """Import and retrieve Bronze provenance in a local SQLite store."""

    def __init__(self, database: str | Path) -> None:
        """Open the store, creating the Bronze tables in this database."""
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
        """Return the open store for a `with` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the store when the `with` block ends."""
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
        parser = source_parser(source_format)

        source = Path(path)
        content = source.read_bytes()
        payload_id = sha256(content).hexdigest()

        exported_on_source = "declared"
        if exported_on is None:
            inferred = parser.exported_on_from_filename(source.name)
            if inferred is None:
                raise MissingExportDateError(source_format)
            exported_on = inferred
            exported_on_source = "filename"

        result = parser.parse(content)
        failure_reason = result.failure_reason
        covers_through, covers_through_source, declaration_refused = covers_through_for(
            covers_through,
            exported_on,
            result.last_transaction_date,
            payload_readable=failure_reason is None,
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
            repeat_of = (
                original_run["import_run_id"] if original_run is not None else None
            )

            # Bytes already stored for another account are refused: the
            # payload has one owner, and only a manual decision may move it.
            account_conflict = None
            if repeat_of is None:
                account_conflict = self._connection.execute(
                    """
                    SELECT import_run_id FROM import_runs
                    WHERE payload_id = ? AND outcome = 'stored'
                        AND declared_account_id <> ?
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
                    covers_through, covers_through_source, started_at, outcome,
                    repeat_of
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
                    covers_through_source,
                    started_at.isoformat(),
                    _outcome_for(refused=refused, repeat_of=repeat_of),
                    repeat_of,
                ),
            )
            # Source records and format failures are derived cache: functions of
            # the payload, its format, and the parser, which a parser change can
            # regenerate at any time. A presentation therefore reconciles them -
            # and only them - while payload bytes and import-run history stay
            # untouched.
            if failure_reason is None:
                self._connection.execute(
                    """
                    DELETE FROM format_failures
                    WHERE payload_id = ? AND source_format = ?
                    """,
                    (payload_id, source_format),
                )
                self._connection.executemany(
                    """
                    INSERT INTO source_records (payload_id, record_ordinal, fields)
                    VALUES (?, ?, ?)
                    ON CONFLICT (payload_id, record_ordinal) DO NOTHING
                    """,
                    (
                        (payload_id, ordinal, json.dumps(dict(fields)))
                        for ordinal, fields in enumerate(result.records, start=1)
                    ),
                )
            else:
                # A payload that does not match the declared format has no
                # source records, so records a laxer parser derived for the same
                # bytes must not stay visible beside the stricter verdict.
                self._connection.execute(
                    "DELETE FROM source_records WHERE payload_id = ?", (payload_id,)
                )
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
        """Return one import run's stored provenance."""
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
        """Return one retained payload's exact bytes."""
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
        """Return one payload's source records, or nothing if it failed format."""
        # A payload that failed its format has no source records. The verdict
        # belongs to the payload, so it holds for a store written by any parser.
        failure = self._connection.execute(
            "SELECT 1 FROM format_failures WHERE payload_id = ? LIMIT 1",
            (payload_id,),
        ).fetchone()
        if failure is not None:
            return ()
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
        """Return the format verdicts recorded for one payload."""
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
