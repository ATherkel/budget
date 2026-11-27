# Copyright 2026 Therkel
"""Overblik's summary cards: one view model and one macro render every card.

Expected values are the Gold worked example's tables in
`tests/gold/worked_example.py`; the dashboard is driven in-process.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.analytics import MonthlyOverview, ReportContext, monthly_overview
from budget.dashboard import FEATURES, create_app, jinja_environment
from budget.dashboard.features.report.summary_cards import GroupCard, summary_cards
from budget.gold import GoldResult, ReportingMonth
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Disclosure, Page, read
from tests.dashboard.test_monthly_actuals import report
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

CARDS = jinja_environment(FEATURES).from_string(
    '{% from "report/card.html" import summary_card %}'
    "{% for card in cards %}{{ summary_card(card) }}{% endfor %}"
)
# A card of the income group under a label of its own, to try the card logic.
TRIAL = GroupCard("income", "Prøve", "Ingen prøver i måneden.")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


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
