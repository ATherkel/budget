# Copyright 2026 Therkel
"""The report as a feature: served only while it is registered.

The dashboard is driven in-process.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.login import LOGIN
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
REPORT_SHEET = re.compile(
    r'<link rel="stylesheet" href="(/static/report/report\.css\?v=[0-9a-f]+)">'
)


def test_a_dashboard_without_the_report_feature_serves_no_report(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(LOGIN, VIEW_STATE)
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get(
        "/report",
        params={"publication": 1, "reference_date": "2026-05-14", "month": "2026-05"},
    )

    assert response.status_code == 404


def test_a_page_links_the_report_stylesheet_the_dashboard_serves(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(dashboard_profile(tmp_path), clock=lambda: NOW))

    linked = REPORT_SHEET.findall(client.get("/login").text)
    served = [client.get(address) for address in linked]

    assert [
        (sheet.status_code, ".account-activity {" in sheet.text) for sheet in served
    ] == [(200, True)]
