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
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.sqlstore import StoreNotFoundError

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
def profile(tmp_path: Path) -> Profile:
    profile = replace(
        make_test_profile(tmp_path),
        passphrase_file=tmp_path / "dashboard-passphrase",
    )
    migrate_gold(profile)
    set_passphrase(profile, HOUSEHOLD_PHRASE)
    return profile


@pytest.fixture
def client(profile: Profile, clock: Clock) -> TestClient:
    return TestClient(create_app(profile, clock=clock), follow_redirects=False)


def log_in(client: TestClient) -> None:
    response = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert (response.status_code, response.headers.get("location")) == (303, "/"), (
        "the household passphrase did not log in"
    )


def test_the_dashboard_refuses_a_profile_whose_gold_store_is_missing(
    tmp_path: Path,
) -> None:
    # Gold never migrated: the dashboard must not start and fail on each page.
    unmigrated = replace(
        make_test_profile(tmp_path),
        passphrase_file=tmp_path / "dashboard-passphrase",
    )
    set_passphrase(unmigrated, HOUSEHOLD_PHRASE)

    with pytest.raises(StoreNotFoundError, match="gold"):
        create_app(unmigrated, clock=Clock())


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


def test_a_session_cookie_with_letters_outside_ascii_is_refused_not_an_error(
    client: TestClient,
) -> None:
    # Cookie unquoting can hand the dashboard any text; refusing it keeps
    # that browser able to log in again instead of failing on every page.
    client.cookies.set("session", '"9999999999.\\346"')
    response = client.get("/")

    assert (response.status_code, response.headers.get("location")) == (
        303,
        "/login",
    )


def test_the_login_page_a_reader_is_sent_to_asks_for_the_passphrase(
    client: TestClient,
) -> None:
    # Every guarded page redirects here, so it must answer, not 405.
    response = client.get("/login")

    assert (response.status_code, 'name="passphrase"' in response.text) == (
        200,
        True,
    )


def test_the_browser_keeps_a_login_for_30_days_not_until_it_closes(
    client: TestClient,
) -> None:
    # A cookie without a lifetime dies with the browser; a restart would
    # ask for the passphrase long before 30 days of disuse.
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    assert [
        "max-age=2592000" in cookie.lower()
        for cookie in login.headers.get_list("set-cookie")
    ] == [True]


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


def test_five_failed_logins_in_a_row_lock_login_for_30_seconds(
    client: TestClient, clock: Clock
) -> None:
    def attempt(passphrase: str) -> int:
        return client.post("/login", data={"passphrase": passphrase}).status_code

    refused = [attempt("wrong guess") for _ in range(5)]
    locked = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    clock.now += timedelta(seconds=29)
    still_locked = attempt(HOUSEHOLD_PHRASE)
    clock.now += timedelta(seconds=1)

    # Even the right passphrase waits out the lock, and the reader is told so.
    assert (
        refused,
        locked.status_code,
        locked.headers.get("retry-after"),
        "Prøv igen om 30 sekunder" in locked.text,
        still_locked,
        attempt(HOUSEHOLD_PHRASE),
    ) == ([200] * 5, 429, "30", True, 429, 303)


def test_each_further_lock_doubles_its_wait_up_to_15_minutes(
    client: TestClient, clock: Clock
) -> None:
    waits = []
    for _ in range(7):
        for _ in range(5):
            client.post("/login", data={"passphrase": "wrong guess"})
        locked = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
        wait = int(locked.headers.get("retry-after", "0"))
        waits.append(wait)
        clock.now += timedelta(seconds=wait)

    assert waits == [30, 60, 120, 240, 480, 900, 900]


def test_a_successful_login_resets_the_failures_and_the_doubling(
    client: TestClient, clock: Clock
) -> None:
    def fail(times: int) -> None:
        for _ in range(times):
            client.post("/login", data={"passphrase": "wrong guess"})

    def wait_after_five_failures() -> int:
        fail(5)
        locked = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
        return int(locked.headers.get("retry-after", "0"))

    # Four failures, a login, four more: never five in a row.
    fail(4)
    log_in(client)
    fail(4)
    not_locked = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    first_wait = wait_after_five_failures()
    clock.now += timedelta(seconds=first_wait)
    log_in(client)
    # After a login, the next lock starts again at 30 seconds, not 60.
    next_wait = wait_after_five_failures()

    assert (not_locked.status_code, first_wait, next_wait) == (303, 30, 30)


def test_setting_a_new_passphrase_logs_out_every_device(
    client: TestClient, profile: Profile
) -> None:
    log_in(client)
    set_passphrase(profile, "a new household phrase")
    logged_out = client.get("/")
    # Logged out because the passphrase changed, not because the file broke.
    again = client.post("/login", data={"passphrase": "a new household phrase"})

    assert (logged_out.status_code, again.status_code) == (303, 303)
