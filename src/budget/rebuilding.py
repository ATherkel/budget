# Copyright 2026 Therkel
"""The `rebuild` application operation: build a stage from its upstream.

Silver's build keeps its one definition, the pure `budget.silver.build`, and
this module is only the thin adapter a command calls: it reads the profile's
Bronze inputs and account registry, then hands them to the existing
`budget.silver.rebuild_silver`, which replaces the stored result. No build,
admission, or duplicate-resolution rule lives here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from budget.bronze import BronzeStore
from budget.bronze.models import ImportRun
from budget.inputs import load_accounts
from budget.locking import WriterLock
from budget.profiles import Profile
from budget.silver import SilverBuildInputs, SilverResult, rebuild_silver


@dataclass(frozen=True)
class SilverRebuild:
    """One Silver rebuild's Bronze provenance and the result it stored.

    The runs are the import runs read under the command's own writer lock,
    before that lock was released, so a summary reports what the build actually
    read instead of rereading a store a later command may have changed.
    """

    runs: Sequence[ImportRun]
    result: SilverResult


def bronze_inputs(profile: Profile) -> SilverBuildInputs:
    """Read every Bronze input one Silver build needs, and the currencies.

    The profile's import runs, each run's payload's source records or format
    failures, and each declared account's currency are read as they stand now.
    Manual decisions are not read: the decision-log reader is not built yet, so
    a build from here reads no decision rather than half of the log.
    """
    currencies = {
        account_id: account.currency
        for account_id, account in load_accounts(profile).items()
    }
    with BronzeStore(profile) as store:
        runs = store.import_runs()
        source_records = {
            run.payload_id: store.get_source_records(run.payload_id) for run in runs
        }
        format_failures = {
            run.payload_id: store.get_format_failures(run.payload_id) for run in runs
        }
    return SilverBuildInputs(
        runs=runs,
        source_records=source_records,
        format_failures=format_failures,
        currencies=currencies,
    )


def rebuild_from_silver(lock: WriterLock) -> SilverRebuild:
    """Rebuild the locked profile's Silver from its Bronze store.

    The caller holds the profile's writer lock for its whole command, so the
    Bronze inputs are read under that one lock and handed to the existing
    `budget.silver.rebuild_silver`, which replaces the stored result. The runs
    read here come back with the result, so no caller rereads Bronze.
    """
    profile = lock.profile
    inputs = bronze_inputs(profile)
    result = rebuild_silver(lock, inputs=inputs)
    return SilverRebuild(runs=inputs.runs, result=result)
