# Copyright 2026 Therkel
"""`budget dev refresh`: give development production's newest backup set.

Each test writes a synthetic production profile and a development profile
whose `upstream_backups` names production's backups folder, both in one
temporary folder. Every test passes `main` an explicit environment.
"""

import errno
import json
import shutil
import sqlite3
import stat
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import BackupSet, back_up, complete_backup_sets
from budget.bronze import BronzeStore
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import checksum, import_one, manifest, run_ids
from tests.cli.commands import dev_refresh, migrate, restore
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


def _production_with_a_set(folder: Path) -> tuple[Profile, BackupSet]:
    """Start production in `folder`, import one run, and back it up."""
    folder.mkdir()
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir()
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    with writer_lock(production) as lock:
        import_one(lock)
        written = back_up(lock, now=datetime.now(UTC))
    return production, written


def production_file(production: Profile) -> Path:
    """The profile file `_production_with_a_set` wrote for `production`."""
    return Path(production.stores).parent / "production.toml"


def _development(folder: Path, production: Profile) -> tuple[Path, Profile]:
    """Write a development profile in `folder` reading production's sets."""
    folder.mkdir()
    profile_file = write_profile(folder, upstream_backups=production.backups)
    return profile_file, load_profile_file(profile_file)


class DevRefreshTests(unittest.TestCase):
    def test_dev_refresh_restores_the_newest_set_into_upstream_read_only(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            development.inputs.mkdir()
            own_accounts = b"# development's own working copy\n"
            development.accounts_file.write_bytes(own_accounts)

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {written.name} into upstream (read-only)\n"
            )
            upstream = development.stores / "upstream"
            for store in ("bronze.db", "silver.db", "gold.db"):
                copy = upstream / store
                assert checksum(copy) == checksum(written.path / store)
                assert not copy.stat().st_mode & stat.S_IWRITE
            assert development.accounts_file.read_bytes() == own_accounts
            assert not development.bronze_store.exists()

    def test_dev_refresh_with_inputs_replaces_developments_inputs(self) -> None:
        # Development's inputs become production's, as the set holds them:
        # a file only development had is not kept.
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            development.inputs.mkdir()
            development.accounts_file.write_bytes(b"# a development edit\n")
            development.input_file("rules.toml").write_bytes(b"# draft rules\n")

            status, stdout, stderr = dev_refresh(profile_file, "--inputs")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {written.name} into upstream (read-only)\n"
                f"replaced development's inputs with backup set {written.name}'s\n"
            )
            sets_inputs = written.path / "inputs"
            assert sorted(path.name for path in development.inputs.iterdir()) == (
                sorted(path.name for path in sets_inputs.iterdir())
            )
            assert (
                development.accounts_file.read_bytes()
                == (sets_inputs / "accounts.toml").read_bytes()
            )

    def test_dev_refresh_writable_restores_developments_own_stores(self) -> None:
        # Relabelled as development's, so development's commands open them;
        # Bronze's evidence, its runs, comes over unchanged.
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            sets_bronze = checksum(written.path / "bronze.db")

            status, stdout, stderr = dev_refresh(profile_file, "--writable")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {written.name} into development's own "
                "stores (writable)\n"
            )
            with BronzeStore(development) as store:
                restored = [run.import_run_id for run in store.import_runs()]
            assert restored == run_ids(written.path / "bronze.db")
            for stage_store in (development.silver_store, development.gold_store):
                assert stage_store.exists()
            assert checksum(written.path / "bronze.db") == sets_bronze

    def test_dev_refresh_refuses_a_profile_that_reads_no_upstream_sets(
        self,
    ) -> None:
        # Production never refreshes from itself, and development without
        # `upstream_backups` has no sets to read.
        with TemporaryDirectory() as directory:
            production, _ = _production_with_a_set(Path(directory) / "prod")
            (Path(directory) / "dev").mkdir()
            cases = {
                "production": Path(directory) / "prod" / "production.toml",
                "development without upstream_backups": write_profile(
                    Path(directory) / "dev"
                ),
            }
            for case, profile_file in cases.items():
                with self.subTest(case):
                    status, stdout, stderr = dev_refresh(profile_file)

                    assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
                    assert "dev refresh needs a development profile" in stderr
            assert not (production.stores / "upstream").exists()

    def test_dev_refresh_and_restore_take_folders_with_spaces_and_signs(
        self,
    ) -> None:
        # SQLite opens a set's stores by URI, where these characters must be
        # escaped.
        with TemporaryDirectory() as directory:
            folder = Path(directory) / "Budget data ø & #1 (100%)"
            folder.mkdir()
            production, written = _production_with_a_set(folder / "prod uction")
            profile_file, development = _development(
                folder / "dev elopment", production
            )

            refreshed = dev_refresh(profile_file)
            shutil.rmtree(production.stores)
            restored = restore(production_file(production), written.name)

            assert refreshed[::2] == (EXIT_OK, "")
            assert restored[::2] == (EXIT_OK, "")
            assert checksum(development.stores / "upstream" / "bronze.db") == (
                checksum(written.path / "bronze.db")
            )

    def test_dev_refresh_refuses_a_set_that_is_not_productions(self) -> None:
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            listed = manifest(written.path)
            listed["profile"] = "development"
            (written.path / "manifest.json").write_text(
                json.dumps(listed), encoding="utf-8"
            )

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert (
                f"backup set {written.name} is the development profile's, "
                "not production's"
            ) in stderr
            assert not (development.stores / "upstream").exists()

    def test_dev_refresh_passes_over_a_newest_set_this_code_cannot_read(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            production, older = _production_with_a_set(Path(directory) / "prod")
            with writer_lock(production) as lock:
                newer = back_up(lock, now=datetime.now(UTC))
            with closing(sqlite3.connect(newer.path / "bronze.db")) as connection:
                connection.execute("PRAGMA user_version = 99")
            listed = manifest(newer.path)
            files = listed["files"]
            assert isinstance(files, dict)
            files["bronze.db"] = checksum(newer.path / "bronze.db")
            (newer.path / "manifest.json").write_text(
                json.dumps(listed), encoding="utf-8"
            )
            profile_file, development = _development(
                Path(directory) / "dev", production
            )

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.endswith(
                f"restored backup set {older.name} into upstream (read-only)\n"
            )
            assert checksum(development.stores / "upstream" / "bronze.db") == (
                checksum(older.path / "bronze.db")
            )

    def test_dev_refresh_refuses_when_production_has_no_complete_set(
        self,
    ) -> None:
        # As when the synchronised backups folder is offline or empty.
        with TemporaryDirectory() as directory:
            (Path(directory) / "dev").mkdir()
            profile_file = write_profile(
                Path(directory) / "dev",
                upstream_backups=Path(directory) / "no backups yet",
            )

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "no complete backup set this code can read" in stderr

    def test_dev_refresh_never_relabels_a_store_of_another_profile(self) -> None:
        # The manifest says production, but the store itself does not.
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            silver = written.path / "silver.db"
            with closing(sqlite3.connect(silver)) as connection, connection:
                connection.execute("UPDATE store_identity SET profile = 'test'")
            listed = manifest(written.path)
            files = listed["files"]
            assert isinstance(files, dict)
            files["silver.db"] = checksum(silver)
            (written.path / "manifest.json").write_text(
                json.dumps(listed), encoding="utf-8"
            )
            profile_file, development = _development(
                Path(directory) / "dev", production
            )

            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )

            status, stdout, stderr = dev_refresh(profile_file, "--writable")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.endswith(
                f"restored backup set {older.name} into development's own "
                "stores (writable)\n"
            )
            assert checksum(development.bronze_store) != checksum(
                written.path / "bronze.db"
            )

    def test_a_writable_refresh_cut_off_while_moving_keeps_the_old_stores(
        self,
    ) -> None:
        # Never new Bronze beside old Silver: the stores change as a group.
        with TemporaryDirectory() as directory:
            production, _ = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            development.stores.mkdir()
            old = {
                store: f"development's own {store}".encode()
                for store in ("bronze.db", "silver.db", "gold.db")
            }
            for store, content in old.items():
                (development.stores / store).write_bytes(content)
            move = Path.replace
            failed: list[Path] = []

            def cut_off_once_at_silver(source: Path, target: Path) -> Path:
                # Once: the move putting the old store back then succeeds.
                if Path(target) == development.silver_store and not failed:
                    failed.append(Path(target))
                    raise OSError(errno.EIO, "Input/output error")
                return move(source, target)

            with mock.patch.object(
                Path, "replace", autospec=True, side_effect=cut_off_once_at_silver
            ):
                status, stdout, stderr = dev_refresh(profile_file, "--writable")

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "Input/output error; development's stores are as they were" in (
                stderr
            )
            for store, content in old.items():
                assert (development.stores / store).read_bytes() == content

    def test_dev_refresh_replaces_upstream_with_a_newer_set(self) -> None:
        with TemporaryDirectory() as directory:
            production, _ = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            assert dev_refresh(profile_file)[0] == EXIT_OK
            with writer_lock(production) as lock:
                import_one(lock, "export-20260509.csv")
                newer = back_up(lock, now=datetime.now(UTC))

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {newer.name} into upstream (read-only)\n"
            )
            upstream = development.stores / "upstream" / "bronze.db"
            assert checksum(upstream) == checksum(newer.path / "bronze.db")
