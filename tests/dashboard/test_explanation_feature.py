# Copyright 2026 Therkel
"""The explanation page as a feature: served only while it is registered.

The dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def test_a_dashboard_without_the_explanation_feature_serves_no_explanation_page(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(VIEW_STATE,)
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get(
        "/explanation",
        params={
            "publication": 1,
            "reference_date": "2026-05-14",
            "month": "2026-05",
        },
    )

    assert response.status_code == 404
