# Copyright 2026 Therkel
"""Production imports wait for the command that backs up after them.

Production can be migrated now, so it can have a Bronze store; nothing may
import into it until `budget import` backs up after its Bronze writes. The
production profile here is a synthetic profile file in a temporary folder.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore, ImportDeclaration
from budget.bronze.store import ProductionImportBlockedError
from budget.importing import import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import COVERAGE, run_ids
from tests.cli.commands import migrate
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0


def _production(folder: Path) -> Profile:
    """A migrated production profile with the synthetic accounts."""
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir(parents=True, exist_ok=True)
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return production


class ProductionImportTests(unittest.TestCase):
    def test_an_inbox_file_is_not_imported_into_production(self) -> None:
        with TemporaryDirectory() as directory:
            production = _production(Path(directory))
            content = payload("01.04.2026")
            source = drop(production, "joint-current", "export-20260502.csv", content)

            with (
                writer_lock(production) as lock,
                pytest.raises(ProductionImportBlockedError, match="budget import"),
            ):
                import_inbox_file(lock, source, COVERAGE)

            assert source.read_bytes() == content
            assert run_ids(production.bronze_store) == []
            assert not production.import_log_file.exists()
            assert not production.exports.exists()

    def test_bronze_imports_nothing_into_production(self) -> None:
        with TemporaryDirectory() as directory:
            production = _production(Path(directory))
            source = Path(directory) / "export-20260502.csv"
            source.write_bytes(payload("01.04.2026"))
            declaration = ImportDeclaration(
                declared_account_id="joint-current",
                source_format="danske-csv-v1",
                covers_from=COVERAGE.covers_from,
                covers_through=COVERAGE.covers_through,
            )

            with (
                BronzeStore(production) as store,
                pytest.raises(ProductionImportBlockedError),
            ):
                store.import_file(source, declaration)

            assert run_ids(production.bronze_store) == []


if __name__ == "__main__":
    unittest.main()
