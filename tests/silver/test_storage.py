# Copyright 2026 Therkel
"""The Silver store file: its migration and the identity it records.

This test uses the public `Profile` and `migrate_silver` seams. The store file
is opened directly only to check the on-disk contracts ADR-013 names: `STRICT`
tables, WAL, `PRAGMA user_version`, and the one-row `store_identity` that keeps
another profile, or another stage, from opening this file.
"""

import sqlite3
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import test_profile as make_test_profile
from budget.silver.storage import migrate_silver

# The whole persisted result: the identity table, the account currency
# snapshot, every collection of a Silver build, and the parent rows their
# children point at.
STORE_TABLES = {
    "account_currencies",
    "transactions",
    "transaction_evidence",
    "unbooked_records",
    "balance_observations",
    "account_evidence",
    "import_run_results",
    "validation_errors",
    "import_run_result_review_items",
    "review_items",
    "review_item_payloads",
    "store_identity",
}


@contextmanager
def _connected(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the store file directly and close it, so Windows can clean up."""
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


class SilverStorageTests(unittest.TestCase):
    def test_migrate_creates_a_strict_silver_store_that_records_its_identity(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            migrate_silver(profile)

            with _connected(profile.silver_store) as connection:
                definitions = dict(
                    connection.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                    )
                )
                assert set(definitions) == STORE_TABLES
                for definition in definitions.values():
                    assert "STRICT" in definition
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                assert connection.execute(
                    "SELECT profile, stage FROM store_identity"
                ).fetchall() == [("test", "silver")]
                assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


if __name__ == "__main__":
    unittest.main()
