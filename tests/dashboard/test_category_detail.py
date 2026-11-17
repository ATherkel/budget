# Copyright 2026 Therkel
"""Category and group detail: the entries behind an overview figure.

Expected values are the "Spending detail" worked examples in
`report-contract.md`, over the synthetic worked-example publication; the
dashboard is driven in-process.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldRecords, GoldResult
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


def logged_in(
    tmp_path: Path, publications: int = 1, records: GoldRecords = RECORDS
) -> TestClient:
    """Publish `records` `publications` times and log in to the dashboard."""
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        for publication_id in range(1, publications + 1):
            published = replace(PUBLICATION, publication_id=publication_id)
            store.publish(GoldResult(published, records), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return logged_in(tmp_path)


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
        "Housing, januar\N{EN DASH}april 2026",
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
    # opens shows the month detail's own figure: Groceries 520.00.
    groceries = detail(client, "2026-02", "category=groceries&scope=month")
    back = groceries.attributes("back-to-overview").get("href")
    overview = client.get(back or "/")

    assert (back, overview.status_code) == (f"/?{PINNED}&month=2026-02", 200)
    assert groceries.text_of("detail-spending") == "520,00 kr."
    assert (read(overview.text).text_of("categories") or "").endswith(
        f"Groceries {groceries.text_of('detail-spending')}"
    )


def test_a_detail_names_each_incomplete_month_of_its_scope_by_account(
    client: TestClient,
) -> None:
    # February year to date: Joint current's January and February and Joint
    # savings' January are partial. Neither month can still change.
    year = detail(client, "2026-02", "category=groceries&scope=year_to_date")

    assert (year.text_of("coverage-note"), year.text_of("provisional-label")) == (
        (
            "Tallene mangler noget fra Joint current (januar 2026, februar 2026)"
            " og Joint savings (januar 2026)."
        ),
        None,
    )


def test_a_detail_whose_scope_can_still_change_is_labelled_provisional(
    client: TestClient,
) -> None:
    # May is the current month, and its bookings are not settled.
    may = detail(client, "2026-05", "category=groceries&scope=year_to_date")

    assert may.text_of("provisional-label") == "Foreløbige tal"


@pytest.mark.parametrize(
    ("address", "said"),
    [
        (
            f"/category?{PINNED}&month=2026-02&category=homeware&scope=month",
            "Kategorien findes ikke i disse tal.",
        ),
        (
            f"/category?{PINNED}&month=2026-02&group=income&scope=month",
            "Kategorien findes ikke i disse tal.",
        ),
        (
            f"/category?{PINNED}&month=2026-02&category=salary&scope=month",
            "Kategorien findes ikke i disse tal.",
        ),
        (
            f"/category?{PINNED}&month=2026-06&category=groceries&scope=month",
            "Den valgte måned ligger uden for de måneder, der kan vælges.",
        ),
        (
            (
                "/category?publication=9&reference_date=2026-05-14"
                f"&account={CURRENT}&month=2026-02&category=groceries&scope=month"
            ),
            "Disse tal findes ikke længere.",
        ),
    ],
)
def test_a_detail_that_cannot_be_shown_says_why_in_danish(
    client: TestClient, address: str, said: str
) -> None:
    response = client.get(address)
    page = read(response.text)

    assert response.status_code == 200
    assert said in (page.text_of("detail-failure") or "")
    assert page.text_of("detail-spending") is None


def test_a_detail_without_data_shows_its_figure_as_unknown_and_no_rows(
    client: TestClient,
) -> None:
    # June on reference date 2026-06-03: both accounts' June is no_data.
    response = client.get(
        "/category?publication=1&reference_date=2026-06-03"
        f"&account={CURRENT}&account={SAVINGS}&month=2026-06"
        "&category=groceries&scope=month"
    )
    june = read(response.text)

    assert (june.text_of("detail-spending"), june.text_of("detail-rows")) == (
        "Ingen data endnu",
        "Dato Tekst Konto Beløb",
    )


def test_a_year_to_date_detail_is_headed_with_its_whole_period(
    client: TestClient,
) -> None:
    # The year to date through February covers January and February.
    year = detail(client, "2026-02", "category=groceries&scope=year_to_date")

    assert year.text_of("detail-title") == "Groceries, januar\N{EN DASH}februar 2026"


def test_a_detail_of_a_superseded_publication_offers_the_newer_figures(
    tmp_path: Path,
) -> None:
    # Publication 2 is current, so a detail pinned to 1 says newer figures exist.
    older = read(
        logged_in(tmp_path, publications=2)
        .get(f"/category?{PINNED}&month=2026-02&category=groceries&scope=month")
        .text
    )

    assert (
        older.text_of("newer-figures"),
        older.attributes("newer-figures").get("href"),
        older.text_of("detail-spending"),
    ) == ("Hent de nyeste tal", "/", "520,00 kr.")


@pytest.mark.parametrize(
    "subject",
    ["", "&category=groceries&group=food"],
    ids=["neither", "both"],
)
def test_a_detail_address_must_name_exactly_one_category_or_group(
    client: TestClient, subject: str
) -> None:
    response = client.get(f"/category?{PINNED}&month=2026-02{subject}&scope=month")

    assert response.status_code == 400
    assert read(response.text).text_of("detail-spending") is None


def test_two_accounts_sharing_a_name_keep_their_own_incomplete_months(
    tmp_path: Path,
) -> None:
    # Both accounts are called "Joint current": each still lists its own months.
    same_name = replace(
        RECORDS,
        accounts=tuple(
            replace(account, display_name="Joint current")
            for account in RECORDS.accounts
        ),
    )
    year = read(
        logged_in(tmp_path, records=same_name)
        .get(f"/category?{PINNED}&month=2026-02&category=groceries&scope=year_to_date")
        .text
    )

    assert year.text_of("coverage-note") == (
        "Tallene mangler noget fra Joint current (januar 2026, februar 2026)"
        " og Joint current (januar 2026)."
    )


def test_a_detail_with_no_accounts_selected_asks_for_one(client: TestClient) -> None:
    response = client.get(
        f"/category?publication=1&reference_date={REFERENCE_DATE}"
        "&month=2026-02&category=groceries&scope=month"
    )

    assert "Vælg mindst én konto." in (
        read(response.text).text_of("detail-failure") or ""
    )
