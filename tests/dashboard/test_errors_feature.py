# Copyright 2026 Therkel
"""The error pages as a feature: explained in Danish only while it is registered.

The dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.login import LOGIN
from budget.dashboard.features.report import REPORT
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


def test_a_dashboard_without_the_errors_feature_answers_a_bad_address_as_fastapi(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path),
        clock=lambda: NOW,
        features=(LOGIN, VIEW_STATE, REPORT),
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get("/report", params={"publication": "not-a-number"})

    assert (response.status_code, response.headers["content-type"]) == (
        422,
        "application/json",
    )
