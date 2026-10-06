# Copyright 2026 Therkel
"""Backup sets: a complete, checked copy of a profile, written whole or not at all.

Every profile here is a synthetic test profile in a temporary folder; no test
opens a production store or reads a real export.
"""

import json
import shutil
import sqlite3
import tomllib
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.backups import (
    PUBLISHING_SUFFIX,
    BackupVerificationError,
    BackupWriteError,
    UnsupportedStoresError,
    back_up,
    complete_backup_sets,
    hold_for_recovery,
)
from budget.bronze import migrate_bronze
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.locking import writer_lock
from budget.profiles import Profile, RetentionPolicy
from budget.silver import migrate_silver
from tests.backups.sets import (
    NOW,
    add_silver_currency,
    checksum,
    copied_run_ids,
    damaged_rereads,
    holding,
    holding_silver,
    import_one,
    manifest,
    run_ids,
    silver_accounts,
)
from tests.bronze.migration_resources import SILVER_MIGRATIONS, added_migration
from tests.importing.households import household

REPOSITORY = Path(__file__).resolve().parents[2]


def _source_fingerprint(package: Path) -> str:
    """The fingerprint `operations.md` defines for the package's source.

    One line per `.py` and `.sql` file, sorted by its `/`-separated path in
    the package: the path, a tab, the file's SHA-256, and a line feed; then
    the SHA-256 of those lines.
    """
    sources = [path for path in package.rglob("*") if path.suffix in {".py", ".sql"}]
    lines = sorted(
        f"{path.relative_to(package).as_posix()}\t"
        f"{sha256(path.read_bytes()).hexdigest()}\n"
        for path in sources
    )
    return sha256("".join(lines).encode("utf-8")).hexdigest()


