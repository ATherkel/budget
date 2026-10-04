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
from collections.abc import Mapping
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType, TracebackType
from typing import Literal, Self
from uuid import uuid4

from budget.bronze.coverage import declared_range_refused
from budget.bronze.models import (
    FormatFailure,
    ImportDeclaration,
    ImportRun,
    RawPayload,
    SourceRecord,
)
from budget.bronze.parsers.base import ParserResult, SourceParser
from budget.bronze.parsers.registry import (
    UnsupportedSourceFormatError,
    source_formats,
    source_parser,
)
from budget.bronze.storage import open_bronze_connection, open_bronze_snapshot
from budget.profiles import Profile


class MissingExportDateError(ValueError):
    """The declared format reads no export date from the filename."""

    def __init__(self, source_format: str) -> None:
        """Name the format whose filename carries no usable export date."""
        super().__init__(
            "Declare exported_on: the declared source format "
            f"{source_format} reads no export date from this filename"
        )


class ParserFormatMismatchError(ValueError):
    """A parser was registered under a format ID it does not name."""

    def __init__(self, source_format: str, parser_format: str) -> None:
        """Name both IDs, so the mislabelled provenance is obvious."""
        super().__init__(
            f"parser {parser_format!r} cannot be registered as {source_format!r}"
        )


def _parsers_for(
    parsers: Mapping[str, SourceParser] | None,
) -> Mapping[str, SourceParser]:
    """Copy the caller's parsers into a frozen map, or use the built-in ones."""
    if parsers is None:
        built_in = {
            source_format: source_parser(source_format)
            for source_format in source_formats()
        }
        return MappingProxyType(built_in)
    chosen: dict[str, SourceParser] = {}
    for source_format, parser in parsers.items():
        if parser.source_format != source_format:
            raise ParserFormatMismatchError(source_format, parser.source_format)
        chosen[source_format] = parser
    return MappingProxyType(chosen)


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


