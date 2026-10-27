# Copyright 2026 Therkel
"""`budget restore`: put a whole profile back from one complete backup set.

Each profile here is a synthetic production profile file in a temporary
folder, whose stores are deleted as a machine that died would lose them.
Every test passes `main` an explicit environment.
"""

import errno
import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import BackupSet, back_up, complete_backup_sets
from budget.bronze import BronzeStore
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
from tests.importing.households import ACCOUNTS, log_entries
from tests.test_decision_log import documented_example

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


def _live_run_ids(profile: Profile) -> list[str]:
    """The runs a live Bronze store holds, its write-ahead log included."""
    with BronzeStore(profile) as store:
        return [run.import_run_id for run in store.import_runs()]


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


def _decisions() -> list[bytes]:
    """The documented decision-log example, one complete line each."""
    return [f"{line}\n".encode() for line in documented_example().splitlines()]


def _production_with_decisions(
    folder: Path, logged: list[bytes]
) -> tuple[Path, Profile, BackupSet]:
    """Start production with `logged` as its decision log, and back it up."""
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir()
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    production.input_file("decisions.jsonl").write_bytes(b"".join(logged))
    with writer_lock(production) as lock:
        written = back_up(lock, now=datetime.now(UTC))
    return profile_file, production, written


class DecisionLogRecoveryTests(unittest.TestCase):
    def test_restore_stops_on_a_decision_log_that_does_not_extend_the_sets(
        self,
    ) -> None:
        # Shorter or rewritten, it may have lost decisions or be the newer
        # truth: both copies are kept for the operator to decide between.
        first, second, *_ = _decisions()
        cases = {"shorter": first, "rewritten": second}
        for case, live in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                profile_file, production, written = _production_with_decisions(
                    Path(directory), [first, second]
                )
                shutil.rmtree(production.stores)
                log = production.input_file("decisions.jsonl")
                log.write_bytes(live)

                status, stdout, stderr = restore(profile_file, written.name)

                assert (status, stdout) == (EXIT_VERIFICATION_FAILED, "")
                assert "decision log does not begin with the backup set's" in stderr
                assert log.read_bytes() == live
                assert (written.path / "inputs" / "decisions.jsonl").read_bytes() == (
                    first + second
                )
                assert list(production.stores.glob("*.db")) == []

    def test_restore_falls_back_to_the_sets_decision_log_and_says_what_is_lost(
        self,
    ) -> None:
        first, second, *_ = _decisions()
        with TemporaryDirectory() as directory:
            profile_file, production, written = _production_with_decisions(
                Path(directory), [first, second]
            )
            shutil.rmtree(production.stores)
            log = production.input_file("decisions.jsonl")
            log.unlink()

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert log.read_bytes() == first + second
            assert (
                "the decision log was missing: decisions recorded after backup "
                f"set {written.name} cannot be recovered\n"
            ) in stdout

    def test_restore_stops_on_a_damaged_decision_log(self) -> None:
        # It begins with the set's entries, but a later line is no entry.
        first, second, *_ = _decisions()
        with TemporaryDirectory() as directory:
            profile_file, production, written = _production_with_decisions(
                Path(directory), [first]
            )
            shutil.rmtree(production.stores)
            log = production.input_file("decisions.jsonl")
            damaged = first + b"not a decision\n" + second
            log.write_bytes(damaged)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_VERIFICATION_FAILED, "")
            assert "the live decision log is damaged" in stderr
            assert log.read_bytes() == damaged
            assert list(production.stores.glob("*.db")) == []


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
            # The set's own copies, not fresh stores with the same tables.
            for store in ("silver.db", "gold.db"):
                assert checksum(production.stores / store) == checksum(
                    written.path / store
                )

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
            # Without a later log, restore has no run to catch up with.
            production.import_log_file.unlink()

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
            # Without a later log, restore has no run to catch up with.
            production.import_log_file.unlink()

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"skipped backup set {written.name}: this code cannot read it\n"
                f"restored backup set {older.name}\n"
            )
            assert run_ids(production.bronze_store) == []

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

    def test_restore_migrates_an_older_set_though_the_import_log_runs_ahead(
        self,
    ) -> None:
        # The machine died after an import the set does not hold: the
        # surviving log is ahead of the restored Bronze, as catch-up expects.
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            with writer_lock(production) as lock:
                later = import_one(lock, "export-20260509.csv")
            shutil.rmtree(production.stores)

            with added_migration(
                "CREATE TABLE added_after_the_set (id INTEGER PRIMARY KEY);",
                folder=SILVER_MIGRATIONS,
            ):
                status, _, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert "added_after_the_set" in tables(production.silver_store)
            assert _live_run_ids(production) == [run_id, later]

    def test_restore_replays_runs_the_import_log_lists_beyond_the_set(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            with writer_lock(production) as lock:
                later = import_one(lock, "export-20260509.csv")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                "replayed 1 import run from the export archive\n"
                f"restored backup set {written.name}\n"
            )
            assert _live_run_ids(production) == [run_id, later]

    def test_restore_accepts_an_import_log_missing_runs_the_set_holds(
        self,
    ) -> None:
        # The entries are reconstructible: the next import logs again every
        # run Bronze holds that the log lacks (`operations.md`).
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            production.import_log_file.write_bytes(b"")
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {written.name}\n"
            assert _live_run_ids(production) == [run_id]

    def test_restore_stops_before_anything_on_an_import_log_that_conflicts(
        self,
    ) -> None:
        # The live log records the set's run as started at another time, or
        # does not read: it is kept as it is for the operator to decide on,
        # and nothing is restored beside it.
        def a_day_earlier(line: str, entry: dict[str, object]) -> str:
            # Written exactly as an import writes it, so only the run differs.
            started_at = str(entry["started_at"])
            earlier = datetime.fromisoformat(started_at) - timedelta(days=1)
            return line.replace(started_at, earlier.isoformat())

        def not_an_entry(_: str, entry: dict[str, object]) -> str:
            return json.dumps({**entry, "original_filename": "another.csv"}) + "\n"

        cases = {
            "conflicting run": (a_day_earlier, "records a run the set holds"),
            "invalid entry": (not_an_entry, "an entry does not read"),
        }
        for case, (rewrite, reason) in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                profile_file, production, written, _ = _production_with_a_set(
                    Path(directory)
                )
                (entry,) = log_entries(production)
                line = production.import_log_file.read_bytes().decode("utf-8")
                # As bytes: on Windows, text mode would write CRLF line ends.
                production.import_log_file.write_bytes(
                    rewrite(line, entry).encode("utf-8")
                )
                conflicting = production.import_log_file.read_bytes()
                shutil.rmtree(production.stores)

                status, stdout, stderr = restore(profile_file, written.name)

                assert (status, stdout) == (EXIT_VERIFICATION_FAILED, "")
                assert (
                    f"the live import log does not agree with backup set {written.name}"
                ) in stderr
                assert reason in stderr
                assert production.import_log_file.read_bytes() == conflicting
                assert list(production.stores.glob("*.db")) == []

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
            # Without a later log, restore has no run to catch up with.
            production.import_log_file.unlink()

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"skipped backup set {written.name}: this code cannot read it\n"
                f"restored backup set {older.name}\n"
            )

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

    def test_a_restore_whose_store_copy_fails_puts_back_no_input(self) -> None:
        # "Nothing was restored" must hold for the inputs too.
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            production.accounts_file.unlink()
            copy = shutil.copyfile

            def disk_full_at_gold(source: Path, target: Path) -> object:
                if Path(target).name == "gold.db":
                    raise OSError(errno.ENOSPC, "No space left on device")
                return copy(source, target)

            with mock.patch("shutil.copyfile", side_effect=disk_full_at_gold):
                status, _, stderr = restore(profile_file, written.name)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "nothing was restored" in stderr
            assert not production.accounts_file.exists()

    def test_a_restore_cut_off_while_moving_stores_into_place_can_be_retried(
        self,
    ) -> None:
        # Bronze is in place and Silver is not: the stores folder holds what
        # an unfinished restore left, which a retry finishes.
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            move = Path.replace

            def cut_off_at_silver(source: Path, target: Path) -> Path:
                if Path(target).name == "silver.db":
                    raise OSError(errno.EIO, "Input/output error")
                return move(source, target)

            with mock.patch.object(
                Path, "replace", autospec=True, side_effect=cut_off_at_silver
            ):
                assert restore(profile_file, written.name)[0] != EXIT_OK
            assert production.bronze_store.exists()

            status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {written.name}\n"
            assert run_ids(production.bronze_store) == [run_id]
            assert checksum(production.silver_store) == checksum(
                written.path / "silver.db"
            )

    def test_commands_refuse_a_profile_whose_restore_has_not_finished(self) -> None:
        # Its stores are a restore's half-done work, not a profile to use.
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            move = Path.replace

            def cut_off_at_silver(source: Path, target: Path) -> Path:
                if Path(target).name == "silver.db":
                    raise OSError(errno.EIO, "Input/output error")
                return move(source, target)

            with mock.patch.object(
                Path, "replace", autospec=True, side_effect=cut_off_at_silver
            ):
                restore(profile_file, written.name)
            bronze = production.bronze_store.read_bytes()

            backed_up = backup(profile_file)
            migrated = migrate(profile_file)

            unfinished = (
                f"a restore of backup set {written.name} has not finished; "
                "rerun `budget restore`"
            )
            for status, stderr in (backed_up[::2], migrated):
                assert status == EXIT_REFUSED_ENVIRONMENT
                assert unfinished in stderr
            assert production.bronze_store.read_bytes() == bronze

    def test_restore_names_each_household_input_it_put_back(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            production.accounts_file.unlink()

            status, stdout, _ = restore(profile_file, written.name)

            assert status == EXIT_OK
            assert stdout == (
                "put back inputs/accounts.toml from the backup set\n"
                f"restored backup set {written.name}\n"
            )

    def test_a_restore_whose_store_copy_fails_leaves_no_store_and_can_be_retried(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            copy = shutil.copyfile

            def disk_full_at_gold(source: Path, target: Path) -> object:
                if Path(target).name == "gold.db":
                    raise OSError(errno.ENOSPC, "No space left on device")
                return copy(source, target)

            with mock.patch("shutil.copyfile", side_effect=disk_full_at_gold):
                status, stdout, stderr = restore(profile_file, written.name)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "No space left on device; nothing was restored" in stderr
            assert list(production.stores.glob("*.db")) == []
            assert restore(profile_file, written.name)[0] == EXIT_OK
            assert run_ids(production.bronze_store) == [run_id]

    def test_restore_puts_back_a_household_input_the_profile_has_lost(
        self,
    ) -> None:
        # The live inputs are newer than any set, so only what is missing is
        # taken from the set; what survived is left as it is.
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)
            production.accounts_file.unlink()
            survived = production.import_log_file.read_bytes()

            status, _, stderr = restore(profile_file, written.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert production.accounts_file.is_file(), "accounts.toml not put back"
            assert (
                production.accounts_file.read_bytes()
                == (written.path / "inputs" / "accounts.toml").read_bytes()
            )
            assert production.import_log_file.read_bytes() == survived