class BackUpTests(unittest.TestCase):
    def test_a_set_holds_a_snapshot_of_bronze_taken_through_the_backup_api(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = household(folder / "household")
            with closing(holding(profile)), writer_lock(profile) as lock:
                run_id = import_one(lock)
                # The run is still in the WAL file: a copy of the store file
                # alone would miss it.
                assert copied_run_ids(profile.bronze_store, folder) == []

                backup = back_up(lock, now=NOW)

            assert backup.name == "2026-05-02T18-05-11.120731Z"
            assert backup.path == (folder / "household" / "backups" / backup.name)
            assert backup.created_at == NOW
            store = backup.path / "bronze.db"
            written = manifest(backup.path)
            files = written["files"]
            assert isinstance(files, dict)
            assert files["bronze.db"] == checksum(store)
            assert run_ids(store) == [run_id]
            assert written["format"] == 1
            assert written["profile"] == "test"
            assert written["created_at"] == "2026-05-02T18:05:11.120731+00:00"
            assert written["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1}
            }
            assert complete_backup_sets(profile) == (backup,)

    def test_a_set_holds_a_snapshot_of_silver_beside_bronze(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = household(folder / "household")
            migrate_silver(profile)
            with closing(holding_silver(profile)), writer_lock(profile) as lock:
                add_silver_currency(profile, "joint-current", "DKK")
                # The row is still in Silver's WAL file: a copy of the store
                # file alone would miss it.
                copy = folder / "copied-silver.db"
                shutil.copyfile(profile.silver_store, copy)
                assert silver_accounts(copy) == []

                backup = back_up(lock, now=NOW)

            store = backup.path / "silver.db"
            written = manifest(backup.path)
            files = written["files"]
            assert isinstance(files, dict)
            assert files["silver.db"] == checksum(store)
            assert files["bronze.db"] == checksum(backup.path / "bronze.db")
            assert silver_accounts(store) == ["joint-current"]
            assert written["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1},
                "silver": {"path": "silver.db", "schema_version": 1},
            }
            assert complete_backup_sets(profile) == (backup,)

    def test_a_set_copies_the_inputs_folder_and_records_each_logs_length(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            decisions = profile.inputs / "decisions.jsonl"
            # A complete entry, then one a crash cut off, which is not counted.
            decisions.write_bytes(b'{"format": 1, "entry": 1}\n{"format": 1, "ent')
            nested = profile.inputs / "notes" / "read-me.txt"
            nested.parent.mkdir()
            nested.write_bytes(b"synthetic")
            with writer_lock(profile) as lock:
                import_one(lock)
                backup = back_up(lock, now=NOW)

            written = manifest(backup.path)
            files = written["files"]
            assert isinstance(files, dict)
            names = ("accounts.toml", "imports.jsonl", "decisions.jsonl")
            for relative in (*names, "notes/read-me.txt"):
                copy = backup.path / "inputs" / relative
                assert copy.read_bytes() == (profile.inputs / relative).read_bytes()
                assert files[f"inputs/{relative}"] == checksum(copy)
            assert set(files) == {
                "bronze.db",
                "inputs/accounts.toml",
                "inputs/imports.jsonl",
                "inputs/decisions.jsonl",
                "inputs/notes/read-me.txt",
            }
            assert written["logs"] == {
                "imports.jsonl": profile.import_log_file.stat().st_size,
                "decisions.jsonl": len(b'{"format": 1, "entry": 1}\n'),
            }

    def test_a_set_names_the_code_version_that_wrote_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                backup = back_up(lock, now=NOW)

            pyproject = tomllib.loads(
                (REPOSITORY / "pyproject.toml").read_text("utf-8")
            )
            assert manifest(backup.path)["code_version"] == {
                "package": pyproject["project"]["version"],
                "source_sha256": _source_fingerprint(REPOSITORY / "src" / "budget"),
            }

    def test_a_log_that_does_not_exist_yet_has_length_zero(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                backup = back_up(lock, now=NOW)

            assert manifest(backup.path)["logs"] == {
                "imports.jsonl": 0,
                "decisions.jsonl": 0,
            }


class InterruptedSetTests(unittest.TestCase):
    def test_an_interrupted_set_is_never_selected_and_the_next_backup_removes_it(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                earlier = back_up(lock, now=NOW - timedelta(days=1))
            # What a crash leaves: a set still in staging, a set cut off while
            # it was copied into the backups folder, and one cut off before
            # its manifest under its own name.
            staged = profile.backup_staging / "2026-05-02T00-00-00.000000Z"
            staged.mkdir(parents=True)
            (staged / "bronze.db").write_bytes(b"cut off")
            backups = earlier.path.parent
            copying = backups / "2026-05-02T01-00-00.000000Z.partial"
            shutil.copytree(earlier.path, copying)
            no_manifest = backups / "2026-05-02T02-00-00.000000Z"
            shutil.copytree(earlier.path, no_manifest)
            (no_manifest / "manifest.json").unlink()

            assert complete_backup_sets(profile) == (earlier,)

            with writer_lock(profile) as lock:
                backup = back_up(lock, now=NOW)

            assert complete_backup_sets(profile) == (backup, earlier)
            assert list(profile.backup_staging.iterdir()) == []
            assert not copying.exists()
            # Not this code's to delete: it is named as a set, and may be one
            # a person is putting back by hand.
            assert no_manifest.exists()


class ChecksumTests(unittest.TestCase):
    def test_a_set_whose_files_do_not_match_its_manifest_is_never_selected(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                earlier = back_up(lock, now=NOW - timedelta(days=1))
                import_one(lock)
                later = back_up(lock, now=NOW)
            cases = {
                "a changed byte": lambda content: content[:-1] + b"\x00",
                "a cut-off file": lambda content: content[:-1],
            }
            for case, damage in cases.items():
                for relative in ("bronze.db", "inputs/imports.jsonl"):
                    with self.subTest(case, file=relative):
                        target = later.path / relative
                        original = target.read_bytes()
                        target.write_bytes(damage(original))

                        assert complete_backup_sets(profile) == (earlier,)

                        target.write_bytes(original)
            missing = later.path / "inputs" / "accounts.toml"
            missing.unlink()
            assert complete_backup_sets(profile) == (earlier,)

    def test_a_copy_that_does_not_match_its_manifest_is_never_published(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_one(lock)

                with (
                    damaged_rereads(profile.backup_staging, "bronze.db"),
                    pytest.raises(BackupVerificationError),
                ):
                    back_up(lock, now=NOW)

            assert complete_backup_sets(profile) == ()
            backups = profile.backup_path(".")
            assert list(backups.iterdir()) == []
            assert list(profile.backup_staging.iterdir()) == []


class ImportLogAgreementTests(unittest.TestCase):
    def test_a_set_is_refused_when_the_import_log_disagrees_with_the_snapshot(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = household(folder / "household")
            with writer_lock(profile) as lock:
                import_one(lock)
            entry = profile.import_log_file.read_bytes()
            fresh = household(folder / "fresh")
            cases = {
                "a blank line": (profile, entry + b"\n", ImportLogDamagedError),
                "an edited entry": (
                    profile,
                    entry.replace(b'"stored"', b'"repeat"'),
                    ImportLogDamagedError,
                ),
                "an entry for a run the snapshot lacks": (
                    fresh,
                    entry,
                    ImportLogAheadOfBronzeError,
                ),
            }
            for minute, (case, (target, log, refusal)) in enumerate(cases.items()):
                with self.subTest(case):
                    target.import_log_file.write_bytes(log)

                    with writer_lock(target) as lock, pytest.raises(refusal):
                        back_up(lock, now=NOW + timedelta(minutes=minute))

                    assert complete_backup_sets(target) == ()
                    assert list(target.backup_staging.iterdir()) == []

    def test_a_log_behind_bronze_or_cut_off_by_a_crash_is_backed_up(self) -> None:
        # The next import logs the runs it lacks and completes a cut-off
        # entry, so neither is a disagreement.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_one(lock, "export-20260502.csv")
                first = profile.import_log_file.read_bytes()
                import_one(lock, "export-20260503.csv")
            second = profile.import_log_file.read_bytes()[len(first) :]
            cases = {
                "a run not logged yet": first,
                "an entry cut off by a crash": first + second[:-9],
            }
            for minute, (case, log) in enumerate(cases.items()):
                with self.subTest(case):
                    profile.import_log_file.write_bytes(log)

                    with writer_lock(profile) as lock:
                        backup = back_up(lock, now=NOW + timedelta(minutes=minute))

                    logs = manifest(backup.path)["logs"]
                    assert isinstance(logs, dict)
                    assert logs["imports.jsonl"] == len(first)
                    copy = backup.path / "inputs" / "imports.jsonl"
                    assert copy.read_bytes() == log


class UnsupportedStoreTests(unittest.TestCase):
    def test_a_profile_with_a_store_this_backup_cannot_cover_is_refused(
        self,
    ) -> None:
        # Bronze and Silver are covered; Gold has no store in this code yet.
        cases = {
            "a Gold store": Path("gold.db"),
            "a legacy publication": Path("gold") / "legacy" / "publication-1.db",
            "an empty Gold store being created": Path("gold.db"),
            "a store under any other name": Path("household.sqlite"),
        }
        for case, relative in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                profile = household(Path(directory))
                store = profile.stores / relative
                store.parent.mkdir(parents=True, exist_ok=True)
                if case.startswith("an empty"):
                    store.write_bytes(b"")
                else:
                    with closing(sqlite3.connect(store)) as connection:
                        connection.execute("CREATE TABLE marker (x TEXT)")

                with (
                    writer_lock(profile) as lock,
                    pytest.raises(UnsupportedStoresError, match=relative.parts[0]),
                ):
                    back_up(lock, now=NOW)

                assert complete_backup_sets(profile) == ()

    def test_a_lost_store_only_a_damaged_set_holds_does_not_stop_a_backup(
        self,
    ) -> None:
        # A damaged set restores nothing, so it is no reason to wait for a
        # restore, as it is none to refuse a new store (`migrate`).
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            migrate_silver(profile)
            with writer_lock(profile) as lock:
                damaged = back_up(lock, now=NOW - timedelta(days=1))
                (damaged.path / "silver.db").write_bytes(b"damaged")
                for lost in profile.stores.glob("silver.db*"):
                    lost.unlink()

                newest = back_up(lock, now=NOW)

            assert complete_backup_sets(profile) == (newest,)

    def test_files_that_are_not_stores_do_not_stop_a_backup(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            (profile.stores / "notes.txt").write_text("synthetic", encoding="utf-8")
            (profile.stores / "logs").mkdir()

            with writer_lock(profile) as lock:
                backup = back_up(lock, now=NOW)

            assert complete_backup_sets(profile) == (backup,)


def _at(text: str) -> datetime:
    """A UTC time written as `2026-05-02 18:05`."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def _set_names(profile: Profile) -> list[str]:
    """Every folder in the profile's backups folder, by name."""
    return sorted(child.name for child in profile.backup_path(".").iterdir())


class RetentionTests(unittest.TestCase):
    def test_a_new_set_prunes_older_sets_the_policy_does_not_keep(self) -> None:
        # Every set from the last 2 days, then the newest of each day for 10
        # days, then the newest of each month for 3 months, counting this one.
        policy = RetentionPolicy(keep_all_days=2, keep_daily_days=10, keep_monthly=3)
        times = {
            "December, too old": "2025-12-01 09:00",
            "February, newest of its month but too old": "2026-02-27 09:00",
            "March, not the newest of its month": "2026-03-15 09:00",
            "March, the newest of its month": "2026-03-20 09:00",
            "April 10, not the newest of April": "2026-04-10 05:00",
            "April 10, later, still not the newest of April": "2026-04-10 06:00",
            "April 29, not the newest of its day": "2026-04-29 08:00",
            "April 29, the newest of its day": "2026-04-29 20:00",
            "May 1, within two days": "2026-05-01 09:00",
            "May 2, within two days": "2026-05-02 10:00",
        }
        kept = {
            "March, the newest of its month",
            "April 29, the newest of its day",
            "May 1, within two days",
            "May 2, within two days",
        }
        with TemporaryDirectory() as directory:
            profile = replace(household(Path(directory)), retention=policy)
            with writer_lock(profile) as lock:
                written = {
                    case: back_up(lock, now=_at(time)).name
                    for case, time in times.items()
                }
                newest = back_up(lock, now=NOW).name

            assert _set_names(profile) == sorted(
                [newest, *(written[case] for case in kept)]
            )

    def test_monthly_sets_are_kept_forever_by_default(self) -> None:
        policy = RetentionPolicy(keep_all_days=0, keep_daily_days=0)
        with TemporaryDirectory() as directory:
            profile = replace(household(Path(directory)), retention=policy)
            with writer_lock(profile) as lock:
                old = back_up(lock, now=_at("2019-01-31 23:00")).name
                replaced = back_up(lock, now=_at("2026-04-01 09:00")).name
                april = back_up(lock, now=_at("2026-04-30 09:00")).name
                newest = back_up(lock, now=NOW).name

            assert replaced not in _set_names(profile)
            assert _set_names(profile) == sorted([old, april, newest])

    def test_the_new_set_is_kept_whatever_the_policy(self) -> None:
        policy = RetentionPolicy(keep_all_days=0, keep_daily_days=0, keep_monthly=0)
        with TemporaryDirectory() as directory:
            profile = replace(household(Path(directory)), retention=policy)
            with writer_lock(profile) as lock:
                back_up(lock, now=NOW - timedelta(hours=1))
                newest = back_up(lock, now=NOW)

            assert complete_backup_sets(profile) == (newest,)

    def test_a_set_whose_manifest_this_code_cannot_read_is_never_pruned(
        self,
    ) -> None:
        # A later version may record what this one does not know about, such
        # as a legacy publication that needs the set kept.
        policy = RetentionPolicy(keep_all_days=0, keep_daily_days=0, keep_monthly=0)
        with TemporaryDirectory() as directory:
            profile = replace(household(Path(directory)), retention=policy)
            with writer_lock(profile) as lock:
                later_format = back_up(lock, now=NOW - timedelta(days=400))
                document = manifest(later_format.path)
                document["format"] = 2
                (later_format.path / "manifest.json").write_text(
                    json.dumps(document), encoding="utf-8"
                )
                newest = back_up(lock, now=NOW)

            assert _set_names(profile) == sorted([later_format.name, newest.name])

    def test_a_set_of_bronze_alone_stays_complete_and_kept_by_the_policy(
        self,
    ) -> None:
        # Before backups covered Silver, every set held Bronze alone, under
        # the same manifest format. Such a set is still complete, and the
        # policy keeps it as it would any other set of its age.
        policy = RetentionPolicy(keep_all_days=30, keep_daily_days=0, keep_monthly=0)
        with TemporaryDirectory() as directory:
            profile = replace(household(Path(directory)), retention=policy)
            with writer_lock(profile) as lock:
                bronze_only = back_up(lock, now=NOW - timedelta(days=1))
                migrate_silver(profile)
                newest = back_up(lock, now=NOW)

            written = manifest(bronze_only.path)
            assert written["format"] == 1
            assert written["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1}
            }
            assert complete_backup_sets(profile) == (newest, bronze_only)


class RecoveryReleaseTests(unittest.TestCase):
    def test_a_backup_releases_a_held_set_once_its_schema_is_behind(self) -> None:
        # `budget backup` is the documented remedy for a migration whose own
        # backup failed (MigratedWithoutBackupError): the store already
        # migrated, so the set taken before it no longer guards anything
        # once a fresh set of the new schema is written.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                before = back_up(lock, now=NOW - timedelta(days=1))
                hold_for_recovery(lock, before)

                with added_migration("CREATE TABLE marker (x TEXT) STRICT;\n"):
                    migrate_bronze(profile)
                    back_up(lock, now=NOW)

            assert not profile.recovery_sets_file.exists()

    def test_a_backup_releases_a_held_set_once_its_silver_schema_is_behind(
        self,
    ) -> None:
        # As above, after a migration that changed only Silver's schema.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            migrate_silver(profile)
            with writer_lock(profile) as lock:
                before = back_up(lock, now=NOW - timedelta(days=1))
                hold_for_recovery(lock, before)

                with added_migration(
                    "CREATE TABLE marker (x TEXT) STRICT;\n", folder=SILVER_MIGRATIONS
                ):
                    migrate_silver(profile)
                    back_up(lock, now=NOW)

            assert not profile.recovery_sets_file.exists()

    def test_a_held_set_without_silver_stays_held_once_silver_starts(
        self,
    ) -> None:
        # A set written before Silver had a store records no Silver version,
        # so a later set holding Silver says nothing about its migration.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                before = back_up(lock, now=NOW - timedelta(days=1))
                hold_for_recovery(lock, before)

                migrate_silver(profile)
                back_up(lock, now=NOW)

            held = json.loads(profile.recovery_sets_file.read_bytes())
            assert held["sets"] == [before.name]

    def test_an_unreadable_recovery_file_is_never_silently_replaced(self) -> None:
        # A hold that cannot be read might be hiding a set another operation
        # still needs (decision 7): overwriting it would drop that
        # protection, so the file is left exactly as it was.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                before = back_up(lock, now=NOW)
                profile.recovery_sets_file.parent.mkdir(parents=True, exist_ok=True)
                profile.recovery_sets_file.write_bytes(b"not json")

                with pytest.raises(BackupWriteError, match=r"recovery-sets\.json"):
                    hold_for_recovery(lock, before)

            assert profile.recovery_sets_file.read_bytes() == b"not json"

    def test_a_recovery_file_that_cannot_be_written_refuses_cleanly(self) -> None:
        # A plain OSError from this write must not escape as a traceback: it
        # has to become the same kind of refusal an unreadable file gets,
        # and the schema-changing step this guards must never run.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                before = back_up(lock, now=NOW)
                partial = profile.recovery_sets_file.with_name(
                    profile.recovery_sets_file.name + PUBLISHING_SUFFIX
                )
                partial.mkdir()

                with pytest.raises(BackupWriteError):
                    hold_for_recovery(lock, before)

            assert not profile.recovery_sets_file.exists()


class FailedBackupTests(unittest.TestCase):
    def test_a_set_that_cannot_be_written_leaves_nothing_behind(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = household(root)
            # Where the backups folder should be, a file stands.
            (root / "backups").write_bytes(b"not a folder")

            with (
                writer_lock(profile) as lock,
                pytest.raises(BackupWriteError, match="nothing was published"),
            ):
                back_up(lock, now=NOW)

            assert list(profile.backup_staging.iterdir()) == []
            assert (root / "backups").read_bytes() == b"not a folder"

    def test_a_set_never_replaces_one_with_its_name(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                first = back_up(lock, now=NOW)
                kept = manifest(first.path)
                import_one(lock)

                with pytest.raises(BackupWriteError):
                    back_up(lock, now=NOW)

            assert manifest(first.path) == kept
            assert complete_backup_sets(profile) == (first,)
            assert list(profile.backup_staging.iterdir()) == []


if __name__ == "__main__":
    unittest.main()
