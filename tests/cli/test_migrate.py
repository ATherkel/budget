# Copyright 2026 Therkel
"""`budget migrate`: creating and upgrading a profile's Bronze store.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore
from budget.bronze.storage import StoreIdentityError
from budget.cli import main
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.cli.profile_files import write_profile

EXIT_OK = 0


class MigrateTests(unittest.TestCase):
    def test_migrate_creates_the_development_bronze_store(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_OK
            development = Profile(name="development", stores=folder / "stores")
            with BronzeStore(development):
                pass
            with pytest.raises(StoreIdentityError):
                BronzeStore(make_test_profile(folder))


if __name__ == "__main__":
    unittest.main()
