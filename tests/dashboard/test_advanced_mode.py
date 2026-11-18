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
