# Copyright 2026 Therkel
"""The profile's writer lock: one writing command at a time.

A writing command locks `budget.lock` in the profile's stores folder for its
whole run. The lock is taken without waiting, so a second writing command
refuses at once. It is the operating system's own file lock, which the system
releases when the process ends, however it ends.
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

from budget.profiles import Profile


class WriterLockHeldError(RuntimeError):
    """Another writing command holds the profile's writer lock."""

    def __init__(self) -> None:
        """Say what to do, since nothing was written."""
        super().__init__(
            "another command is running: nothing was written; rerun when it ends"
        )


if sys.platform == "win32":
    import msvcrt

    def _try_lock(file: BinaryIO) -> bool:
        """Lock the file's first byte without waiting; report success."""
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(file: BinaryIO) -> None:
        """Release the byte `_try_lock` locked."""
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(file: BinaryIO) -> bool:
        """Lock the whole file without waiting; report success."""
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(file: BinaryIO) -> None:
        """Release the lock `_try_lock` took."""
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@contextmanager
def writer_lock(profile: Profile) -> Iterator[None]:
    """Hold the profile's writer lock for the length of a `with` block.

    Raises `WriterLockHeldError` at once when another command holds it.
    """
    path = profile.writer_lock_file
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append mode creates the file without truncating one another holds.
    with path.open("a+b") as file:
        if not _try_lock(file):
            raise WriterLockHeldError
        try:
            yield
        finally:
            _unlock(file)
