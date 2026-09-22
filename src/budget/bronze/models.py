"""Public Bronze contracts: provenance in, source records out."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


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
