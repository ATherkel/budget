# Copyright 2026 Therkel
"""`budget backup`: write one backup set of production by hand.

Each profile here is a synthetic profile file in a temporary folder. Every
test passes `main` an explicit environment.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import complete_backup_sets
from budget.profiles import load_profile_file
from tests.cli.commands import backup, migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class BackupCommandTests(unittest.TestCase):
    def test_backup_writes_a_set_of_production_and_names_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            status, stdout, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            newest, _ = complete_backup_sets(production)
            assert stdout == f"backup set {newest.name} written\n"

    def test_backup_is_refused_for_a_profile_that_writes_no_sets(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory))
            assert migrate(profile_file)[0] == EXIT_OK

            status, stdout, stderr = backup(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "writes no backup sets" in stderr

    def test_backup_is_refused_where_production_has_no_store(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _, stderr = backup(write_profile(folder, name="production"))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Bronze store" in stderr
            assert not (folder / "backups").exists()


if __name__ == "__main__":
    unittest.main()
