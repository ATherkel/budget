# Copyright 2026 Therkel
"""The view-state controls: the month, mode and account pickers, as a feature.

The dashboard is driven in-process with its default features.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from tests.dashboard.households import dashboard_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
SELECTION_SHEET = re.compile(
    r'<link rel="stylesheet" href="(/static/view_state/selection\.css\?v=[0-9a-f]+)">'
)


def test_every_page_links_the_selection_stylesheet_the_dashboard_serves(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(dashboard_profile(tmp_path), clock=lambda: NOW))

    linked = SELECTION_SHEET.findall(client.get("/login").text)
    served = [client.get(address) for address in linked]

    assert [(sheet.status_code, "#selection {" in sheet.text) for sheet in served] == [
        (200, True)
    ]
