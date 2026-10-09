# Copyright 2026 Therkel
"""`gold.build`: Gold records from Silver, the account registry and the taxonomy.

Nothing is classified yet, so every transaction is `unknown`. The expected
records are the worked example's (`gold-layer.md`), and the other cases are
synthetic. Records come in no fixed order, so they are compared as multisets.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import (
    GoldAccount,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.inputs import Account
from budget.silver import AccountEvidence, EvidenceExport
from tests.gold.worked_example import (
    ACCOUNTS,
    CATEGORIES,
    CURRENT,
    MONTHLY_BALANCES,
    PUBLICATION,
    SAVINGS,
    TRANSACTIONS,
)
from tests.gold.worked_silver import (
    COVERS_FROM,
    REGISTRY,
    SILVER,
    build_from,
    silver_transaction,
)
from tests.silver import exports


def test_the_registry_and_taxonomy_are_published_as_dimensions() -> None:
    result = build_from()

    assert result.publication() == PUBLICATION
    assert Counter(result.accounts()) == Counter(ACCOUNTS)
    assert Counter(result.categories()) == Counter(CATEGORIES)


def test_an_account_with_no_export_is_published_without_evidence() -> None:
    unimported = Account(
        account_id="own-savings",
        display_name="Own savings",
        account_type="savings",
        ownership_scope="person",
        currency="DKK",
        source_format="danske-csv-v1",
    )

    result = build_from(accounts={**REGISTRY, "own-savings": unimported})

    assert Counter(result.accounts()) == Counter(
        (
            *ACCOUNTS,
            GoldAccount(
                account_id="own-savings",
                display_name="Own savings",
                account_type="savings",
                ownership_scope="person",
                currency="DKK",
                closed_on=None,
                coverage_start=None,
                evidence_through=None,
            ),
        )
    )


def _all_transactions(result: GoldResult) -> Sequence[GoldTransaction]:
    return result.transactions(start_date=date.min, end_date=date.max)


def test_each_booked_silver_transaction_is_one_unknown_gold_transaction() -> None:
    result = build_from()

    # The balance check has tests of its own.
    assert Counter(
        replace(t, balance_check="opening") for t in _all_transactions(result)
    ) == Counter(
        replace(
            t,
            description=f"TEXT {t.transaction_id}",
            transaction_type="unknown",
            transfer_group_id=None,
            balance_check="opening",
        )
        for t in TRANSACTIONS
    )


def test_a_pending_or_cancelled_silver_transaction_is_no_gold_transaction() -> None:
    unbooked = (
        replace(
            silver_transaction("pending", CURRENT, date(2026, 4, 28), "-60.00", None),
            booking_status="pending",
        ),
        replace(
            silver_transaction("cancelled", SAVINGS, date(2026, 3, 3), "5.00", None),
            booking_status="cancelled",
        ),
    )
    silver = replace(SILVER, transactions=(*SILVER.transactions, *unbooked))

    found = _all_transactions(build_from(silver))

    assert Counter(found) == Counter(_all_transactions(build_from()))


def test_the_worked_examples_balance_checks_come_out_exactly() -> None:
    result = build_from()

    assert {t.transaction_id: t.balance_check for t in _all_transactions(result)} == {
        t.transaction_id: t.balance_check for t in TRANSACTIONS
    }


def test_a_missing_balance_is_bridged_but_never_filled_in() -> None:
    stated = (
        silver_transaction("a", CURRENT, date(2026, 1, 5), "-5.00", None),
        silver_transaction("b", CURRENT, date(2026, 1, 6), "-10.00", "100.00"),
        silver_transaction("c", CURRENT, date(2026, 1, 7), "-10.00", None),
        silver_transaction("d", CURRENT, date(2026, 1, 8), "-10.00", "80.00"),
        silver_transaction("e", CURRENT, date(2026, 1, 9), "-10.00", "75.00"),
    )

    found = _all_transactions(build_from(replace(SILVER, transactions=stated)))

    assert [(t.transaction_id, t.balance_after, t.balance_check) for t in found] == [
        ("a", None, "missing_balance"),
        ("b", Decimal("100.00"), "opening"),
        ("c", None, "missing_balance"),
        # 100.00 - 10.00 - 10.00, bridging c's missing balance
        ("d", Decimal("80.00"), "consistent"),
        ("e", Decimal("75.00"), "break"),
    ]


def _all_snapshots(result: GoldResult) -> Sequence[MonthlyBalanceSnapshot]:
    return result.monthly_balances(
        start_month=ReportingMonth(1, 1), end_month=ReportingMonth(9999, 12)
    )


def test_the_worked_examples_months_and_coverage_come_out_exactly() -> None:
    result = build_from()

    # One row per month from the first transaction through May, the month of
    # the latest evidence_through, even though neither account has a May row.
    assert Counter(
        (s.account_id, s.month, s.coverage) for s in _all_snapshots(result)
    ) == Counter((s.account_id, s.month, s.coverage) for s in MONTHLY_BALANCES)


def test_the_worked_examples_balances_come_out_exactly() -> None:
    result = build_from()

    # joint-savings carries 53,000.00 through its complete quiet months, and
    # May, quiet with partial evidence, has no balance on either account.
    assert Counter(
        (s.account_id, s.month, s.opening_balance, s.closing_balance)
        for s in _all_snapshots(result)
    ) == Counter(
        (s.account_id, s.month, s.opening_balance, s.closing_balance)
        for s in MONTHLY_BALANCES
    )


def test_the_worked_examples_snapshots_come_out_exactly() -> None:
    result = build_from()

    # The only export, dated 2026-05-08, settles every month through April.
    assert Counter(_all_snapshots(result)) == Counter(MONTHLY_BALANCES)


APRIL = ReportingMonth(2026, 4)


def _settled(*exports: EvidenceExport) -> dict[ReportingMonth, bool]:
    """Which of joint-current's months these exports settle."""
    result = build_from(replace(SILVER, evidence_exports=exports))
    return {
        s.month: s.late_bookings_settled
        for s in _all_snapshots(result)
        if s.account_id == CURRENT
    }


