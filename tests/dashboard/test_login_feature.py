# Copyright 2026 Therkel
"""Logging in and out as a feature: served only while it is registered.

The dashboard is driven in-process.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features.report import REPORT
from budget.dashboard.features.view_state import VIEW_STATE
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
LOGIN_SHEET = re.compile(
    r'<link rel="stylesheet" href="(/static/login/login\.css\?v=[0-9a-f]+)">'
)


def test_a_dashboard_without_the_login_feature_serves_no_login_or_logout(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(VIEW_STATE,)
    )
    client = TestClient(app, follow_redirects=False)

    assert (
        client.get("/login").status_code,
        client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE}).status_code,
        client.post("/logout").status_code,
    ) == (404, 404, 404)


def test_a_dashboard_without_the_login_feature_still_refuses_every_page(
    tmp_path: Path,
) -> None:
    app = create_app(
        dashboard_profile(tmp_path), clock=lambda: NOW, features=(VIEW_STATE, REPORT)
    )
    client = TestClient(app, follow_redirects=False)
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get(
        "/report",
        params={"publication": 1, "reference_date": "2026-05-14", "month": "2026-05"},
    )

    assert (response.status_code, response.headers.get("location")) == (
        303,
        "/login",
    )


def test_the_login_page_links_the_login_stylesheet_the_dashboard_serves(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(dashboard_profile(tmp_path), clock=lambda: NOW))

    linked = LOGIN_SHEET.findall(client.get("/login").text)
    served = [client.get(address) for address in linked]

    assert [
        (sheet.status_code, ".login-layout {" in sheet.text) for sheet in served
    ] == [(200, True)]
