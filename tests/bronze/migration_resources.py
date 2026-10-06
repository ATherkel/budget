# Copyright 2026 Therkel
"""Altered packaged migrations, for tests of what a broken migration does."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from budget.bronze import storage


@contextmanager
def patched_resources(suffix: str) -> Iterator[None]:
    """Patch the stdlib read boundary so the real resource gains a suffix.

    Discovery, the loader, the runner, the transaction and the foreign-key check
    all stay the real code; only `pathlib.Path.read_text` is replaced, and only
    for the packaged `0001` file, which is returned with `suffix` appended.
    """
    original = Path.read_text

    def read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        text = original(path, encoding, errors)
        if path.name.startswith("0001_"):
            return text + suffix
        return text

    with mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text):
        yield


# Where the installed package keeps the Bronze migrations.
MIGRATIONS = Path(storage.__file__).resolve().parent.parent / "migrations" / "bronze"


@contextmanager
def added_migration(sql: str, *, folder: Path = MIGRATIONS) -> Iterator[None]:
    """Package one more migration after a stage's real ones, holding `sql`.

    `folder` is the stage's packaged migrations folder, Bronze's by default.
    Only the stdlib boundaries are replaced: `pathlib.Path.glob` lists the
    added file beside the packaged ones, and `pathlib.Path.read_text` returns
    `sql` for it. Discovery, the runner and the transaction stay the real
    code, so a store migrated inside the block is one version newer.
    """
    added = folder / f"{len(list(folder.glob('*.sql'))) + 1:04d}_added.sql"
    original_glob = Path.glob
    original_read_text = Path.read_text

    def glob(
        path: Path, pattern: str, *, case_sensitive: bool | None = None
    ) -> Iterator[Path]:
        found = list(original_glob(path, pattern, case_sensitive=case_sensitive))
        if path == folder and pattern == "*.sql":
            found.append(added)
        return iter(found)

    def read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == added:
            return sql
        return original_read_text(path, encoding, errors)

    with (
        mock.patch.object(Path, "glob", autospec=True, side_effect=glob),
        mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text),
    ):
        yield


# Where the installed package keeps the Silver migrations, for `added_migration`.
SILVER_MIGRATIONS = MIGRATIONS.parent / "silver"
