# Copyright 2026 Therkel
"""What one Silver build reads, named once."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.decisions import SilverDecision
from budget.silver.formats import SourceFormat


@dataclass(frozen=True, kw_only=True)
class SilverBuildInputs:
    """Everything one Silver build reads, as `budget.silver.build` names it.

    `formats` replaces the built-in source formats for this build; without it
    every run is read in the format the application declares.
    """

    runs: Sequence[ImportRun]
    source_records: Mapping[str, Sequence[SourceRecord]]
    format_failures: Mapping[str, Sequence[FormatFailure]]
    currencies: Mapping[str, str]
    decisions: Sequence[SilverDecision] = ()
    decision_log_position: int = 0
    decision_log_prefix_sha256: str = ""
    code_version: str | None = None
    identity_version: str = "1"
    formats: Mapping[str, SourceFormat] | None = None
