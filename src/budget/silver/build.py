# Copyright 2026 Therkel
"""The Silver build: canonical records from a set of Bronze import runs."""

from collections.abc import Mapping, Sequence

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.models import SilverResult


def build(
    *,
    runs: Sequence[ImportRun],
    source_records: Mapping[str, Sequence[SourceRecord]],
    format_failures: Mapping[str, Sequence[FormatFailure]],
    currencies: Mapping[str, str],
) -> SilverResult:
    """Derive Silver from import runs, their payloads' records and currencies."""
    raise NotImplementedError
