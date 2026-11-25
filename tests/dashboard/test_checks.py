# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the selection's trust diagnostics.

The dashboard is driven in-process over the synthetic worked example.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult, ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Page, read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

KONTROL = {
    "publication": "1",
    "reference_date": "2026-05-14",
    "account": [CURRENT, SAVINGS],
    "month": "2026-03",
    "mode": "advanced",
    "tab": "checks",
}


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303
    return client


def kontrol(client: TestClient, **changes: object) -> Page:
    """Return the Kontrol fragment for the worked example, with `changes`."""
    return read(
        client.get(
            "/report",
            params={**KONTROL, **changes},
            headers={"HX-Request": "true"},
        ).text
    )


def test_avanceret_tab_bar_links_kontrol_and_marks_it_current_there(
    client: TestClient,
) -> None:
    overview = kontrol(client, tab="overview")
    checks = kontrol(client)
    link = parse_qs(urlsplit(overview.attributes("tab-checks").get("href", "")).query)

    assert (
        overview.text_of("tab-checks"),
        overview.attributes("tab-checks").get("aria-current"),
        link.get("tab"),
        link.get("account"),
        link.get("month"),
        checks.attributes("tab-checks").get("aria-current"),
        checks.attributes("tab-overview").get("aria-current"),
    ) == ("Kontrol", None, ["checks"], [CURRENT, SAVINGS], ["2026-03"], "page", None)


def test_kontrol_shows_the_selections_coverage(client: TestClient) -> None:
    # March lacks part of Joint current; April is fully covered for both.
    assert (
        kontrol(client).text_of("checks-coverage"),
        kontrol(client, month="2026-04").text_of("checks-coverage"),
    ) == ("Dækning: delvist dækket.", "Dækning: fuldt dækket.")


def test_kontrol_lists_each_incomplete_account_month(client: TestClient) -> None:
    # March lacks part of Joint current only; April lacks nothing.
    assert (
        kontrol(client).text_of("checks-incomplete-months"),
        kontrol(client, month="2026-04").text_of("checks-incomplete-months"),
    ) == (
        "Joint current, marts 2026: delvist dækket.",
        "Ingen valgte kontomåneder mangler dækning.",
    )


def test_kontrol_names_each_reason_the_figures_are_provisional(
    profile: Profile,
    client: TestClient,
) -> None:
    # Publication 2 leaves Joint current's April late bookings unsettled.
    april = ReportingMonth(2026, 4)
    unsettled = tuple(
        replace(snapshot, late_bookings_settled=False)
        if snapshot.account_id == CURRENT and snapshot.month == april
        else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                replace(RECORDS, monthly_balances=unsettled),
            ),
            RECIPE,
            CONFIGURATION,
        )

    assert (
        kontrol(client, month="2026-05").text_of("checks-provisional"),
        kontrol(client, publication="2", month="2026-04").text_of(
            "checks-provisional"
        ),
        kontrol(client, month="2026-04").text_of("checks-provisional"),
    ) == (
        "Foreløbigt: maj 2026 er indeværende måned, så der kan stadig komme "
        "posteringer. Sene bogføringer kan stadig komme fra Joint current og "
        "Joint savings.",
        "Foreløbigt: Sene bogføringer kan stadig komme fra Joint current.",
        None,
    )


def test_changing_account_or_month_inside_kontrol_stays_on_kontrol(
    client: TestClient,
) -> None:
    changed = client.get(
        "/report",
        params={
            **KONTROL,
            "account": [CURRENT],
            "month": "2026-04",
            "active_mode": "advanced",
        },
        headers={"HX-Request": "true"},
    )
    fragment = read(changed.text)
    pushed = changed.headers["hx-push-url"]
    restored = read(client.get(pushed).text)

    assert (
        fragment.attributes("report").get("data-tab"),
        fragment.hidden("tab"),
        parse_qs(urlsplit(pushed).query),
        restored.attributes("report").get("data-tab"),
        restored.hidden("tab"),
    ) == (
        "checks",
        "checks",
        {
            "publication": ["1"],
            "reference_date": ["2026-05-14"],
            "account": [CURRENT],
            "month": ["2026-04"],
            "mode": ["advanced"],
            "tab": ["checks"],
            "comparison": ["amounts"],
        },
        "checks",
        "checks",
    )
