# Copyright 2026 Therkel
"""Selection options and selection validation of `report-contract.md` (#179).

Every expected value is copied from the contract's worked examples, not
derived from the code under test.
"""

from dataclasses import replace
from datetime import date

import pytest

from budget.analytics import (
    InvalidSelectionError,
    ReportContext,
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
    monthly_overview,
    selection_options,
)
from budget.gold import GoldRecords, GoldResult, ReportingMonth
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS

GOLD = GoldResult(PUBLICATION, RECORDS)
REFERENCE_DATE = date(2026, 5, 14)
FEBRUARY = ReportingMonth(2026, 2)
P1 = ReportPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=PUBLICATION.known_at,
    is_current=True,
)
JOINT_ACCOUNTS = (
    SelectableAccount("joint-current", "Joint current", "current", "household", "DKK"),
    SelectableAccount("joint-savings", "Joint savings", "savings", "household", "DKK"),
)


def test_a_page_may_select_every_account_from_the_first_snapshot_month() -> None:
    assert selection_options(GOLD, REFERENCE_DATE, is_current=True) == (
        SelectionOptions(
            publication=P1,
            accounts=JOINT_ACCOUNTS,
            first_month=ReportingMonth(2026, 1),
            last_month=ReportingMonth(2026, 5),
        )
    )


def test_before_any_snapshot_only_the_reference_month_is_selectable() -> None:
    gold = GoldResult(PUBLICATION, GoldRecords(accounts=RECORDS.accounts))

    options = selection_options(gold, REFERENCE_DATE, is_current=True)

    assert (options.first_month, options.last_month) == (
        ReportingMonth(2026, 5),
        ReportingMonth(2026, 5),
    )


def _context(*account_ids: str, month: ReportingMonth = FEBRUARY) -> ReportContext:
    return ReportContext(
        publication_id=1,
        account_ids=frozenset(account_ids),
        month=month,
        reference_date=REFERENCE_DATE,
    )


def _broken_rules(gold: GoldResult, context: ReportContext) -> InvalidSelectionError:
    with pytest.raises(InvalidSelectionError) as raised:
        monthly_overview(gold, context, is_current=True)
    return raised.value


def test_an_empty_selection_is_never_a_zero_report() -> None:
    assert _broken_rules(GOLD, _context()).reasons == {"no_accounts"}


def test_an_account_outside_the_publication_is_named() -> None:
    broken = _broken_rules(GOLD, _context(CURRENT, "old-current"))

    assert (broken.reasons, broken.unknown_account_ids) == (
        {"unknown_account"},
        ("old-current",),
    )


def test_accounts_in_different_currencies_are_never_aggregated() -> None:
    euro = replace(RECORDS.accounts[1], account_id="euro-savings", currency="EUR")
    gold = GoldResult(PUBLICATION, replace(RECORDS, accounts=(*RECORDS.accounts, euro)))

    assert _broken_rules(gold, _context(CURRENT, "euro-savings")).reasons == {
        "mixed_currencies"
    }


@pytest.mark.parametrize(
    "month",
    [ReportingMonth(2025, 12), ReportingMonth(2026, 6)],
    ids=["before-the-first-snapshot", "after-the-reference-month"],
)
def test_a_month_outside_the_selectable_range_is_refused(
    month: ReportingMonth,
) -> None:
    assert _broken_rules(GOLD, _context(CURRENT, month=month)).reasons == {
        "month_out_of_range"
    }


def test_every_broken_rule_is_named_at_once() -> None:
    context = _context(CURRENT, "old-current", month=ReportingMonth(2025, 12))

    assert _broken_rules(GOLD, context).reasons == {
        "unknown_account",
        "month_out_of_range",
    }


def test_a_report_never_answers_a_context_from_another_publication() -> None:
    # One page never mixes two publications (report-contract.md, ReportContext).
    context = replace(_context(CURRENT), publication_id=2)

    with pytest.raises(ValueError, match="names publication 2, but publication 1"):
        monthly_overview(GOLD, context, is_current=True)


def test_the_first_selectable_month_is_valid() -> None:
    report = monthly_overview(
        GOLD, _context(CURRENT, month=ReportingMonth(2026, 1)), is_current=True
    )

    assert report.context.month == ReportingMonth(2026, 1)
