# Copyright 2026 Therkel
"""Rebuilding Silver from Bronze inputs into the profile's store.

The build itself is `tests/silver/`'s existing subject; this module covers the
step that puts its result in `silver.db`: the writer lock, one replacement, and
the `SilverResult` the caller gets back.
"""

import unittest
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory

import pytest

from budget.locking import WriterLockHeldError, writer_lock
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.silver import (
    SilverBuildInputs,
    SilverResult,
    SilverStore,
    VoidImportRun,
    build,
    rebuild_silver,
)
from budget.silver.decisions import SilverDecision
from budget.silver.storage import migrate_silver
from tests.silver.exports import Export, export, row

# A quiet first export, then one that adds a late booking the balances explain.
FIRST = export(
    [row("01.03.2026", "NETTO", "-45,00", "955,00")],
    run_id="run-a",
    exported_on=date(2026, 3, 5),
    covers_through=date(2026, 3, 4),
)
LATER = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "BIO", "-100,00", "855,00"),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
    covers_through=date(2026, 3, 8),
)


def _inputs(
    *exports: Export, decisions: Sequence[SilverDecision] = ()
) -> SilverBuildInputs:
    """The one value a rebuild names its Bronze inputs in."""
    return SilverBuildInputs(
        runs=[each.run for each in exports],
        source_records={each.run.payload_id: each.records for each in exports},
        format_failures={each.run.payload_id: each.failures for each in exports},
        currencies={each.run.declared_account_id: "DKK" for each in exports},
        decisions=decisions,
    )


def _pure_build(inputs: SilverBuildInputs) -> SilverResult:
    """The same inputs through the unchanged pure `budget.silver.build`."""
    return build(
        runs=inputs.runs,
        source_records=inputs.source_records,
        format_failures=inputs.format_failures,
        currencies=inputs.currencies,
        decisions=inputs.decisions,
    )


def _rebuild_with_profile_keyword(
    call: Callable[..., SilverResult], profile: Profile, inputs: SilverBuildInputs
) -> SilverResult:
    """Call a rebuild the way public callers wrote it before `target`.

    The parameter is a plain callable, so the keyword call belongs to the
    callback contract and not to the current function's own signature.
    """
    return call(profile=profile, inputs=inputs)


def _stored_dates(profile: Profile) -> list[date]:
    """The stored transactions' dates, in their stored order."""
    with SilverStore(profile) as store:
        return [item.transaction_date for item in store.read().transactions]


class SilverRebuildTests(unittest.TestCase):
    def test_rebuild_silver_stores_what_the_pure_build_produces(self) -> None:
        inputs = _inputs(FIRST, LATER)
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            result = rebuild_silver(profile, inputs=inputs)

            assert result == _pure_build(inputs)
            with SilverStore(profile) as store:
                assert store.read() == result

    def test_rebuilding_again_replaces_the_stored_result(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            first = rebuild_silver(profile, inputs=_inputs(FIRST))
            second = rebuild_silver(profile, inputs=_inputs(FIRST, LATER))

            assert second != first
            assert _stored_dates(profile) == [date(2026, 3, 1), date(2026, 3, 3)]
            with SilverStore(profile) as store:
                assert store.read() == second

    def test_a_voided_run_leaves_the_rebuilt_result(self) -> None:
        # *Void import run* is a build rule, not a rebuild rule: rebuilding
        # with the decision simply stores the build's result again.
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            rebuild_silver(profile, inputs=_inputs(FIRST, LATER))

            rebuild_silver(
                profile,
                inputs=_inputs(
                    FIRST,
                    LATER,
                    decisions=(
                        VoidImportRun(decision_id="d-0001", import_run_id="run-b"),
                    ),
                ),
            )

            with SilverStore(profile) as store:
                stored = store.read()
            assert [run.import_run_id for run in stored.import_run_results] == ["run-a"]
            assert [item.transaction_date for item in stored.transactions] == [
                date(2026, 3, 1)
            ]

    def test_a_rebuild_refuses_while_another_command_holds_the_lock(self) -> None:
        inputs = _inputs(FIRST)
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with writer_lock(profile), pytest.raises(WriterLockHeldError):
                rebuild_silver(profile, inputs=inputs)

            # Nothing was written, so the store holds no result yet.
            with SilverStore(profile) as store:
                assert store.read() == SilverResult((), (), (), (), (), (), ())

    def test_a_held_writer_lock_is_the_rebuild_target(self) -> None:
        # A command that reads another store's inputs holds the profile's
        # writer lock for its whole run, so the rebuild takes that lock as its
        # one authority instead of acquiring the profile's lock a second time.
        inputs = _inputs(FIRST)
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with writer_lock(profile) as lock:
                result = rebuild_silver(lock, inputs=inputs)

            assert [(t.account_id, t.description) for t in result.transactions] == [
                ("joint-current", "NETTO")
            ]
            with SilverStore(profile) as store:
                stored = store.read()
            assert [
                (t.transaction_date, t.amount, t.balance, t.currency)
                for t in stored.transactions
            ] == [(date(2026, 3, 1), Decimal("-45.00"), Decimal("955.00"), "DKK")]
            assert [
                (run.import_run_id, run.status) for run in stored.import_run_results
            ] == [("run-a", "accepted")]
            assert stored.review_items == ()

    def test_the_profile_keyword_still_names_the_rebuild_target(self) -> None:
        # Before the target argument was renamed, callers wrote
        # `rebuild_silver(profile=..., inputs=...)`; that public call must keep
        # working. The helper's callable parameter exercises the keyword at
        # runtime without asking the type checker about the current signature.
        inputs = _inputs(FIRST)
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            _rebuild_with_profile_keyword(rebuild_silver, profile, inputs)

            with SilverStore(profile) as store:
                stored = store.read()
            assert [(t.account_id, t.description) for t in stored.transactions] == [
                ("joint-current", "NETTO")
            ]
            assert [
                (run.import_run_id, run.status) for run in stored.import_run_results
            ] == [("run-a", "accepted")]


if __name__ == "__main__":
    unittest.main()
