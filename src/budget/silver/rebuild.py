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
from budget.locking import WriterLock, writer_lock
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


def rebuild_silver(
    target: Profile | WriterLock,
    *,
    inputs: SilverBuildInputs,
) -> SilverResult:
    """Rebuild one profile's Silver store from Bronze inputs and return it.

    The build is the existing pure `budget.silver.build`; this function only
    replaces the stored result with what the build produced, so a rebuild is
    one transaction against `silver.db`. `target` is the one authority for the
    profile the result belongs to: a `Profile` takes and releases the writer
    lock itself, and a `WriterLock` is a command's own lock, held for its whole
    run, which the rebuild reuses without acquiring it a second time.
    """
    if isinstance(target, WriterLock):
        return _replace(target.profile, inputs)
    with writer_lock(target) as held:
        return _replace(held.profile, inputs)


def _replace(profile: Profile, inputs: SilverBuildInputs) -> SilverResult:
    """Run the pure build and store exactly what it produced."""
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
