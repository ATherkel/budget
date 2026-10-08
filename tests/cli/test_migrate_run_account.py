# Copyright 2026 Therkel
"""Migrating a Silver store made before each run's account was recorded (#216).

The old store is the packaged schema version 1 with rows in it, built here from
the packaged `0001` migration file. `budget migrate` must upgrade it without a
Bronze change, leave Silver reading as "not built yet" instead of half-built,
and let the following `budget rebuild` fill the account for every run.
"""

import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverResult, SilverStore
from tests.bronze.migration_resources import SILVER_MIGRATIONS
from tests.cli.commands import migrate, rebuild, review
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0
EMPTY = SilverResult((), (), (), (), (), (), ())
# Rows a version-1 store held: a quarantined run with an error and a review
# item, and a transaction. Every statement names only synthetic values.
_OLD_ROWS = (
    "INSERT INTO account_currencies VALUES ('joint-current', 'DKK')",
    "INSERT INTO transactions (ordinal, transaction_id, account_id,"
    " transaction_date, amount, currency, description, source_system,"
    " source_status, booking_status, occurrence, day_sequence, identity_version)"
    " VALUES (1, 'tx-old', 'joint-current', '2026-03-01', -4500, 'DKK', 'OLD',"
    " 'danske-csv-v1', 'Udført', 'booked', 1, 1, '1')",
    "INSERT INTO import_run_results VALUES"
    " (1, 'run-old', 'quarantined', '2026-03-01', '2026-03-02')",
    "INSERT INTO validation_errors VALUES"
    " (1, 1, 'payload-old', 1, 'unknown-status', 'old message')",
    "INSERT INTO review_items VALUES"
    " (1, 'item-old', 'balance-break', 'joint-current', '2026-03-01',"
    " '2026-03-02', NULL, NULL)",
    "INSERT INTO import_run_result_review_items VALUES (1, 1, 'item-old')",
    "INSERT INTO review_item_payloads VALUES (1, 1, 'payload-old')",
)


def _make_version_one_silver(profile: Profile) -> None:
    """Write the Silver store `budget migrate` produced before this change."""
    profile.stores.mkdir(parents=True)
    schema = (SILVER_MIGRATIONS / "0001_create_silver_store.sql").read_text("utf-8")
    with closing(sqlite3.connect(profile.silver_store)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(schema)
        connection.execute(
            "INSERT INTO store_identity VALUES (1, ?, 'silver')", (profile.name,)
        )
        for statement in _OLD_ROWS:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()


def _import_one_export(profile: Profile) -> None:
    """Seed Bronze with one stored import run."""
    source = drop(
        profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
    )
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )


class MigrateRunAccountTests(unittest.TestCase):
    def test_migrate_empties_the_old_result_and_rebuild_fills_the_account(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            _make_version_one_silver(profile)

            assert migrate(profile_file) == (EXIT_OK, "")

            with SilverStore(profile) as store:
                # Not built yet: no run, review item or transaction survives
                # to be read without the run that raised or evidenced it.
                assert store.read() == EMPTY
            assert review(profile_file) == (EXIT_OK, "", "")

            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            _import_one_export(profile)
            status, _, stderr = rebuild(profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            with SilverStore(profile) as store:
                accounts = [r.account_id for r in store.read().import_run_results]
            assert accounts == ["joint-current"]


if __name__ == "__main__":
    unittest.main()
