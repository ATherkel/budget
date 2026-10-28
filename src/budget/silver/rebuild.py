# Copyright 2026 Therkel
"""Rebuilding Silver from Bronze inputs into the profile's store.

The build itself is the pure `budget.silver.build`, whose signature does not
change. A rebuild names its inputs once, in `SilverBuildInputs`, so the
persisted rebuild takes its one profile authority and that one value rather
than a long list of positional arguments.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.locking import WriterLock, writer_lock
from budget.profiles import Profile
from budget.silver.build import build
from budget.silver.decisions import SilverDecision
from budget.silver.fingerprint import SILVER_FINGERPRINT_SCHEME, result_fingerprint
from budget.silver.identity import IDENTITY_VERSION
from budget.silver.models import SilverImportRun, SilverProvenance, SilverResult
from budget.silver.store import SilverStore

EMPTY_DECISION_LOG_PREFIX: Final = sha256(b"").hexdigest()


@dataclass(frozen=True, kw_only=True)
class SilverBuildInputs:
    """Everything one Silver build reads, as `budget.silver.build` names it."""

    runs: Sequence[ImportRun]
    source_records: Mapping[str, Sequence[SourceRecord]]
    format_failures: Mapping[str, Sequence[FormatFailure]]
    currencies: Mapping[str, str]
    decisions: Sequence[SilverDecision] = ()
    decision_log_position: int = 0
    decision_log_prefix_sha256: str = EMPTY_DECISION_LOG_PREFIX
    code_version: str | None = None
    identity_version: str = IDENTITY_VERSION


def rebuild_silver(
    profile: Profile | WriterLock,
    *,
    inputs: SilverBuildInputs,
) -> SilverResult:
    """Rebuild one profile's Silver store from Bronze inputs and return it.

    The build is the existing pure `budget.silver.build`; this function only
    replaces the stored result with what the build produced, so a rebuild is
    one transaction against `silver.db`. `profile` is the one authority for the
    profile the result belongs to, named either way: a `Profile` takes and
    releases the writer lock itself, and a `WriterLock` is a command's own
    lock, held for its whole run, which the rebuild reuses without acquiring it
    a second time.
    """
    if isinstance(profile, WriterLock):
        return _replace(profile.profile, inputs)
    with writer_lock(profile) as held:
        return _replace(held.profile, inputs)


def _replace(profile: Profile, inputs: SilverBuildInputs) -> SilverResult:
    """Run the pure build and store exactly what it produced."""
    result = build(
        runs=inputs.runs,
        source_records=inputs.source_records,
        format_failures=inputs.format_failures,
        currencies=inputs.currencies,
        decisions=tuple(inputs.decisions),
    )
    provenance = SilverProvenance(
        fingerprint_scheme=SILVER_FINGERPRINT_SCHEME,
        result_fingerprint=result_fingerprint(result, currencies=inputs.currencies),
        import_runs=_consumed_runs(inputs.runs),
        currencies=inputs.currencies,
        decisions=tuple(inputs.decisions),
        decision_log_position=inputs.decision_log_position,
        decision_log_prefix_sha256=inputs.decision_log_prefix_sha256,
        code_version=inputs.code_version,
        identity_version=inputs.identity_version,
    )
    with SilverStore(profile) as store:
        store.replace(result, currencies=inputs.currencies, provenance=provenance)
    return result


def _consumed_runs(runs: Sequence[ImportRun]) -> frozenset[SilverImportRun]:
    """Return every stored or repeated run Silver actually interpreted."""
    return frozenset(
        SilverImportRun(run.import_run_id, run.payload_id)
        for run in runs
        if run.outcome in {"stored", "repeat"}
    )
