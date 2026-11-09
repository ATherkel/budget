# Copyright 2026 Therkel
"""Operating a production profile with Gold: import, publish, back up, and again.

The profile is a synthetic production profile file in a temporary folder.
`migrate`, `import` and `backup` run through the command line, and `import`
builds and publishes Gold itself. Every account, date, text and amount is
synthetic.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import complete_backup_sets
from budget.gold.store import GoldStore
from budget.profiles import load_profile_file
from tests.backups.sets import gold_publications, manifest, run_ids
from tests.cli.commands import backup, import_, migrate
from tests.cli.imports import clean_checkout, write_ranges
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import write_profile
from tests.gold.invariants import assert_contract_invariants
from tests.importing.households import drop, log_entries, payload

EXIT_OK = 0


def _import(profile_file: Path, start: str, end: str) -> tuple[int, str, str]:
    """Run `budget import` over one declared range, from committed code."""
    ranges = write_ranges(profile_file.parent, default=(start, end))
    with mock.patch("subprocess.run", side_effect=clean_checkout):
        return import_(profile_file, "--ranges", str(ranges))


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
            write_inputs(profile)
            drop(profile, "joint-current", "danske-20260305.csv", payload("01.03.2026"))
            first = _import(profile_file, "2026-03-01", "2026-03-04")
            assert first[0::2] == (EXIT_OK, "")

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
            assert gold_publications(newest.path / "gold.db") == [1, 2]
            logged = sorted(
                str(entry["import_run_id"]) for entry in log_entries(profile)
            )
            assert len(logged) == 2
            assert sorted(run_ids(newest.path / "bronze.db")) == logged

            status, _, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            rebuilt = complete_backup_sets(profile)[0]
            assert gold_publications(rebuilt.path / "gold.db") == [1, 2]
            with GoldStore(profile) as gold:
                current = gold.current()
                assert current is not None
                # What the import published, read back as a consumer reads it.
                for publication in gold.available():
                    assert_contract_invariants(gold.open(publication.publication_id))
            assert current.publication_id == 2


if __name__ == "__main__":
    unittest.main()
