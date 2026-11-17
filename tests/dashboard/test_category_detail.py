# Copyright 2026 Therkel
"""Category and group detail: the entries behind an overview figure.

Expected values are the "Spending detail" worked examples in
`report-contract.md`, over the synthetic worked-example publication; the
dashboard is driven in-process.
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

PINNED = (
    f"publication=1&reference_date={REFERENCE_DATE}&account={CURRENT}&account={SAVINGS}"
)


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


def report(client: TestClient, month: str) -> Page:
    """Return the overview's report fragment for both accounts in `month`."""
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": REFERENCE_DATE,
            "account": [CURRENT, SAVINGS],
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def detail(client: TestClient, month: str, query: str) -> Page:
    """Return the detail page `query` (`category=…&scope=…`) asks for."""
    response = client.get(f"/category?{PINNED}&month={month}&{query}")
    assert response.status_code == 200
    return read(response.text)


def test_each_overview_category_links_to_its_detail_in_the_same_pinned_context(
    client: TestClient,
) -> None:
    # February lists Rent and Groceries; each opens its own month detail
    # under the page's pin and selection.
    february = report(client, "2026-02")

    assert (
        february.attributes("category-link-groceries").get("href"),
        february.attributes("category-link-rent").get("href"),
    ) == (
        f"/category?{PINNED}&month=2026-02&category=groceries&scope=month",
        f"/category?{PINNED}&month=2026-02&category=rent&scope=month",
    )


def test_a_category_detail_shows_its_total_and_the_rows_behind_it(
    client: TestClient,
) -> None:
    # February groceries: the 120.00 Refund, then the 640.00 purchase, newest
    # first and in the spending sign, adding up to the overview's 520.00.
    groceries = detail(client, "2026-02", "category=groceries&scope=month")

    assert (
        groceries.text_of("detail-title"),
        groceries.text_of("detail-spending"),
        groceries.text_of("detail-rows"),
    ) == (
        "Groceries, februar 2026",
        "520,00 kr.",
        (
            "Dato Tekst Konto Beløb"
            " 12.02.2026 GROCERIES Joint current \N{MINUS SIGN}120,00 kr."
            " 02.02.2026 GROCERIES Joint current 640,00 kr."
        ),
    )


def test_the_scope_switch_keeps_the_pin_and_marks_the_scope_shown(
    client: TestClient,
) -> None:
    # Year to date through February adds January's 842.50: 1,362.50.
    groceries = f"/category?{PINNED}&month=2026-02&category=groceries"
    year = detail(client, "2026-02", "category=groceries&scope=year_to_date")

    assert (
        year.text_of("detail-spending"),
        year.attributes("scope-month").get("href"),
        year.attributes("scope-year-to-date").get("href"),
        year.attributes("scope-month").get("aria-current"),
        year.attributes("scope-year-to-date").get("aria-current"),
    ) == (
        "1.362,50 kr.",
        f"{groceries}&scope=month",
        f"{groceries}&scope=year_to_date",
        None,
        "page",
    )


def test_a_category_detail_links_its_whole_group_in_the_same_scope(
    client: TestClient,
) -> None:
    rent = detail(client, "2026-04", "category=rent&scope=year_to_date")

    assert (
        rent.text_of("group-link"),
        rent.attributes("group-link").get("href"),
    ) == (
        "Hele Housing",
        f"/category?{PINNED}&month=2026-04&group=housing&scope=year_to_date",
    )


def test_a_group_detail_names_each_rows_category_and_adds_up_the_group(
    client: TestClient,
) -> None:
    # April housing year to date: rent, utilities and rent, 18,000.00.
    housing = detail(client, "2026-04", "group=housing&scope=year_to_date")

    assert (
        housing.text_of("detail-title"),
        housing.text_of("detail-spending"),
        housing.text_of("detail-rows"),
        housing.text_of("group-link"),
    ) == (
        "Housing, april 2026",
        "18.000,00 kr.",
        (
            "Dato Tekst Konto Kategori Beløb"
            " 01.04.2026 RENT Joint current Rent 8.500,00 kr."
            " 20.03.2026 UTILITIES Joint current Utilities 1.000,00 kr."
            " 02.02.2026 RENT Joint current Rent 8.500,00 kr."
        ),
        None,
    )


def test_leaving_a_detail_returns_to_the_same_overview_with_the_same_figure(
    client: TestClient,
) -> None:
    # The way back keeps the pin, accounts and month, and the overview it
    # opens shows the figure the detail added up: Groceries 520.00.
    groceries = detail(client, "2026-02", "category=groceries&scope=year_to_date")
    back = groceries.attributes("back-to-overview").get("href")
    overview = client.get(back or "/")

    assert (back, overview.status_code) == (f"/?{PINNED}&month=2026-02", 200)
    assert (read(overview.text).text_of("categories") or "").endswith(
        "Groceries 520,00 kr."
    )
