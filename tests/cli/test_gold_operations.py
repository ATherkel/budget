# Copyright 2026 Therkel
"""Operating a production profile with Gold: import, publish, back up, and again.

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
from tests.cli.imports import clean_git, write_ranges
from tests.cli.profile_files import write_profile
from tests.gold.publishing import RECIPE, publication
from tests.gold.worked_silver import TAXONOMY
from tests.importing.households import ACCOUNTS, drop, log_entries, payload

EXIT_OK = 0


def _import(profile_file: Path, start: str, end: str) -> tuple[int, str, str]:
    """Run `budget import` over one declared range, from committed code."""
    ranges = write_ranges(profile_file.parent, default=(start, end))
    with mock.patch("subprocess.run", return_value=clean_git()):
        return import_(profile_file, "--ranges", str(ranges))


def _build_and_publish(profile: Profile, publication_id: int) -> None:
    """Build Gold from the stored Silver result and publish it as current."""
    configuration = ConfigurationSnapshot(
        accounts=load_accounts(profile), taxonomy=TAXONOMY, rules={}
    )
    with SilverStore(profile) as silver:
        result = build(
            silver=silver.read(),
            configuration=configuration,
            decisions=(),
            publication=publication(publication_id),
            late_booking_window=timedelta(days=7),
        )
    recipe = replace(RECIPE, configuration_fingerprint=configuration.fingerprint)
    with writer_lock(profile), GoldStore(profile) as gold:
        gold.publish(result, recipe, configuration)


class GoldOperationsTests(unittest.TestCase):
    def test_a_profile_with_gold_imports_publishes_backs_up_and_does_it_again(
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
            first = _import(profile_file, "2026-03-01", "2026-03-04")
            assert first[0::2] == (EXIT_OK, "")
            _build_and_publish(profile, 1)

            status, _, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            published = complete_backup_sets(profile)[0]
            assert gold_publications(published.path / "gold.db") == [1]
            drop(profile, "joint-current", "danske-20260310.csv", payload("08.03.2026"))

            again = _import(profile_file, "2026-03-05", "2026-03-09")

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
            assert len(logged) == 2
            assert sorted(run_ids(newest.path / "bronze.db")) == logged
            _build_and_publish(profile, 2)

            status, _, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            rebuilt = complete_backup_sets(profile)[0]
            assert gold_publications(rebuilt.path / "gold.db") == [1, 2]
            with GoldStore(profile) as gold:
                current = gold.current()
            assert current is not None
            assert current.publication_id == 2


if __name__ == "__main__":
    unittest.main()
