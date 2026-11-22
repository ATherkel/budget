# Copyright 2026 Therkel
"""Dashboard features: a feature folder plugs in with one line in `create_app`.

A sample feature in `sample_feature/` stands in for a real one; the dashboard
is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features import Feature
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.dashboard.sample_feature import SAMPLE

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def logged_in(tmp_path: Path, features: tuple[Feature, ...]) -> TestClient:
    """Return a logged-in client of a dashboard with `features` registered."""
    app = create_app(dashboard_profile(tmp_path), clock=lambda: NOW, features=features)
    client = TestClient(app, follow_redirects=False)
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def test_a_registered_feature_serves_its_page(tmp_path: Path) -> None:
    client = logged_in(tmp_path, (SAMPLE,))

    response = client.get("/sample")

    assert (response.status_code, read(response.text).text_of("sample-heading")) == (
        200,
        "Sample feature",
    )
