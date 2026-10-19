# Copyright 2026 Therkel
"""Dashboard access: one household passphrase guards every page and fragment.

The rules are `operations.md` "Dashboard Access" and the #103 decisions. The
app is built from a test profile whose passphrase is set, and driven
in-process; nothing is served.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app, set_passphrase
from budget.gold.storage import migrate_gold
from budget.profiles import test_profile as make_test_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
HOUSEHOLD_PHRASE = "correct horse battery staple"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = replace(
        make_test_profile(tmp_path),
        passphrase_file=tmp_path / "dashboard-passphrase",
    )
    migrate_gold(profile)
    set_passphrase(profile, HOUSEHOLD_PHRASE)
    return TestClient(create_app(profile, clock=lambda: NOW), follow_redirects=False)


def test_a_page_requested_without_logging_in_is_sent_to_the_login_page(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert (response.status_code, response.headers.get("location")) == (
        303,
        "/login",
    )


def test_the_household_passphrase_logs_in_with_a_private_session_cookie(
    client: TestClient,
) -> None:
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    overview = client.get("/")

    # One cookie, the session's, carrying both flags.
    flags = [
        ("httponly" in cookie.lower(), "samesite=strict" in cookie.lower())
        for cookie in login.headers.get_list("set-cookie")
    ]
    assert (
        login.status_code,
        login.headers.get("location"),
        flags,
        overview.status_code,
    ) == (303, "/", [(True, True)], 200)


def test_a_wrong_passphrase_is_refused_without_a_session(client: TestClient) -> None:
    login = client.post("/login", data={"passphrase": "correct horse battery"})
    overview = client.get("/")

    # The form again, saying why, so the reader can retry. A form login uses
    # no HTTP authentication scheme, so the refusal is not a 401.
    assert (
        login.status_code,
        "Adgangsfrasen er forkert" in login.text,
        'name="passphrase"' in login.text,
        login.headers.get_list("set-cookie"),
        overview.status_code,
    ) == (200, True, True, [], 303)
