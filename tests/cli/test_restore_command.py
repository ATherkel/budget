# Copyright 2026 Therkel
"""`budget restore`: put a whole profile back from one complete backup set.

Each profile here is a synthetic production profile file in a temporary
folder, whose stores are deleted as a machine that died would lose them.
Every test passes `main` an explicit environment.
"""

import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import BackupSet, back_up, complete_backup_sets
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import (
    checksum,
    import_one,
    manifest,
    run_ids,
    tables,
    user_version,
)
from tests.bronze.migration_resources import SILVER_MIGRATIONS, added_migration
from tests.cli.commands import backup, migrate, restore
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
EXIT_VERIFICATION_FAILED = 5


def _production_with_a_set(folder: Path) -> tuple[Path, Profile, BackupSet, str]:
    """Start production, import one run, and back it up; return what was made."""
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir()
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    with writer_lock(production) as lock:
        run_id = import_one(lock)
        # After the set `migrate` wrote, so it is the newest.
        written = back_up(lock, now=datetime.now(UTC))
    return profile_file, production, written, run_id


def _rechecksum(backup: BackupSet, store: str, schema_version: int | None) -> None:
    """Rewrite a set's manifest to match a store changed in place."""
    path = backup.path / store
    written = manifest(backup.path)
    files = written["files"]
    stores = written["stores"]
    assert isinstance(files, dict)
    assert isinstance(stores, dict)
    files[store] = checksum(path)
    for entry in stores.values():
        if entry["path"] == store and schema_version is not None:
            entry["schema_version"] = schema_version
    (backup.path / "manifest.json").write_text(json.dumps(written), encoding="utf-8")


def _from_newer_code(backup: BackupSet, store: str) -> None:
    """Make one store in a set a schema version ahead of this code, consistently.

    The manifest is rewritten to match, so the set stays complete: it is only
    a set this code cannot read.
    """
    with closing(sqlite3.connect(backup.path / store)) as connection:
        connection.execute("PRAGMA user_version = 99")
    _rechecksum(backup, store, 99)


def _damaged_inside(backup: BackupSet, store: str) -> None:
    """Damage a store's second page, past its header, and rewrite the manifest.

    The set stays complete by its checksums: only SQLite can tell.
    """
    path = backup.path / store
    with path.open("r+b") as damaged:
        damaged.seek(4096 + 8)
        damaged.write(b"\xa5" * 512)
    _rechecksum(backup, store, None)


WHOLE_PROFILE_ADVICE = (
    "with the rest of the profile: move every store out of the stores "
    "folder, then run `budget restore`"
)


