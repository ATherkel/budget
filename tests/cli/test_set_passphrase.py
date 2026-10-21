# Copyright 2026 Therkel
"""`budget set-passphrase`: the household passphrase the dashboard accepts.

`operations.md` "Dashboard Access": the passphrase is stored as a `scrypt`
hash in the profile's passphrase file, and setting a new one logs out every
device. The profile files are synthetic and written into each test's folder.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold.storage import migrate_gold
from budget.profiles import load_profile_file
from tests.cli.commands import set_passphrase
from tests.cli.profile_files import write_profile

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
FIRST = "the first household phrase"
SECOND = "a new household phrase"


def test_the_passphrase_set_last_is_the_one_the_dashboard_accepts(
    tmp_path: Path,
) -> None:
    profile_file = write_profile(tmp_path)
    # The first run creates the file, in a folder that does not exist yet.
    passphrase_file = tmp_path / "secrets" / "dashboard-passphrase"
    with profile_file.open("a", encoding="utf-8") as file:
        file.write(f"\n[dashboard]\npassphrase_file = '{passphrase_file}'\n")
    profile = load_profile_file(profile_file)
    migrate_gold(profile)

    # Each phrase is typed once, then again to confirm.
    runs = [set_passphrase(profile_file, f"{p}\n{p}\n") for p in (FIRST, SECOND)]
    assert [status for status, _, _ in runs] == [0, 0], "set-passphrase did not succeed"
    dashboard = TestClient(create_app(profile, clock=lambda: NOW))

    def log_in(passphrase: str) -> int:
        response = dashboard.post(
            "/login", data={"passphrase": passphrase}, follow_redirects=False
        )
        return response.status_code

    # The latest phrase logs in and the earlier one no longer does, and
    # neither phrase is ever written back to the terminal.
    output = "".join(stdout + stderr for _, stdout, stderr in runs)
    assert (
        [status for status, _, _ in runs],
        log_in(SECOND),
        log_in(FIRST),
        FIRST in output or SECOND in output,
    ) == ([0, 0], 303, 200, False)


def test_a_confirmation_that_does_not_match_changes_nothing(tmp_path: Path) -> None:
    profile_file = write_profile(tmp_path)
    passphrase_file = tmp_path / "secrets" / "dashboard-passphrase"
    with profile_file.open("a", encoding="utf-8") as file:
        file.write(f"\n[dashboard]\npassphrase_file = '{passphrase_file}'\n")
    profile = load_profile_file(profile_file)
    migrate_gold(profile)
    first_status, _, _ = set_passphrase(profile_file, f"{FIRST}\n{FIRST}\n")
    assert first_status == 0, "set-passphrase did not succeed"

    # A typo in the confirmation must not set a phrase nobody knows.
    status, _, stderr = set_passphrase(profile_file, f"{SECOND}\n{SECOND}x\n")
    dashboard = TestClient(create_app(profile, clock=lambda: NOW))
    kept = dashboard.post(
        "/login", data={"passphrase": FIRST}, follow_redirects=False
    ).status_code

    # The refusal says why, without repeating what was typed.
    assert (status, "do not match" in stderr, SECOND in stderr, kept) == (
        3,
        True,
        False,
        303,
    )


def test_an_empty_passphrase_is_refused(tmp_path: Path) -> None:
    profile_file = write_profile(tmp_path)
    passphrase_file = tmp_path / "secrets" / "dashboard-passphrase"
    with profile_file.open("a", encoding="utf-8") as file:
        file.write(f"\n[dashboard]\npassphrase_file = '{passphrase_file}'\n")
    profile = load_profile_file(profile_file)
    migrate_gold(profile)
    first_status, _, _ = set_passphrase(profile_file, f"{FIRST}\n{FIRST}\n")
    assert first_status == 0, "set-passphrase did not succeed"

    # Enter pressed twice: the household would be guarded by nothing.
    status, _, stderr = set_passphrase(profile_file, "\n\n")
    dashboard = TestClient(create_app(profile, clock=lambda: NOW))
    kept = dashboard.post(
        "/login", data={"passphrase": FIRST}, follow_redirects=False
    ).status_code

    assert (status, "empty" in stderr, kept) == (3, True, 303)


def test_a_profile_that_names_no_passphrase_file_is_refused(tmp_path: Path) -> None:
    # No [dashboard] table: there is nowhere to keep the passphrase, and the
    # operator is told before typing it (nothing is piped in to be read).
    profile_file = write_profile(tmp_path)

    status, _, stderr = set_passphrase(profile_file, "")

    assert (status, "passphrase_file" in stderr) == (3, True)


def test_input_that_ends_before_the_confirmation_is_refused(tmp_path: Path) -> None:
    # A closed or empty pipe: a refusal, not a crash.
    profile_file = write_profile(tmp_path)
    passphrase_file = tmp_path / "secrets" / "dashboard-passphrase"
    with profile_file.open("a", encoding="utf-8") as file:
        file.write(f"\n[dashboard]\npassphrase_file = '{passphrase_file}'\n")

    runs = [set_passphrase(profile_file, typed) for typed in ("", f"{FIRST}\n")]

    assert [
        (status, "no passphrase was typed" in stderr) for status, _, stderr in runs
    ] == [(3, True), (3, True)]
