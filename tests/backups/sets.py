# Copyright 2026 Therkel
"""Read a backup set the way a test checks it: without the code under test.

A set's store is opened read-only and immutable, so reading it never writes
a WAL or shared-memory file into the set.
"""

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from unittest import mock

from budget.importing import Coverage, import_inbox_file
from budget.locking import WriterLock
from budget.profiles import Profile
from tests.importing.households import drop, payload

NOW = datetime(2026, 5, 2, 18, 5, 11, 120731, tzinfo=UTC)
COVERAGE = Coverage(covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 2))


def import_one(lock: WriterLock, name: str = "export-20260502.csv") -> str:
    """Import one synthetic export for `joint-current`; return its run."""
    source = drop(lock.profile, "joint-current", name, payload("01.04.2026"))
    return import_inbox_file(lock, source, COVERAGE).import_run.import_run_id


def run_ids(store: Path) -> list[str]:
    """The import runs a store file holds, read without changing the file."""
    uri = f"{store.as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute("SELECT import_run_id FROM import_runs")
        return [str(row[0]) for row in rows]


def copied_run_ids(store: Path, folder: Path) -> list[str]:
    """The runs a plain file copy of a live store holds, ignoring its WAL."""
    copy = folder / "copied.db"
    shutil.copyfile(store, copy)
    return run_ids(copy)


def tables(store: Path) -> list[str]:
    """The tables a store file holds, read without changing the file."""
    uri = f"{store.as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [str(row[0]) for row in rows]


def user_version(store: Path) -> int:
    """A store file's schema version, read without changing the file."""
    uri = f"{store.as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def manifest(set_folder: Path) -> dict[str, object]:
    """A set's `manifest.json`."""
    text = (set_folder / "manifest.json").read_text(encoding="utf-8")
    document: dict[str, object] = dict(json.loads(text).items())
    return document


def checksum(path: Path) -> dict[str, object]:
    """What a manifest says about one file: its SHA-256 and its length."""
    content = path.read_bytes()
    return {"sha256": sha256(content).hexdigest(), "bytes": len(content)}


@contextmanager
def damaged_rereads(folder: Path, name: str) -> Iterator[None]:
    """Make every read of a file after its first return one changed byte.

    It stands for a copy the disk got wrong: the first read is the one a
    backup checksums, and later reads are what it copies. Only the stdlib
    read boundary, `pathlib.Path.read_bytes`, is replaced, and only for files
    called `name` inside `folder`.
    """
    original = Path.read_bytes
    reads: dict[Path, int] = {}

    def read_bytes(path: Path) -> bytes:
        content = original(path)
        if path.name != name or not path.resolve().is_relative_to(folder):
            return content
        reads[path] = reads.get(path, 0) + 1
        if reads[path] == 1:
            return content
        return content[:-1] + bytes([content[-1] ^ 0xFF])

    with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes):
        yield


def holding(profile: Profile) -> sqlite3.Connection:
    """Open a reader on the live store, so a commit stays in its WAL file.

    SQLite moves the WAL into the store file when its last connection
    closes; a reader held open across a write keeps it from doing so.
    """
    connection = sqlite3.connect(profile.bronze_store)
    connection.execute("SELECT count(*) FROM import_runs").fetchone()
    return connection
