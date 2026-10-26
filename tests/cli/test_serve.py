# Copyright 2026 Therkel
"""`budget serve`: the refusals that come before the dashboard starts.

Starting a real server is checked by hand; these tests only reach the
refusals, so nothing is ever served. The profile files are synthetic.
"""

from pathlib import Path

from budget.gold.storage import migrate_gold
from budget.profiles import load_profile_file
from tests.cli.commands import serve
from tests.cli.profile_files import write_profile


def test_serve_refuses_a_profile_whose_passphrase_was_never_set(
    tmp_path: Path,
) -> None:
    # Everything else is in place: the file is named and Gold is migrated.
    profile_file = write_profile(tmp_path)
    passphrase_file = tmp_path / "secrets" / "dashboard-passphrase"
    with profile_file.open("a", encoding="utf-8") as file:
        file.write(
            f"\n[dashboard]\npassphrase_file = '{passphrase_file}'\n"
            'bind = "127.0.0.1"\nport = 8750\n'
        )
    migrate_gold(load_profile_file(profile_file))

    status, _, stderr = serve(profile_file)

    # A refused environment, with the command that puts it right.
    assert (status, "run `budget set-passphrase`" in stderr) == (4, True)
