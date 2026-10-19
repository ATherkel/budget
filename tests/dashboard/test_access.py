# Copyright 2026 Therkel
"""Dashboard access: one household passphrase guards every page and fragment.

The rules are `operations.md` "Dashboard Access" and the #103 decisions. The
app is built from a test profile whose passphrase is set, and driven
in-process; nothing is served.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app, set_passphrase
from budget.gold.storage import migrate_gold
from budget.profiles import test_profile as make_test_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
HOUSEHOLD_PHRASE = "correct horse battery staple"


class Clock:
    """The time the dashboard is told; a test moves it forward."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(tmp_path: Path, clock: Clock) -> TestClient:
    profile = replace(
        make_test_profile(tmp_path),
        passphrase_file=tmp_path / "dashboard-passphrase",
    )
    migrate_gold(profile)
    set_passphrase(profile, HOUSEHOLD_PHRASE)
    return TestClient(create_app(profile, clock=clock), follow_redirects=False)


def log_in(client: TestClient) -> None:
    response = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert (response.status_code, response.headers.get("location")) == (303, "/"), (
        "the household passphrase did not log in"
    )


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


def test_a_session_cookie_the_dashboard_did_not_issue_is_refused(
    client: TestClient,
) -> None:
    issued = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE}).cookies[
        "session"
    ]
    # The issued value with its first character changed, and one made up. The
    # first character is never encoding padding, so every edit to it counts.
    edited = ("0" if issued[0] != "0" else "1") + issued[1:]
    refused = []
    for forged in (edited, "1"):
        client.cookies.set("session", forged)
        response = client.get("/")
        refused.append((response.status_code, response.headers.get("location")))

    assert refused == [(303, "/login"), (303, "/login")]


def test_a_fragment_requested_without_logging_in_is_refused_not_redirected(
    client: TestClient,
) -> None:
    # htmx marks its requests; a redirect would paint the login page into a panel.
    # HX-Redirect sends the whole page to login instead, since htmx swaps no 401.
    response = client.get("/", headers={"HX-Request": "true"})

    assert (
        response.status_code,
        response.headers.get("location"),
        response.headers.get("hx-redirect"),
    ) == (401, None, "/login")


def test_a_login_unused_for_30_days_asks_for_the_passphrase_again(
    client: TestClient, clock: Clock
) -> None:
    log_in(client)
    clock.now += timedelta(days=30, seconds=1)
    lapsed = client.get("/")

    log_in(client)
    clock.now += timedelta(days=30, seconds=-1)
    kept = client.get("/")

    assert (lapsed.status_code, kept.status_code) == (303, 200)


def test_each_visit_renews_the_login_for_30_days_from_that_visit(
    client: TestClient, clock: Clock
) -> None:
    log_in(client)
    clock.now += timedelta(days=1)
    client.get("/")
    # 31 days after logging in, just under 30 since the visit that renewed it.
    clock.now += timedelta(days=30, seconds=-1)
    kept = client.get("/")
    # Just over 30 days after that visit: renewals do not add up.
    clock.now += timedelta(days=30, seconds=1)
    lapsed = client.get("/")

    assert (kept.status_code, lapsed.status_code) == (200, 303)


def test_logging_out_ends_the_login_in_this_browser(client: TestClient) -> None:
    log_in(client)
    logout = client.post("/logout")
    after = client.get("/")

    assert (
        logout.status_code,
        logout.headers.get("location"),
        after.status_code,
    ) == (303, "/login", 303)
