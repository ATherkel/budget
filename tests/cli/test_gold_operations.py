# Copyright 2026 Therkel
"""Operating a production profile that has Gold: import, publish, back up, again.

The profile is a synthetic production profile file in a temporary folder.
`migrate`, `import` and `backup` run through the command line; the Gold build
and publish run through the library between them, until `import` builds Gold
itself (#176). Every account, date, text and amount is synthetic.
"""

import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import complete_backup_sets
from budget.gold import build
from budget.gold.store import GoldStore
from budget.inputs import ConfigurationSnapshot, load_accounts
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from budget.silver import SilverStore
from tests.backups.sets import gold_publications, manifest, run_ids
from tests.cli.commands import backup, import_, migrate
from tests.cli.profile_files import write_profile
from tests.gold.publishing import RECIPE
from tests.gold.worked_example import PUBLICATION
from tests.gold.worked_silver import TAXONOMY
from tests.importing.households import ACCOUNTS, drop, log_entries, payload

EXIT_OK = 0


def _clean_git() -> mock.Mock:
    """A finished Git call reporting a clean, tracked checkout."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = ""
    completed.stderr = ""
    return completed


def _import(profile_file: Path, ranges: Path) -> tuple[int, str, str]:
    """Run `budget import` from committed code, as production requires."""
    with mock.patch("subprocess.run", return_value=_clean_git()):
        return import_(profile_file, "--ranges", str(ranges))


def _ranges(folder: Path, start: str, end: str) -> Path:
    """Write a ranges file declaring one default range."""
    path = folder / "ranges.toml"
    path.write_text(
        f"format = 1\n\n[default]\nfrom = {start}\nthrough = {end}\n",
        encoding="utf-8",
    )
    return path


def _build_and_publish(profile: Profile) -> None:
    """Build Gold from the stored Silver result and publish it as current."""
    configuration = ConfigurationSnapshot(
        accounts=load_accounts(profile), taxonomy=TAXONOMY, rules={}
    )
    with SilverStore(profile) as silver:
        result = build(
            silver=silver.read(),
            configuration=configuration,
            decisions=(),
            publication=PUBLICATION,
            late_booking_window=timedelta(days=7),
        )
    recipe = replace(RECIPE, configuration_fingerprint=configuration.fingerprint)
    with writer_lock(profile), GoldStore(profile) as gold:
        gold.publish(result, recipe, configuration)


class GoldOperationsTests(unittest.TestCase):
    def test_a_profile_with_gold_imports_publishes_backs_up_and_imports_again(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
            profile = load_profile_file(profile_file)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            drop(profile, "joint-current", "danske-20260305.csv", payload("01.03.2026"))
            first = _import(profile_file, _ranges(folder, "2026-03-01", "2026-03-04"))
            assert first[0::2] == (EXIT_OK, "")
            _build_and_publish(profile)

            status, _, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            published = complete_backup_sets(profile)[0]
            assert gold_publications(published.path / "gold.db") == [1]
            drop(profile, "joint-current", "danske-20260310.csv", payload("08.03.2026"))

            again = _import(profile_file, _ranges(folder, "2026-03-05", "2026-03-09"))

            assert again[0::2] == (EXIT_OK, "")
            newest = complete_backup_sets(profile)[0]
            assert newest != published
            stores = manifest(newest.path)["stores"]
            assert isinstance(stores, dict)
            assert set(stores) == {"bronze", "silver", "gold"}
            assert gold_publications(newest.path / "gold.db") == [1]
            logged = sorted(
                str(entry["import_run_id"]) for entry in log_entries(profile)
            )
            assert len(logged) == len(("first import", "second import"))
            assert sorted(run_ids(newest.path / "bronze.db")) == logged


if __name__ == "__main__":
    unittest.main()