def _decide_outcome(
    connection: sqlite3.Connection,
    *,
    payload_id: str,
    declared_account_id: str,
    declaration_refused: bool,
) -> tuple[bool, str | None]:
    """Decide whether this presentation repeats, is refused, or is a new store."""
    original_run = connection.execute(
        """
        SELECT import_run_id FROM import_runs
        WHERE payload_id = ? AND declared_account_id = ? AND outcome = 'stored'
        ORDER BY started_at, import_run_id
        LIMIT 1
        """,
        (payload_id, declared_account_id),
    ).fetchone()
    repeat_of: str | None = None
    if original_run is not None:
        repeat_of = str(original_run["import_run_id"])

    # Bytes already stored for another account are refused: the payload has one
    # owner, and only a manual decision may move it.
    account_conflict = None
    if repeat_of is None:
        account_conflict = connection.execute(
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
        # A refused run is nobody's original: it is never the run a later
        # presentation of these bytes repeats.
        repeat_of = None
    return refused, repeat_of


def _rebuild_derived_cache(
    connection: sqlite3.Connection,
    *,
    payload_id: str,
    source_format: str,
    result: ParserResult,
) -> None:
    """Replace one payload's derived cache with what this parser version says.

    Source records and the format verdict are functions of the bytes, the
    declared format and the parser, so a presentation regenerates them
    completely; the payload's bytes and every import run stay untouched.
    """
    connection.execute("DELETE FROM source_records WHERE payload_id = ?", (payload_id,))
    if result.failure_reason is None:
        connection.execute(
            """
            DELETE FROM format_failures
            WHERE payload_id = ? AND source_format = ?
            """,
            (payload_id, source_format),
        )
        connection.executemany(
            """
            INSERT INTO source_records (payload_id, record_ordinal, fields)
            VALUES (?, ?, ?)
            """,
            (
                (payload_id, ordinal, json.dumps(dict(fields)))
                for ordinal, fields in enumerate(result.records, start=1)
            ),
        )
        return
    connection.execute(
        """
        INSERT INTO format_failures (payload_id, source_format, reason)
        VALUES (?, ?, ?)
        ON CONFLICT (payload_id, source_format) DO UPDATE SET reason = excluded.reason
        """,
        (payload_id, source_format, result.failure_reason),
    )


def _import_run(row: sqlite3.Row) -> ImportRun:
    """Read one `import_runs` row back as the run it records."""
    return ImportRun(
        import_run_id=row["import_run_id"],
        payload_id=row["payload_id"],
        declared_account_id=row["declared_account_id"],
        source_format=row["source_format"],
        original_filename=row["original_filename"],
        exported_on=date.fromisoformat(row["exported_on"]),
        exported_on_source=row["exported_on_source"],
        covers_from=date.fromisoformat(row["covers_from"]),
        covers_through=date.fromisoformat(row["covers_through"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        outcome=row["outcome"],
        repeat_of=row["repeat_of"],
    )


class BronzeStore:
    """Import and retrieve Bronze provenance in a local SQLite store."""

    def __init__(
        self,
        profile: Profile,
        *,
        parsers: Mapping[str, SourceParser] | None = None,
        snapshot: Path | None = None,
    ) -> None:
        """Open the migrated Bronze store that one profile names.

        With `snapshot`, open that backup snapshot of the profile's store
        instead, read-only: it can be read, never imported into.
        """
        selected = _parsers_for(parsers)
        if snapshot is None:
            self._connection = open_bronze_connection(profile)
        else:
            self._connection = open_bronze_snapshot(profile, snapshot)
        self._parsers = selected

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

    def _parser_for(self, source_format: str) -> SourceParser:
        """Return the parser this store uses for one declared format."""
        try:
            return self._parsers[source_format]
        except KeyError:
            raise UnsupportedSourceFormatError(source_format) from None

    def import_file(
        self,
        path: str | Path,
        declaration: ImportDeclaration,
    ) -> ImportRun:
        """Retain a file's bytes, provenance, and decoded source records."""
        started_at = datetime.now(UTC)
        source_format = declaration.source_format
        parser = self._parser_for(source_format)

        source = Path(path)
        content = source.read_bytes()
        payload_id = sha256(content).hexdigest()

        exported_on = declaration.exported_on
        exported_on_source = "declared"
        if exported_on is None:
            inferred = parser.exported_on_from_filename(source.name)
            if inferred is None:
                raise MissingExportDateError(source_format)
            exported_on = inferred
            exported_on_source = "filename"

        result = parser.parse(content)
        declaration_refused = declared_range_refused(
            covers_from=declaration.covers_from,
            covers_through=declaration.covers_through,
            exported_on=exported_on,
            first_transaction_date=result.first_transaction_date,
            last_transaction_date=result.last_transaction_date,
        )
        import_run_id = uuid4().hex

        # Commit the payload, provenance, and derived records together.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            refused, repeat_of = _decide_outcome(
                self._connection,
                payload_id=payload_id,
                declared_account_id=declaration.declared_account_id,
                declaration_refused=declaration_refused,
            )

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
                    covers_from, covers_through, started_at, outcome, repeat_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_run_id,
                    payload_id,
                    declaration.declared_account_id,
                    source_format,
                    source.name,
                    exported_on.isoformat(),
                    exported_on_source,
                    declaration.covers_from.isoformat(),
                    declaration.covers_through.isoformat(),
                    started_at.isoformat(),
                    _outcome_for(refused=refused, repeat_of=repeat_of),
                    repeat_of,
                ),
            )
            _rebuild_derived_cache(
                self._connection,
                payload_id=payload_id,
                source_format=source_format,
                result=result,
            )

        return self.get_import_run(import_run_id)

    def get_import_run(self, import_run_id: str) -> ImportRun:
        """Return one import run's stored provenance."""
        row = self._connection.execute(
            "SELECT * FROM import_runs WHERE import_run_id = ?", (import_run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(import_run_id)
        return _import_run(row)

    def import_runs(self) -> tuple[ImportRun, ...]:
        """Return every import run's stored provenance, oldest first."""
        rows = self._connection.execute(
            "SELECT * FROM import_runs ORDER BY started_at, import_run_id"
        )
        return tuple(_import_run(row) for row in rows)

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
        """Return the source records the current parser derived for a payload."""
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


class ProductionImportBlockedError(RuntimeError):
    """Production imports wait for the command that backs up after them."""
