# Copyright 2026 Therkel
"""`budget migrate` in production: a verified backup set first, always.

Each production profile here is a synthetic profile file in a temporary
folder, whose stores, inputs and backups stay inside it. No test opens a real
production store. Every test passes `main` an explicit environment.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import complete_backup_sets
from budget.bronze import BronzeStore
from budget.profiles import load_profile_file
from tests.backups.sets import manifest, run_ids
from tests.cli.commands import migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class NewProductionStoreTests(unittest.TestCase):
    def test_a_new_store_is_started_only_when_asked_and_then_backed_up(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")

            status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "--new-store" in stderr
            assert not (folder / "stores").exists()
            assert not (folder / "backups").exists()

            status, stderr = migrate(profile_file, "--new-store")

            assert (status, stderr) == (EXIT_OK, "")
            production = load_profile_file(profile_file)
            with BronzeStore(production):
                pass
            (backup,) = complete_backup_sets(production)
            assert run_ids(backup.path / "bronze.db") == []
            assert manifest(backup.path)["profile"] == "production"


if __name__ == "__main__":
    unittest.main()
