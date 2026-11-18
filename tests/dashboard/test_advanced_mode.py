# Copyright 2026 Therkel
"""The Enkel and Avanceret display contract."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(create_app(profile, clock=lambda: PUBLICATION.known_at))
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


def test_fresh_visit_has_an_accessible_mode_control_and_amounts_default(
    client: TestClient,
) -> None:
    html = client.get("/").text
    page = read(html)

    assert (
        page.attributes("mode-control").get("role"),
        page.checked("mode"),
        page.hidden("comparison"),
        page.text_of("comparison-choice"),
        "Avanceret" in page.visible(),
        0 <= html.find('id="mode-control"') < html.find('class="account-fieldset"'),
    ) == ("group", {"simple"}, "amounts", "Beløb", True, True)


def test_advanced_details_show_dated_balances_separately_from_month_snapshot(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            "publication": "1",
            "reference_date": "2026-05-14",
            "account": "joint-current",
            "month": "2026-04",
            "mode": "advanced",
            "active_mode": "advanced",
            "tab": "details",
        },
        headers={"HX-Request": "true"},
    )
    page = read(response.text)

    assert (
        page.attributes("report").get("data-tab"),
        page.text_of("activity-dated-balance-joint-current"),
        page.text_of("activity-earlier-observation-joint-current"),
        page.text_of("activity-monthly-snapshot-joint-current"),
        page.text_of("activity-evidence-joint-current"),
    ) == (
        "details",
        "52.087,50 kr. den 24.04.2026",
        "35.587,50 kr. den 20.03.2026",
        ("Månedssnapshot: Åbning 35.587,50 kr.; lukning 52.087,50 kr.; fuldt dækket."),
        "Gennem 08.05.2026",
    )