class LostStoreAdviceTests(unittest.TestCase):
    # A store is never restored beside live ones, so the advice for a lost
    # store is a whole-profile restore.
    def test_backup_advises_a_whole_profile_restore_for_a_lost_store(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, _, _ = _production_with_a_set(Path(directory))
            for lost in production.stores.glob("silver.db*"):
                lost.unlink()

            status, _, stderr = backup(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"Silver store must be restored {WHOLE_PROFILE_ADVICE}" in stderr

    def test_migrate_advises_a_whole_profile_restore_for_a_lost_store(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, _, _ = _production_with_a_set(Path(directory))
            for lost in production.stores.glob("gold.db*"):
                lost.unlink()

            status, stderr = migrate(profile_file, "--stage", "gold", "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"Gold store must be restored {WHOLE_PROFILE_ADVICE}" in stderr


class RestoreCommandTests(unittest.TestCase):
    def test_restore_puts_every_store_of_the_newest_set_into_an_empty_profile(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {written.name}\n"
            assert run_ids(production.bronze_store) == [run_id]
            for store in ("silver.db", "gold.db"):
                assert tables(production.stores / store) == tables(written.path / store)

    def test_restore_refuses_a_profile_with_no_complete_set(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")

            status, stdout, stderr = restore(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "no complete backup set this code can read" in stderr

    def test_restore_takes_the_set_it_is_given_by_name(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, older.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {older.name}\n"
            # The set `migrate` wrote holds no import run yet.
            assert run_ids(production.bronze_store) == []

    def test_restore_refuses_a_named_set_that_does_not_match_its_manifest(
        self,
    ) -> None:
        # The default skips such a set; a set asked for by name is never
        # swapped for another.
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            with (written.path / "gold.db").open("r+b") as damaged:
                damaged.seek(100)
                damaged.write(b"\xff")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_VERIFICATION_FAILED, "")
            assert f"backup set {written.name} is not complete" in stderr
            assert not production.bronze_store.exists()

    def test_restore_refuses_a_profile_that_still_has_a_store(self) -> None:
        # Only a whole profile is restored: never one store beside live ones.
        with TemporaryDirectory() as directory:
            profile_file, production, _, _ = _production_with_a_set(Path(directory))
            for lost in production.stores.glob("silver.db*"):
                lost.unlink()
            bronze = production.bronze_store.read_bytes()

            status, stdout, stderr = restore(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "the stores folder still holds bronze.db" in stderr
            assert "move every store out of it" in stderr
            assert production.bronze_store.read_bytes() == bronze
            assert not production.silver_store.exists()

    def test_restore_refuses_a_stores_folder_holding_a_stores_leftover_wal(
        self,
    ) -> None:
        # A restored store beside another store's write-ahead log would have
        # that log replayed into it when first opened.
        with TemporaryDirectory() as directory:
            profile_file, production, _, _ = _production_with_a_set(Path(directory))
            for moved in production.stores.glob("*.db"):
                moved.unlink()
            (production.stores / "bronze.db-wal").write_bytes(b"left by a crash")

            status, stdout, stderr = restore(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "the stores folder still holds bronze.db-wal" in stderr
            assert not production.bronze_store.exists()

    def test_restore_refuses_a_named_set_written_by_newer_code(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            _from_newer_code(written, "silver.db")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "silver.db is at schema version 99" in stderr
            assert list(production.stores.glob("*.db")) == []

    def test_restore_refuses_a_named_set_listing_a_stage_it_does_not_know(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            shutil.copyfile(written.path / "bronze.db", written.path / "later.db")
            listed = manifest(written.path)
            stores, files = listed["stores"], listed["files"]
            assert isinstance(stores, dict)
            assert isinstance(files, dict)
            stores["later"] = {"path": "later.db", "schema_version": 1}
            files["later.db"] = checksum(written.path / "later.db")
            (written.path / "manifest.json").write_text(
                json.dumps(listed), encoding="utf-8"
            )
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "lists a later store, which this code does not know" in stderr
            assert list(production.stores.glob("*.db")) == []

    def test_restore_passes_over_a_newest_set_written_by_newer_code(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )
            _from_newer_code(written, "silver.db")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"skipped backup set {written.name}: this code cannot read it\n"
                f"restored backup set {older.name}\n"
            )
            assert run_ids(production.bronze_store) == []

    def test_restore_refuses_a_set_whose_store_fails_sqlites_integrity_check(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            _damaged_inside(written, "bronze.db")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_VERIFICATION_FAILED, "")
            assert "bronze.db in backup set" in stderr
            assert "fails SQLite's integrity check" in stderr
            assert list(production.stores.glob("*.db")) == []

    def test_restore_passes_over_a_newest_set_holding_a_file_that_is_no_database(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )
            with (written.path / "silver.db").open("r+b") as damaged:
                damaged.write(b"\x00" * 16)
            _rechecksum(written, "silver.db", None)
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.endswith(f"restored backup set {older.name}\n")

    def test_restore_passes_over_a_newest_set_whose_store_is_damaged(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )
            _damaged_inside(written, "bronze.db")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"skipped backup set {written.name}: this code cannot read it\n"
                f"restored backup set {older.name}\n"
            )

    def test_restore_migrates_a_store_the_set_holds_at_an_older_version(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            older_version = user_version(written.path / "silver.db")
            shutil.rmtree(production.stores)

            with added_migration(
                "CREATE TABLE added_after_the_set (id INTEGER PRIMARY KEY);",
                folder=SILVER_MIGRATIONS,
            ):
                status, _, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert user_version(production.silver_store) == older_version + 1
            assert "added_after_the_set" in tables(production.silver_store)
            assert run_ids(production.bronze_store) == [run_id]
