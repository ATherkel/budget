# Copyright 2026 Therkel
"""`budget rebuild --from silver`: rebuild Silver from the profile's Bronze.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. The Bronze inputs are real: the test
seeds them through the documented `import_inbox_file` operation, because the
`import` command does not exist yet.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0


def _migrated_profile_with_accounts(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _import_one_export(profile: Profile) -> None:
    """Seed Bronze with one stored import run, as `budget import` will."""
    source = drop(
        profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
    )
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )


class RebuildFromSilverTests(unittest.TestCase):
    def test_rebuild_from_silver_stores_the_result_from_bronze(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _migrated_profile_with_accounts(profile_file, folder)
            _import_one_export(profile)

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_OK
            assert stderr == ""
            with SilverStore(profile) as store:
                result = store.read()
            assert [(t.account_id, t.description) for t in result.transactions] == [
                ("joint-current", "Café")
            ]
            assert [r.status for r in result.import_run_results] == ["accepted"]
            assert "1 admitted" in stdout


if __name__ == "__main__":
    unittest.main()
