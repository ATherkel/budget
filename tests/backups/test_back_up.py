# Copyright 2026 Therkel
"""Backup sets: a complete, checked copy of a profile, written whole or not at all.

Every profile here is a synthetic test profile in a temporary folder; no test
opens a production store or reads a real export.
"""

import shutil
import tomllib
import unittest
from contextlib import closing
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import back_up, complete_backup_sets
from budget.locking import writer_lock
from tests.backups.sets import (
    NOW,
    checksum,
    copied_run_ids,
    holding,
    import_one,
    manifest,
    run_ids,
)
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


if __name__ == "__main__":
    unittest.main()
