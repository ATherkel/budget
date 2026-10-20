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
