# Copyright 2026 Therkel
"""Rebuilding Silver from Bronze inputs into the profile's store.

The build itself is the pure `budget.silver.build`, whose signature does not
change. A rebuild names its inputs once, in `SilverBuildInputs`, so the
persisted rebuild takes a profile and that one value rather than a long list
of positional arguments.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver.build import build
from budget.silver.decisions import SilverDecision
from budget.silver.models import SilverResult
from budget.silver.store import SilverStore


@dataclass(frozen=True, kw_only=True)
class SilverBuildInputs:
    """Everything one Silver build reads, as `budget.silver.build` names it."""

    runs: Sequence[ImportRun]
    source_records: Mapping[str, Sequence[SourceRecord]]
    format_failures: Mapping[str, Sequence[FormatFailure]]
    currencies: Mapping[str, str]
    decisions: Sequence[SilverDecision] = ()


def rebuild_silver(profile: Profile, *, inputs: SilverBuildInputs) -> SilverResult:
    """Rebuild one profile's Silver store from Bronze inputs and return it.

    The build is the existing pure `budget.silver.build`; this function only
    takes the profile's writer lock and replaces the stored result with what
    the build produced, so a rebuild is one transaction against `silver.db`.
    """
    with writer_lock(profile):
        result = build(
            runs=inputs.runs,
            source_records=inputs.source_records,
            format_failures=inputs.format_failures,
            currencies=inputs.currencies,
            decisions=inputs.decisions,
        )
        with SilverStore(profile) as store:
            store.replace(result, currencies=inputs.currencies)
    return result
