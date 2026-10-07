# Copyright 2026 Therkel
"""Editing `accounts.toml` after Bronze and Silver must refuse the rebuild.

The account registry is an input, so it can change after the stores it
described. A rebuild then runs against an account the registry no longer
declares, or a currency the ISO 4217 table does not know, and that is a
configuration error: exit 3, an actionable message naming the file and the
field, no financial value repeated, the previous Silver result kept, and no
finished-command log for a command that failed.
"""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.routine_logging import LOG_FOLDER
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
EXPORT_FILE = "danske-20260305.csv"
BANK_NUMBER = "0012345678"
# A currency value that must never be repeated in a message or a log.
PRIVATE_CURRENCY = "ZZZ-PRIVATE-CURRENCY"
# The same registry with the imported account left out, and otherwise valid.
SAVINGS_ONLY = """\
format = 1

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
"""
# The imported account, with a currency the ISO 4217 table does not know.
UNKNOWN_CURRENCY = f"""\
format = 1

[account.joint-current]
display_name = "Joint current"
account_type = "current"
ownership_scope = "household"
currency = "{PRIVATE_CURRENCY}"
source_format = "danske-csv-v1"
"""
# Nothing a bank said, and no bank account number, may reach the operator.
LEAKED = ("-45,00", "955,00", "Café", "Dagligvarer", BANK_NUMBER)


def _finished_records(profile: Profile) -> list[dict[str, object]]:
    """Every routine log record the profile holds, parsed."""
    folder = profile.stores / LOG_FOLDER
    paths = sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []
    return [
        json.loads(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _built(folder: Path, profile_file: Path) -> Profile:
    """Migrate, import one export and store a nonempty Silver result."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    source = drop(profile, "joint-current", EXPORT_FILE, payload("01.03.2026"))
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )
    assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
    return profile


class RebuildAccountsTests(unittest.TestCase):
    def test_a_missing_imported_account_refuses_the_rebuild(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _built(folder, profile_file)
            with SilverStore(profile) as store:
                before = store.read()
            logged = len(_finished_records(profile))
            profile.accounts_file.write_text(SAVINGS_ONLY, encoding="utf-8")

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert "accounts.toml" in stderr
            assert "joint-current" in stderr
            with SilverStore(profile) as store:
                assert store.read() == before
            assert len(_finished_records(profile)) == logged
            for leaked in LEAKED:
                assert leaked not in stderr
                assert leaked not in stdout

    def test_an_unknown_currency_refuses_without_repeating_it(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _built(folder, profile_file)
            with SilverStore(profile) as store:
                before = store.read()
            logged = len(_finished_records(profile))
            profile.accounts_file.write_text(UNKNOWN_CURRENCY, encoding="utf-8")

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert "accounts.toml" in stderr
            assert "joint-current" in stderr
            assert "currency" in stderr
            with SilverStore(profile) as store:
                assert store.read() == before
            assert len(_finished_records(profile)) == logged
            for leaked in (*LEAKED, PRIVATE_CURRENCY):
                assert leaked not in stderr
                assert leaked not in stdout


if __name__ == "__main__":
    unittest.main()
