# Copyright 2026 Therkel
"""The Danish words and sentences the dashboard's pages show their reader."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from budget.analytics import ActivityRow, BankBalanceObservation
from budget.analytics.trust import AccountMonthState
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import (
    balance_observation,
    coverage_label,
    coverage_note,
    transaction_kind,
)
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
