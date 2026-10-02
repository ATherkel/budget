# Copyright 2026 Therkel
"""Altered packaged migrations, for tests of what a broken migration does."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


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
