# Copyright 2026 Therkel
"""The profile's writer lock: one writing command at a time.

A writing command locks `budget.lock` in the profile's stores folder for its
whole run. The lock is taken without waiting, so a second writing command
refuses at once. It is the operating system's own file lock, which the system
releases when the process ends, however it ends.
"""

import errno
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from budget.profiles import Profile


class WriterLockHeldError(RuntimeError):
    """Another writing command holds the profile's writer lock."""

    def __init__(self) -> None:
        """Say what to do, since nothing was written."""
        super().__init__(
            "another command is running: nothing was written; rerun when it ends"
        )


class StoresFolderUnavailableError(RuntimeError):
    """The stores folder cannot hold the writer lock: a rerun will not help."""

    def __init__(self, folder: Path, error: OSError) -> None:
        """Name the folder and the operating system's reason."""
        reason = error.strerror or type(error).__name__
        super().__init__(f"the stores folder {folder} cannot be used: {reason}")


class WriterLockReleasedError(RuntimeError):
    """A write was attempted with a writer lock whose `with` block has ended."""


@dataclass(frozen=True)
class WriterLock:
    """What `writer_lock` hands its `with` block: the profile it locked.

    An operation that writes takes this instead of a bare profile, so it
    cannot be called without the lock held for that profile.
    """

    profile: Profile


if sys.platform == "win32":
    import msvcrt

    def _try_lock(file: BinaryIO) -> bool:
        """Lock the file's first byte without waiting; report success."""
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            # Contention is EACCES; any other failure is not another command.
            if error.errno == errno.EACCES:
                return False
            raise
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
def writer_lock(profile: Profile) -> Iterator[WriterLock]:
    """Hold the profile's writer lock for the length of a `with` block.

    Raises `WriterLockHeldError` at once when another command holds it, and
    `StoresFolderUnavailableError` when the folder cannot hold the lock at all.
    """
    path = profile.writer_lock_file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode creates the file without truncating one another holds.
        file = path.open("a+b")
    except OSError as error:
        raise StoresFolderUnavailableError(path.parent, error) from None
    with file:
        try:
            locked = _try_lock(file)
        except OSError as error:
            raise StoresFolderUnavailableError(path.parent, error) from None
        if not locked:
            raise WriterLockHeldError
        try:
            yield WriterLock(profile)
        finally:
            _unlock(file)
