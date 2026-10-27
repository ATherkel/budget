# Copyright 2026 Therkel
"""Enkel's monthly actuals: the report's figures, Categories and trust notes.

Expected values are the worked examples in `report-contract.md`, over the
synthetic worked-example publication; the dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Page, read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

# The worked examples' reference date: May is the current month.
REFERENCE_DATE = "2026-05-14"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def report(
    client: TestClient,
    month: str,
    accounts: tuple[str, ...] = (CURRENT, SAVINGS),
    reference_date: str = REFERENCE_DATE,
) -> Page:
    """Return the report fragment the page's form asks for."""
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": reference_date,
            "account": list(accounts),
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_the_report_shows_income_expenses_and_money_left_in_danish_kroner(
    client: TestClient,
) -> None:
    # February: income 25,000.00, expenses 9,020.00, net cash flow 15,980.00.
    february = report(client, "2026-02")

    assert (
        february.text_of("income"),
        february.text_of("expenses"),
        february.text_of("money-left"),
    ) == ("25.000,00 kr.", "9.020,00 kr.", "15.980,00 kr.")


def test_every_category_is_listed_in_the_order_the_report_gives(
    client: TestClient,
) -> None:
    # February: rent 8,500.00, then groceries 520.00 (640.00 less a 120.00 Refund).
    february = report(client, "2026-02")

    assert february.text_of("categories") == "Rent 8.500,00 kr. Groceries 520,00 kr."


def test_money_left_below_zero_carries_a_minus_sign(client: TestClient) -> None:
    # March: income 0.00 and expenses 1,000.00 leave -1,000.00, written with
    # the minus sign the report contract writes, not a hyphen.
    march = report(client, "2026-03")

    assert march.text_of("money-left") == "\N{MINUS SIGN}1.000,00 kr."


def test_a_partial_report_names_its_incomplete_accounts_and_links_the_explanation(
    client: TestClient,
) -> None:
    # February is partial: Joint current's month has a balance break. The link
    # keeps the page's pinned context and selection.
    february = report(client, "2026-02")

    assert (
        "Joint current" in (february.text_of("coverage-note") or ""),
        "Joint savings" in (february.text_of("coverage-note") or ""),
        february.attributes("coverage-explanation").get("href"),
    ) == (
        True,
        False,
        (
            "/explanation?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-02"
        ),
    )
