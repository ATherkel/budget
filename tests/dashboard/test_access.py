# Copyright 2026 Therkel
"""Dashboard access: one household passphrase guards every page and fragment.

The rules are `operations.md` "Dashboard Access" and the #103 decisions. The
app is built from a test profile and driven in-process; nothing is served.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold.storage import migrate_gold
from budget.profiles import test_profile as make_test_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = make_test_profile(tmp_path)
    migrate_gold(profile)
    return TestClient(create_app(profile, clock=lambda: NOW), follow_redirects=False)


def test_a_page_requested_without_logging_in_is_sent_to_the_login_page(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert (response.status_code, response.headers.get("location")) == (
        303,
        "/login",
    )
