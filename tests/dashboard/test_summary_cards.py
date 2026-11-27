# Copyright 2026 Therkel
"""Overblik's summary cards: one view model and one macro render every card.

Expected values are the Gold worked example's tables in
`tests/gold/worked_example.py`; the dashboard is driven in-process.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.analytics import MonthlyOverview, ReportContext, monthly_overview
from budget.dashboard import FEATURES, create_app, jinja_environment
from budget.dashboard.features.report.summary_cards import GroupCard, summary_cards
from budget.gold import GoldRecords, GoldResult, ReportingMonth
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Disclosure, Page, read
from tests.dashboard.test_monthly_actuals import OFFSETTING, report
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

CARDS = jinja_environment(FEATURES).from_string(
    '{% from "report/card.html" import summary_card %}'
    "{% for card in cards %}{{ summary_card(card) }}{% endfor %}"
)
# A card of the income group under a label of its own, to try the card logic.
TRIAL = GroupCard("income", "Prøve", "Ingen prøver i måneden.")


def _logged_in(root: Path, records: GoldRecords = RECORDS) -> TestClient:
    profile = dashboard_profile(root)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, records), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _logged_in(tmp_path)


def _overview(month: int, reference_date: date = date(2026, 5, 14)) -> MonthlyOverview:
    context = ReportContext(
        publication_id=PUBLICATION.publication_id,
        account_ids=frozenset((CURRENT, SAVINGS)),
        month=ReportingMonth(2026, month),
        reference_date=reference_date,
    )
    return monthly_overview(GoldResult(PUBLICATION, RECORDS), context, is_current=True)


def _rendered(overview: MonthlyOverview) -> Page:
    """Render the trial card through the one card macro."""
    return read(CARDS.render(cards=summary_cards(overview, (TRIAL,))))


def test_a_group_card_starts_closed_and_lists_its_rows() -> None:
    # February's income is one salary of 25,000.00 on 25 February.
    page = _rendered(_overview(2))

    assert page.disclosures.get("income-card") == Disclosure(
        open=False,
        summary="Prøve 25.000,00 kr.",
        rows=[("25.02.2026", "SALARY", "+25.000,00 kr.", "+25.000,00 kr.")],
    )


def test_a_quiet_month_shows_the_cards_own_empty_message() -> None:
    # May has evidence through 8 May but no transactions.
    page = _rendered(_overview(5))

    assert page.disclosures.get("income-card") == Disclosure(
        open=False,
        summary="Prøve 0,00 kr.",
        rows=[("Ingen prøver i måneden.",)],
    )


def test_a_month_without_data_says_so_in_the_card() -> None:
    # June on 3 June: no account has evidence yet.
    page = _rendered(_overview(6, reference_date=date(2026, 6, 3)))

    assert page.disclosures.get("income-card") == Disclosure(
        open=False,
        summary="Prøve Ingen data endnu",
        rows=[("Ingen data endnu.",)],
    )


def test_money_left_is_a_card_that_never_expands(client: TestClient) -> None:
    # February: income 25,000.00 less expenses 9,020.00.
    february = report(client, "2026-02")

    assert (
        february.text_of("money-left-card"),
        "money-left-card" in february.disclosures,
    ) == ("Penge tilbage 15.980,00 kr.", False)


def test_indtaegter_lists_each_income_with_its_bank_amount_and_contribution(
    client: TestClient,
) -> None:
    # April: a salary of 25,000.00 on 24 April and interest of 12.40 on 30 April.
    april = report(client, "2026-04")

    assert april.disclosures.get("income-card") == Disclosure(
        open=False,
        summary="Indtægter 25.012,40 kr.",
        rows=[
            ("30.04.2026", "INTEREST", "+12,40 kr.", "+12,40 kr."),
            ("24.04.2026", "SALARY", "+25.000,00 kr.", "+25.000,00 kr."),
        ],
    )


def test_a_month_without_income_says_so_in_indtaegter(client: TestClient) -> None:
    may = report(client, "2026-05")

    assert may.disclosures.get("income-card") == Disclosure(
        open=False, summary="Indtægter 0,00 kr.", rows=[("Ingen indtægter i måneden.",)]
    )


def test_udgifter_counts_a_refund_against_its_purchases(client: TestClient) -> None:
    # February: rent 8,500.00 and groceries 640.00, less a 120.00 grocery Refund.
    february = report(client, "2026-02")

    assert february.disclosures.get("expenses-card") == Disclosure(
        open=False,
        summary="Udgifter 9.020,00 kr.",
        rows=[
            ("12.02.2026", "GROCERIES", "+120,00 kr.", "\N{MINUS SIGN}120,00 kr."),
            ("02.02.2026", "GROCERIES", "\N{MINUS SIGN}640,00 kr.", "+640,00 kr."),
            ("02.02.2026", "RENT", "\N{MINUS SIGN}8.500,00 kr.", "+8.500,00 kr."),
        ],
    )


def test_a_month_without_expenses_says_so_in_udgifter(client: TestClient) -> None:
    may = report(client, "2026-05")

    assert may.disclosures.get("expenses-card") == Disclosure(
        open=False, summary="Udgifter 0,00 kr.", rows=[("Ingen udgifter i måneden.",)]
    )


def test_overfoersler_lists_both_legs_of_a_transfer(client: TestClient) -> None:
    # January: 3,000.00 moves from Joint current to Joint savings on 20 January.
    january = report(client, "2026-01")

    assert january.disclosures.get("transfers-card") == Disclosure(
        open=False,
        summary="Overførsler 0,00 kr.",
        rows=[
            ("20.01.2026", "TRANSFER", "+3.000,00 kr.", "+3.000,00 kr."),
            (
                "20.01.2026",
                "TRANSFER",
                "\N{MINUS SIGN}3.000,00 kr.",
                "\N{MINUS SIGN}3.000,00 kr.",
            ),
        ],
    )


def test_overfoersler_into_the_selection_carry_a_plus_sign(client: TestClient) -> None:
    january = report(client, "2026-01", accounts=(SAVINGS,))

    assert january.text_of("transfers") == "+3.000,00 kr."


def test_a_month_without_transfers_says_so_in_overfoersler(client: TestClient) -> None:
    may = report(client, "2026-05")

    assert may.disclosures.get("transfers-card") == Disclosure(
        open=False,
        summary="Overførsler 0,00 kr.",
        rows=[("Ingen overførsler i måneden.",)],
    )


def test_ukategoriseret_names_account_and_direction_money_in_first(
    tmp_path: Path,
) -> None:
    # April on Joint current: +1,000.00 in, then -600.00 and -400.00 out.
    records = replace(RECORDS, transactions=(*RECORDS.transactions, *OFFSETTING))
    april = report(_logged_in(tmp_path, records), "2026-04", accounts=(CURRENT,))
    minus = "\N{MINUS SIGN}"

    assert april.disclosures.get("unclassified-card") == Disclosure(
        open=False,
        summary=f"Ukategoriseret Ind +1.000,00 kr. Ud {minus}1.000,00 kr.",
        rows=[
            (
                "10.04.2026",
                "UNKNOWN",
                "Joint current",
                "Ind",
                "+1.000,00 kr.",
                "+1.000,00 kr.",
            ),
            (
                "10.04.2026",
                "UNKNOWN",
                "Joint current",
                "Ud",
                f"{minus}400,00 kr.",
                f"{minus}400,00 kr.",
            ),
            (
                "10.04.2026",
                "UNKNOWN",
                "Joint current",
                "Ud",
                f"{minus}600,00 kr.",
                f"{minus}600,00 kr.",
            ),
        ],
    )


def test_a_month_without_unclassified_money_says_so_in_ukategoriseret(
    client: TestClient,
) -> None:
    february = report(client, "2026-02")

    assert february.disclosures.get("unclassified-card") == Disclosure(
        open=False,
        summary="Ukategoriseret Ind 0,00 kr. Ud 0,00 kr.",
        rows=[("Ingen ukategoriserede posteringer i måneden.",)],
    )
