# Copyright 2026 Therkel
"""The Danish words and sentences the dashboard's pages show their reader."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from budget.analytics import (
    AccountMonth,
    AccountMonthCoverage,
    ActivityRow,
    BankBalanceObservation,
    MonthlyBalanceObservation,
    ReportCoverage,
)
from budget.analytics.reports import AccountMonthStatus
from budget.analytics.trust import AccountMonthState
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import (
    account_names,
    balance_observation,
    coverage_gap,
    coverage_label,
    coverage_note,
    evidence_line,
    incomplete_months,
    monthly_snapshot_line,
    transaction_kind,
)
from budget.gold import ReportingMonth
from budget.gold.models import TransactionType


def test_a_date_reads_day_month_and_year_with_points() -> None:
    assert danish_date(date(2026, 2, 3)) == "03.02.2026"


def _row(transaction_type: TransactionType) -> ActivityRow:
    return ActivityRow(
        transaction_date=date(2026, 2, 3),
        description="Betaling",
        account_id="current",
        account_display_name="Lønkonto",
        amount=Decimal("-100.00"),
        transaction_type=transaction_type,
        transfer_pairing=None,
        counterpart_account_id=None,
        counterpart_account_display_name=None,
        counterpart_transaction_date=None,
    )


@pytest.mark.parametrize(
    ("transaction_type", "kind"),
    [
        ("income", "Indtægt"),
        ("expense", "Udgift"),
        ("refund", "Tilbagebetaling"),
        ("adjustment", "Regulering"),
    ],
)
def test_a_transaction_names_its_type_in_danish(
    transaction_type: TransactionType, kind: str
) -> None:
    assert transaction_kind(_row(transaction_type)) == kind


def test_a_paired_transfer_names_the_account_and_date_of_its_other_half() -> None:
    row = replace(
        _row("transfer"),
        transfer_pairing="paired",
        counterpart_account_id="savings",
        counterpart_account_display_name="Opsparing",
        counterpart_transaction_date=date(2026, 2, 4),
    )

    assert transaction_kind(row) == "Overførsel, parret med Opsparing den 04.02.2026"


def test_a_transfer_with_no_other_half_says_it_is_one_sided() -> None:
    row = replace(_row("transfer"), transfer_pairing="one_sided")

    assert transaction_kind(row) == "Overførsel, ensidig"


def test_a_transaction_of_unknown_type_reads_as_uncategorised() -> None:
    assert transaction_kind(_row("unknown")) == "Ukategoriseret"


@pytest.mark.parametrize(
    ("state", "label"),
    [
        ("complete", "fuldt dækket"),
        ("partial", "delvist dækket"),
        ("no_data", "ingen data"),
        ("outside_history", "uden for historikken"),
    ],
)
def test_an_account_months_coverage_reads_in_danish(
    state: AccountMonthState, label: str
) -> None:
    assert coverage_label(state) == label


def test_a_balance_never_observed_reads_as_the_missing_text() -> None:
    shown = balance_observation(None, "DKK", "Ingen tidligere observation")

    assert shown == "Ingen tidligere observation"


def test_a_balance_the_bank_left_blank_reads_as_unknown_on_its_date() -> None:
    observation = BankBalanceObservation(date(2026, 2, 3), balance_after=None)

    shown = balance_observation(observation, "DKK", "Ingen observation i måneden")

    assert shown == "Ukendt den 03.02.2026"


def test_a_stated_balance_reads_as_its_amount_on_its_date() -> None:
    observation = BankBalanceObservation(date(2026, 2, 3), Decimal("-1234.50"))

    shown = balance_observation(observation, "DKK", "Ingen observation i måneden")

    assert shown == "\N{MINUS SIGN}1.234,50 kr. den 03.02.2026"


def test_a_coverage_note_with_no_account_in_history_says_none_has_history() -> None:
    note = coverage_note("no_data", [], "februar 2026")

    assert note == "Ingen af de valgte konti har historik i februar 2026."


def test_a_coverage_note_with_no_data_yet_names_the_accounts() -> None:
    note = coverage_note("no_data", ["Lønkonto", "Opsparing"], "februar 2026")

    assert note == "Der er ingen data endnu fra Lønkonto og Opsparing."


def test_a_partial_coverage_note_says_what_the_figures_lack() -> None:
    note = coverage_note("partial", ["Lønkonto"], "februar 2026")

    assert note == "Tallene mangler noget fra Lønkonto."


def _month(display_name: str, status: AccountMonthStatus) -> AccountMonthCoverage:
    return AccountMonthCoverage(
        display_name.lower(), display_name, ReportingMonth(2026, 2), status
    )


def test_a_month_outside_an_accounts_history_lacks_nothing() -> None:
    current = _month("Lønkonto", "partial")
    savings = _month("Opsparing", "outside_history")
    budget = _month("Budgetkonto", "no_data")
    coverage = ReportCoverage("partial", (current, savings, budget))

    assert incomplete_months(coverage) == [current, budget]


def test_account_months_read_as_their_accounts_names_in_a_danish_list() -> None:
    february = ReportingMonth(2026, 2)
    months = [
        AccountMonth("acc-1", "Lønkonto", february),
        AccountMonth("acc-2", "Budgetkonto", february),
    ]

    assert account_names(months) == "Lønkonto og Budgetkonto"


@pytest.mark.parametrize(
    ("status", "gap"),
    [
        ("no_data", "der er ingen data for måneden endnu."),
        ("partial", "kun en del af måneden er dækket."),
    ],
)
def test_an_incomplete_month_says_what_it_lacks(
    status: AccountMonthStatus, gap: str
) -> None:
    assert coverage_gap(status) == gap


def test_an_account_with_nothing_imported_says_so() -> None:
    assert evidence_line(None) == "Ingen importeret data"


def test_an_accounts_imported_data_reaches_through_its_last_date() -> None:
    assert evidence_line(date(2026, 2, 3)) == "Gennem 03.02.2026"


def test_a_month_without_a_published_snapshot_says_so() -> None:
    assert monthly_snapshot_line(None, "DKK") == "Ingen månedssnapshot"


def test_a_monthly_snapshot_reads_its_opening_closing_and_coverage() -> None:
    snapshot = MonthlyBalanceObservation(
        opening_balance=Decimal("1000.00"),
        closing_balance=None,
        coverage="partial",
        late_bookings_settled=False,
    )

    assert monthly_snapshot_line(snapshot, "DKK") == (
        "Månedssnapshot: Åbning 1.000,00 kr.; lukning Ingen data endnu; delvist dækket."
    )
