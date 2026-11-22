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
from tests.gold.worked_example import PUBLICATION, RECORDS

# The worked examples' reference date: May is the current month.
NOW = datetime(2026, 5, 14, 10, tzinfo=UTC)


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
