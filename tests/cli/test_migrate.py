# Copyright 2026 Therkel
"""`budget migrate`: creating and upgrading a profile's Bronze, Silver and Gold stores.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import sqlite3
import unittest
from contextlib import AbstractContextManager, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget import sqlstore
from budget.bronze import BronzeStore, migrate_bronze
from budget.bronze.storage import (
    ForeignKeyViolationError,
    MigrationResourceError,
    StoreIdentityError,
)
from budget.cli import main
from budget.gold.store import GoldStore
from budget.profiles import test_profile as make_test_profile
from budget.silver import SilverStore, migrate_silver
from tests.bronze.migration_resources import (
    SILVER_MIGRATIONS,
    added_migration,
    patched_resources,
)
from tests.cli.commands import migrate, rebuild
from tests.cli.pipelines import household
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4

_SHORT_BUSY_TIMEOUT_MS = 100
_MARKER_TABLE = "CREATE TABLE marker (x TEXT) STRICT;\n"

_ORPHAN_SOURCE_RECORD = (
    "INSERT INTO source_records (payload_id, record_ordinal, fields)"
    " VALUES ('missing-payload', 1, '{}');\n"
)
_INVALID_STATEMENT = "INSERT INTO nowhere (x) VALUES (this is not valid sql);\n"


def _user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _table_names(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def _short_busy_timeout() -> AbstractContextManager[object]:
    """Wait 100 ms for a held store instead of the real five seconds."""
    return mock.patch.object(sqlstore, "BUSY_TIMEOUT_MS", _SHORT_BUSY_TIMEOUT_MS)


class MigrateTests(unittest.TestCase):
    def test_migrate_creates_the_development_bronze_store(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_OK
            development = development_profile(folder)
            with BronzeStore(development):
                pass
            with pytest.raises(StoreIdentityError):
                BronzeStore(make_test_profile(folder))

    def test_the_bronze_stage_can_be_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder), "--stage", "bronze")

            assert status == EXIT_OK
            with BronzeStore(development_profile(folder)):
                pass

    def test_the_silver_stage_can_be_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder), "--stage", "silver")

            assert status == EXIT_OK
            development = development_profile(folder)
            assert development.silver_store.exists()
            with SilverStore(development):
                pass

    def test_the_gold_stage_can_be_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder), "--stage", "gold")

            assert status == EXIT_OK
            development = development_profile(folder)
            assert development.gold_store.exists()
            with GoldStore(development):
                pass

    def test_migrate_creates_every_store_when_no_stage_is_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder))

            assert status == EXIT_OK
            development = development_profile(folder)
            assert development.bronze_store.exists()
            assert development.silver_store.exists()
            assert development.gold_store.exists()
            with BronzeStore(development), SilverStore(development):
                pass
            with GoldStore(development):
                pass


class MigrateRefusalTests(unittest.TestCase):
    def test_production_migration_is_refused_before_anything_is_created(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = migrate(write_profile(folder, name="production"))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "production" in stderr
            assert not (folder / "stores").exists()

    def test_a_store_of_another_profile_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            migrate_bronze(make_test_profile(folder))

            status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "'test'" in stderr
            with BronzeStore(make_test_profile(folder)):
                pass

    def test_a_silver_store_of_another_profile_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            migrate_silver(make_test_profile(folder))

            status, stderr = migrate(write_profile(folder), "--stage", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "'test'" in stderr
            with SilverStore(make_test_profile(folder)):
                pass

    def test_a_store_of_another_stage_is_refused(self) -> None:
        # Each stage's file is replaced by a store the other stage migrated.
        for stage, other in (("bronze", "silver"), ("silver", "bronze")):
            with self.subTest(stage=stage), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder)
                development = development_profile(folder)
                paths = {
                    "bronze": development.bronze_store,
                    "silver": development.silver_store,
                }
                assert migrate(profile_file, "--stage", other)[0] == EXIT_OK
                paths[other].rename(paths[stage])
                if stage == "bronze":
                    # Silver is at a newer schema version than Bronze knows;
                    # pretend otherwise so the stage mismatch is what refuses.
                    with closing(sqlite3.connect(paths[stage])) as connection:
                        connection.execute("PRAGMA user_version = 1")

                status, stderr = migrate(profile_file, "--stage", stage)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert f"stage {other!r}" in stderr
                with closing(sqlite3.connect(paths[stage])) as connection:
                    assert connection.execute(
                        "SELECT stage FROM store_identity"
                    ).fetchall() == [(other,)]

    def test_production_silver_is_refused_first_for_want_of_bronze(self) -> None:
        # Starting Silver would be refused too until Bronze has a store, so
        # the advice is the step that works first.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = migrate(
                write_profile(folder, name="production"), "--stage", "silver"
            )

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Bronze store" in stderr
            assert "budget migrate --stage bronze --new-store" in stderr
            assert "120" not in stderr
            assert not (folder / "stores").exists()
            assert not (folder / "backups").exists()

    def test_a_store_newer_than_this_code_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            store = development_profile(folder).bronze_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "99" in stderr
            assert _user_version(store) == 99

    def test_a_silver_store_newer_than_this_code_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file, "--stage", "silver")[0] == EXIT_OK
            store = development_profile(folder).silver_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            status, stderr = migrate(profile_file, "--stage", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "99" in stderr
            assert _user_version(store) == 99

    def test_sqlite_below_the_version_floor_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with mock.patch.object(sqlite3, "sqlite_version_info", (3, 51, 2)):
                status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "3.51.2" in stderr
            assert not (folder / "stores").exists()

    def test_a_store_another_program_holds_is_refused(self) -> None:
        # Such as DB Browser for SQLite, left open in a write transaction.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            store = development_profile(folder).bronze_store
            store.parent.mkdir(parents=True)
            with (
                closing(sqlite3.connect(store, isolation_level=None)) as holder,
                _short_busy_timeout(),
            ):
                holder.execute("BEGIN EXCLUSIVE")

                status, stderr = migrate(write_profile(folder))

                holder.execute("ROLLBACK")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"{store} is in use" in stderr
            assert store.read_bytes() == b""

    def test_a_silver_store_another_program_holds_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            store = development_profile(folder).silver_store
            store.parent.mkdir(parents=True)
            with (
                closing(sqlite3.connect(store, isolation_level=None)) as holder,
                _short_busy_timeout(),
            ):
                holder.execute("BEGIN EXCLUSIVE")

                status, stderr = migrate(write_profile(folder), "--stage", "silver")

                holder.execute("ROLLBACK")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"{store} is in use" in stderr
            assert store.read_bytes() == b""

    def test_a_gold_store_another_program_holds_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            store = development_profile(folder).gold_store
            store.parent.mkdir(parents=True)
            with (
                closing(sqlite3.connect(store, isolation_level=None)) as holder,
                _short_busy_timeout(),
            ):
                holder.execute("BEGIN EXCLUSIVE")

                status, stderr = migrate(write_profile(folder), "--stage", "gold")

                holder.execute("ROLLBACK")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"{store} is in use" in stderr
            assert store.read_bytes() == b""

    def test_a_silver_store_another_program_writes_to_is_refused_an_upgrade(
        self,
    ) -> None:
        # A migrated store is in WAL mode, where a writer leaves reads open: the
        # refusal comes only when the pending migration starts to write.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            migrate(profile_file, "--stage", "silver")
            store = development_profile(folder).silver_store
            version = _user_version(store)
            with (
                closing(sqlite3.connect(store, isolation_level=None)) as holder,
                added_migration(_MARKER_TABLE, folder=SILVER_MIGRATIONS),
                _short_busy_timeout(),
            ):
                holder.execute("BEGIN IMMEDIATE")

                status, stderr = migrate(profile_file, "--stage", "silver")

                holder.execute("ROLLBACK")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"{store} is in use" in stderr
            assert _user_version(store) == version
            assert "marker" not in _table_names(store)


class MigrateDefectTests(unittest.TestCase):
    def test_a_broken_packaged_migration_is_a_defect_not_a_refusal(self) -> None:
        # A defect propagates out of `main`, so Python reports it and exits 1.
        cases = {
            "an incomplete statement": (
                "CREATE TABLE marker (x TEXT)\n",
                MigrationResourceError,
            ),
            "a foreign-key violation": (
                _ORPHAN_SOURCE_RECORD,
                ForeignKeyViolationError,
            ),
        }
        for case, (suffix, defect) in cases.items():
            with (
                self.subTest(case),
                TemporaryDirectory() as directory,
                patched_resources(suffix),
                pytest.raises(defect),
            ):
                migrate(write_profile(Path(directory)))

    def test_a_failed_migration_commits_none_of_the_steps_before_it(self) -> None:
        # The first step would make a store, the added second one fails it.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with (
                added_migration(_ORPHAN_SOURCE_RECORD),
                pytest.raises(ForeignKeyViolationError),
            ):
                migrate(write_profile(folder))

            store = development_profile(folder).bronze_store
            assert _user_version(store) == 0
            with closing(sqlite3.connect(store)) as connection:
                assert (
                    connection.execute("SELECT * FROM sqlite_master").fetchall() == []
                )

    def test_a_failed_silver_migration_commits_none_of_the_steps_before_it(
        self,
    ) -> None:
        # The first step would make a store, the added second one fails it.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with (
                added_migration(_INVALID_STATEMENT, folder=SILVER_MIGRATIONS),
                pytest.raises(sqlite3.OperationalError, match='near "sql"'),
            ):
                migrate(write_profile(folder), "--stage", "silver")

            store = development_profile(folder).silver_store
            assert _user_version(store) == 0
            with closing(sqlite3.connect(store)) as connection:
                assert (
                    connection.execute("SELECT * FROM sqlite_master").fetchall() == []
                )


class SilverProvenanceRecoveryTests(unittest.TestCase):
    def test_populated_version_2_silver_recovers_through_cli_rebuild(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            built = household(folder, silver=False)
            built.profile.silver_store.unlink()
            schema_1 = (SILVER_MIGRATIONS / "0001_create_silver_store.sql").read_text(
                "utf-8"
            )
            schema_2 = (SILVER_MIGRATIONS / "0002_record_run_payloads.sql").read_text(
                "utf-8"
            )
            with closing(sqlite3.connect(built.profile.silver_store)) as connection:
                connection.executescript(schema_1)
                connection.executescript(schema_2)
                connection.execute(
                    "INSERT INTO store_identity VALUES (1, 'development', 'silver')"
                )
                connection.execute(
                    "INSERT INTO account_currencies VALUES ('joint-current', 'DKK')"
                )
                connection.execute(
                    "INSERT INTO transactions"
                    " (ordinal, transaction_id, account_id, transaction_date, amount,"
                    " currency, description, source_system, source_status,"
                    " booking_status, occurrence, day_sequence, identity_version)"
                    " VALUES (1, 't1', 'joint-current', '2026-03-01', -4500, 'DKK',"
                    " 'SYNTHETIC', 'csv', 'BOOKED', 'booked', 1, 1, '1')"
                )
                connection.execute(
                    "INSERT INTO evidence_exports VALUES"
                    " (1, 'run-old', 'joint-current', '2026-03-05',"
                    " '2026-03-01', '2026-03-04', 'payload-old')"
                )
                connection.execute(
                    "INSERT INTO import_run_results VALUES"
                    " (1, 'run-old', 'joint-current', 'accepted',"
                    " '2026-03-01', '2026-03-04', 'payload-old')"
                )
                connection.execute("PRAGMA user_version = 2")
                connection.commit()

            status, stderr = migrate(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            with SilverStore(built.profile) as store:
                assert not store.is_built()
                assert store.read().transactions == ()
                assert store.read().import_run_results == ()

            status, _, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1


if __name__ == "__main__":
    unittest.main()