def test_an_export_produced_under_7_days_after_a_month_does_not_settle_it() -> None:
    six_days_after = EvidenceExport(
        CURRENT, date(2026, 5, 6), COVERS_FROM, date(2026, 5, 6)
    )
    seven_days_after = EvidenceExport(
        CURRENT, date(2026, 5, 7), COVERS_FROM, date(2026, 5, 7)
    )

    assert _settled(six_days_after)[APRIL] is False
    assert _settled(seven_days_after)[APRIL] is True


def test_an_export_whose_range_misses_the_months_last_day_never_settles_it() -> None:
    starts_after = EvidenceExport(
        CURRENT, date(2026, 6, 30), date(2026, 5, 1), date(2026, 6, 30)
    )
    ends_before = EvidenceExport(
        CURRENT, date(2026, 6, 30), COVERS_FROM, date(2026, 4, 29)
    )

    # Each was produced long after April ended, but cannot show its late bookings.
    assert _settled(starts_after)[APRIL] is False
    assert _settled(ends_before)[APRIL] is False


def _rows(result: GoldResult, account_id: str) -> list[tuple[object, ...]]:
    """An account's (month, coverage, opening, closing, settled), month by month."""
    return [
        (
            s.month,
            s.coverage,
            s.opening_balance,
            s.closing_balance,
            s.late_bookings_settled,
        )
        for s in sorted(_all_snapshots(result), key=lambda s: s.month)
        if s.account_id == account_id
    ]


def test_an_account_whose_exports_lag_still_has_a_row_for_each_later_month() -> None:
    lagging = replace(
        SILVER,
        transactions=(
            *(t for t in SILVER.transactions if t.account_id == CURRENT),
            silver_transaction(
                "savings-01", SAVINGS, date(2026, 1, 20), "3000.00", "53000.00"
            ),
        ),
        account_evidence=(
            AccountEvidence(CURRENT, COVERS_FROM, date(2026, 5, 8)),
            AccountEvidence(SAVINGS, COVERS_FROM, date(2026, 3, 15)),
        ),
        evidence_exports=(
            EvidenceExport(CURRENT, date(2026, 5, 8), COVERS_FROM, date(2026, 5, 8)),
            EvidenceExport(SAVINGS, date(2026, 3, 15), COVERS_FROM, date(2026, 3, 15)),
        ),
    )

    result = build_from(lagging)

    # joint-current's evidence reaches May, so joint-savings has rows through May.
    assert _rows(result, SAVINGS) == [
        (
            ReportingMonth(2026, 1),
            "partial",
            Decimal("50000.00"),
            Decimal("53000.00"),
            True,
        ),
        (
            ReportingMonth(2026, 2),
            "complete",
            Decimal("53000.00"),
            Decimal("53000.00"),
            True,
        ),
        (ReportingMonth(2026, 3), "partial", None, None, False),
        (ReportingMonth(2026, 4), "no_data", None, None, False),
        (ReportingMonth(2026, 5), "no_data", None, None, False),
    ]


def test_a_closed_accounts_rows_end_at_its_closing_or_the_latest_month() -> None:
    def closing(on: date) -> list[ReportingMonth]:
        accounts = {**REGISTRY, SAVINGS: replace(REGISTRY[SAVINGS], closed_on=on)}
        result = build_from(accounts=accounts)
        return sorted(
            s.month for s in _all_snapshots(result) if s.account_id == SAVINGS
        )

    closed_in_april = closing(date(2026, 4, 30))
    # A closing recorded ahead of time never reaches past the published data.
    closing_in_september = closing(date(2026, 9, 30))

    assert closed_in_april == [ReportingMonth(2026, month) for month in (1, 2, 3, 4)]
    assert closing_in_september == [
        ReportingMonth(2026, month) for month in (1, 2, 3, 4, 5)
    ]


def test_a_quiet_accounts_repeated_export_settles_its_months() -> None:
    first = exports.declared(
        exports.export(
            [exports.row("10.01.2026", "LOEN", "1000,00", "1000,00")],
            run_id="run-1",
            exported_on=date(2026, 2, 3),
        ),
        covers_from=date(2026, 1, 1),
    )
    # Nothing new was booked, so the bank's next export has the same bytes.
    same_bytes = exports.repeat(first, run_id="run-2", exported_on=date(2026, 3, 10))
    registry = {exports.ACCOUNT: REGISTRY[CURRENT]}

    def settled(*runs: exports.Export) -> list[bool]:
        result = build_from(exports.build_from(*runs), accounts=registry)
        by_month = sorted(_all_snapshots(result), key=lambda s: s.month)
        return [s.late_bookings_settled for s in by_month]

    # Produced three days after January, the first export settles nothing.
    assert settled(first) == [False, False]
    assert settled(first, same_bytes) == [True, True, False]
