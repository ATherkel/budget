# Copyright 2026 Therkel
"""Public Bronze contracts: provenance in, source records out."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


@dataclass(frozen=True)
class RawPayload:
    """One source's exact bytes, stored once under their SHA-256 identifier."""

    payload_id: str
    byte_length: int
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class ImportRun:
    """One presentation of a payload, with the operator's declarations."""

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
    """One record exactly as the source presented it, still uninterpreted."""

    payload_id: str
    record_ordinal: int
    fields: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class FormatFailure:
    """A verdict that a payload does not match its declared source format."""

    payload_id: str
    source_format: str
    reason: str
