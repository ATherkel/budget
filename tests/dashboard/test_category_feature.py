# Copyright 2026 Therkel
"""The category page as a feature: served only while it is registered.

The dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.login import LOGIN
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def test_a_dashboard_without_the_category_feature_serves_no_category_page(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(LOGIN, VIEW_STATE)
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get(
        "/category",
        params={
            "publication": 1,
            "reference_date": "2026-05-14",
            "month": "2026-05",
            "category": "groceries",
        },
    )

    assert response.status_code == 404
