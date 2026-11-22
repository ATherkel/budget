# Copyright 2026 Therkel
"""Every dashboard page and error page, pinned as the HTML it renders.

The dashboard's refactor moves pages without changing them, so each page's
HTML is pinned here and must stay identical. The household's Gold holds the
synthetic worked example; the dashboard is driven in-process at a fixed time.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.snapshot import assert_matches_snapshot
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

# The worked examples' reference date: May is the current month.
NOW = datetime(2026, 5, 14, 10, tzinfo=UTC)

PINNED = f"publication=1&reference_date=2026-05-14&account={CURRENT}&account={SAVINGS}"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(create_app(profile, clock=lambda: NOW), follow_redirects=False)
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def test_the_overview_of_a_fresh_visit_is_unchanged(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert_matches_snapshot("overview", response.text)


ADVANCED = "&mode=advanced&tab=details&comparison=amounts"


@pytest.mark.parametrize(
    ("name", "address"),
    [
        pytest.param(name, address, id=name)
        for name, address in (
            ("overview-advanced-details", f"/?{PINNED}&month=2026-02{ADVANCED}"),
            ("category-month", f"/category?{PINNED}&month=2026-02&category=groceries"),
            (
                "group-year-to-date",
                f"/category?{PINNED}&month=2026-04&group=housing&scope=year_to_date",
            ),
            ("explanation", f"/explanation?{PINNED}&month=2026-02"),
        )
    ],
)
def test_each_page_a_reader_opens_is_unchanged(
    client: TestClient, name: str, address: str
) -> None:
    response = client.get(address)

    assert response.status_code == 200
    assert_matches_snapshot(name, response.text)


@pytest.mark.parametrize(
    ("name", "query"),
    [
        pytest.param(name, query, id=name)
        for name, query in (
            ("report", f"{PINNED}&month=2026-02"),
            (
                "report-advanced-details",
                f"{PINNED}&month=2026-02{ADVANCED}&active_mode=advanced",
            ),
            (
                "report-no-accounts",
                "publication=1&reference_date=2026-05-14&month=2026-02",
            ),
        )
    ],
)
def test_each_report_fragment_a_selection_swaps_in_is_unchanged(
    client: TestClient, name: str, query: str
) -> None:
    response = client.get(f"/report?{query}", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert_matches_snapshot(name, response.text)


def test_the_login_page_is_unchanged(tmp_path: Path) -> None:
    profile = dashboard_profile(tmp_path)
    client = TestClient(create_app(profile, clock=lambda: NOW))
    response = client.get("/login")

    assert response.status_code == 200
    assert_matches_snapshot("login", response.text)


def test_the_login_page_refusing_a_wrong_passphrase_is_unchanged(
    tmp_path: Path,
) -> None:
    profile = dashboard_profile(tmp_path)
    client = TestClient(create_app(profile, clock=lambda: NOW))
    response = client.post("/login", data={"passphrase": "wrong"})

    assert response.status_code == 200
    assert_matches_snapshot("login-wrong-passphrase", response.text)


def test_the_login_page_of_a_locked_login_is_unchanged(tmp_path: Path) -> None:
    # Five wrong passphrases in a row lock login for 30 seconds.
    profile = dashboard_profile(tmp_path)
    client = TestClient(create_app(profile, clock=lambda: NOW))
    for _ in range(5):
        client.post("/login", data={"passphrase": "wrong"})
    response = client.post("/login", data={"passphrase": "wrong"})

    assert response.status_code == 429
    assert_matches_snapshot("login-locked", response.text)


def test_the_overview_before_anything_is_published_is_unchanged(
    tmp_path: Path,
) -> None:
    profile = dashboard_profile(tmp_path)
    client = TestClient(create_app(profile, clock=lambda: NOW), follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    response = client.get("/")

    assert response.status_code == 200
    assert_matches_snapshot("nothing-published", response.text)


# Publication 9 was never published, so its figures are unavailable.
UNAVAILABLE = f"publication=9&reference_date=2026-05-14&account={CURRENT}&month=2026-02"


@pytest.mark.parametrize(
    ("name", "address", "status"),
    [
        pytest.param(name, address, status, id=name)
        for name, address, status in (
            ("unavailable-page", f"/?{UNAVAILABLE}", 200),
            ("invalid-address-page", "/?publication=first", 400),
            ("category-unavailable", f"/category?{UNAVAILABLE}&category=rent", 200),
            ("explanation-unavailable", f"/explanation?{UNAVAILABLE}", 200),
        )
    ],
)
def test_each_error_page_is_unchanged(
    client: TestClient, name: str, address: str, status: int
) -> None:
    response = client.get(address)

    assert response.status_code == status
    assert_matches_snapshot(name, response.text)


@pytest.mark.parametrize(
    ("name", "query"),
    [
        pytest.param(name, query, id=name)
        for name, query in (
            ("report-unavailable", UNAVAILABLE),
            ("report-invalid-address", "publication=first"),
            (
                "report-invalid-selection",
                "publication=1&reference_date=2026-05-14&account=closed&month=2026-02",
            ),
        )
    ],
)
def test_each_error_fragment_is_unchanged(
    client: TestClient, name: str, query: str
) -> None:
    response = client.get(f"/report?{query}", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert_matches_snapshot(name, response.text)
