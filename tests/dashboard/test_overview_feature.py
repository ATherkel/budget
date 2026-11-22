# Copyright 2026 Therkel
"""The overview page as a feature: served only while it is registered.

The dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def test_a_dashboard_without_the_overview_feature_serves_no_overview(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(VIEW_STATE,)
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    assert client.get("/").status_code == 404
