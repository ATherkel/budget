# Copyright 2026 Therkel
"""The `restore` application operation: put a whole profile back from one set.

Every store a backup set lists is restored together, into a profile that has
no stores; a store is never restored beside live ones (`operations.md`,
*Backup and Restore*).
"""

import json
import os
import shutil
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.bronze import BronzeStore
from budget.bronze.storage import bronze_stage
from budget.decision_log import read_decision_log
from budget.durability import sync_folder
from budget.gold.storage import gold_stage
from budget.inputs import ConfigurationError
from budget.locking import WriterLock
from budget.profiles import (
    BRONZE_STORE_NAME,
    DECISION_LOG_FILE_NAME,
    INPUTS_FOLDER,
    Profile,
)
from budget.replaying import (
    REPLAY_REFUSALS,
    ImportLogInvalidError,
    NotALogPrefixError,
    RunConflictError,
    check_log_continues,
    replay_import_log,
)
from budget.silver.storage import silver_stage
from budget.sqlstore import StageStore, StoreError, migrate_store, open_store_snapshot

# Where a restore copies a set's stores before moving them into place.
RESTORE_STAGING: Final = "restore-staging"
# Present while a restore has moved, or is moving, stores into place.
RESTORE_MARKER: Final = "restore-in-progress.json"
RESTORE_MARKER_FORMAT: Final = 1
# A store file and the files SQLite keeps beside it.
_STORE_FILE_SUFFIXES: Final = ("", "-wal", "-shm", "-journal")
# Gold's legacy extracts (operations.md, *Where production lives*).
_LEGACY_GOLD_FOLDER: Final = "gold"
_STAGES: Final[dict[str, Callable[[Profile], StageStore]]] = {
    "bronze": bronze_stage,
    "silver": silver_stage,
    "gold": gold_stage,
}


class RestoreWriteError(RuntimeError):
    """The set's stores could not be copied into place: none was restored."""

    def __init__(self, reason: str) -> None:
        """Say why, and that no store came of it."""
        super().__init__(
            f"the backup set could not be restored: {reason}; nothing was restored"
        )


class UnknownStageError(StoreError):
    """The set lists a store for a stage this code does not know.

    Newer code wrote it: restoring the rest without it would drop a store.
    """

    def __init__(self, name: str, stage: str) -> None:
        """Name the set and the stage."""
        super().__init__(
            f"backup set {name} lists a {stage} store, which this code does "
            "not know; nothing was restored"
        )


class NoUsableSetError(RuntimeError):
    """No complete set of the profile can be restored: nothing was restored."""

    def __init__(self, skipped: list[str]) -> None:
        """Name every complete set passed over, if any."""
        passed = f": passed over {', '.join(skipped)}" if skipped else ""
        super().__init__(
            f"there is no complete backup set this code can read{passed}; "
            "nothing was restored"
        )


class IncompleteSetError(RuntimeError):
    """The set asked for by name is not complete: nothing was restored.

    A set asked for by name is never swapped for another one.
    """

    def __init__(self, name: str) -> None:
        """Name the set, and say that nothing was restored."""
        super().__init__(
            f"backup set {name} is not complete: it is missing, or a file does "
            "not match the checksum its manifest records; nothing was restored"
        )


class OccupiedProfileError(RuntimeError):
    """The profile still has a store: nothing was restored or deleted.

    A whole profile is restored, never one store beside live ones, and the
    stores already there are the operator's to keep or set aside.
    """

    def __init__(self, names: list[str]) -> None:
        """Name what is in the way, and how to retry."""
        super().__init__(
            f"the stores folder still holds {', '.join(names)}: restore puts "
            "back a whole profile, never a store beside live ones; move every "
            "store out of it, keeping them if they may be needed, then rerun; "
            "nothing was restored"
        )


def _store_files(profile: Profile) -> list[Path]:
    """Name every stage store file and the SQLite files kept beside each."""
    stores = (profile.bronze_store, profile.silver_store, profile.gold_store)
    return [
        store.with_name(store.name + suffix)
        for store in stores
        for suffix in _STORE_FILE_SUFFIXES
    ]


def _require_no_stores(profile: Profile) -> None:
    """Refuse a profile that has any stage store, touching nothing.

    A store's write-ahead log, shared-memory or rollback journal file counts
    too: SQLite would apply a leftover log to the store restored beside it.
    So does Gold's `gold` folder of legacy extracts.
    """
    candidates = [*_store_files(profile), profile.stores / _LEGACY_GOLD_FOLDER]
    found = [path.name for path in candidates if path.exists()]
    if found:
        raise OccupiedProfileError(found)


@dataclass(frozen=True)
class Restored:
    """What `restore` did: the set, the newer sets passed over, the inputs put back.

    `put_back` names each household input the profile had lost, by its path
    in the set, which was copied from the set. `replayed` counts the import
    runs restored from the export archive beyond the set.
    """

    backup: BackupSet
    skipped: tuple[str, ...]
    put_back: tuple[str, ...]
    replayed: int

    @property
    def decisions_lost(self) -> bool:
        """Whether the decision log was missing, so its set copy stands in.

        Decisions recorded after the set are then lost: a recovery limit.
        """
        return f"{INPUTS_FOLDER}/{DECISION_LOG_FILE_NAME}" in self.put_back


class DamagedStoreError(RuntimeError):
    """A store in the set fails SQLite's integrity check: nothing was restored.

    Its checksum can match while its pages do not, as when the store was
    already damaged when the set was taken.
    """

    def __init__(self, store: str, name: str) -> None:
        """Name the store and the set, and say that nothing was restored."""
        super().__init__(
            f"{store} in backup set {name} fails SQLite's integrity check; "
            "nothing was restored"
        )


def _is_intact(connection: sqlite3.Connection) -> bool:
    """Report whether SQLite's integrity check finds the database sound."""
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError:
        return False
    return [tuple(row) for row in rows] == [("ok",)]


def _require_readable(profile: Profile, backup: BackupSet) -> None:
    """Refuse a set holding a store this code cannot open, touching nothing.

    A store at a schema version this code does not know is a `StoreError`;
    one SQLite finds damaged is a `DamagedStoreError`.
    """
    for stage, name in set_store_files(backup).items():
        if stage not in _STAGES:
            raise UnknownStageError(backup.name, stage)
        path = backup.path / name
        try:
            snapshot = open_store_snapshot(_STAGES[stage](profile), path)
        except sqlite3.DatabaseError:
            raise DamagedStoreError(name, backup.name) from None
        with closing(snapshot) as store:
            if not _is_intact(store):
                raise DamagedStoreError(name, backup.name)


def _named(profile: Profile, sets: tuple[BackupSet, ...], name: str) -> BackupSet:
    """Return the complete set named `name`, refusing it if it cannot be read."""
    for found in sets:
        if found.name == name:
            _require_readable(profile, found)
            return found
    raise IncompleteSetError(name)


def _newest_readable(
    profile: Profile, sets: tuple[BackupSet, ...]
) -> tuple[BackupSet, tuple[str, ...]]:
    """Return the newest set this code can read, and the newer ones passed over."""
    skipped: list[str] = []
    for found in sets:
        try:
            _require_readable(profile, found)
        except (StoreError, DamagedStoreError):
            skipped.append(found.name)
            continue
        return found, tuple(skipped)
    raise NoUsableSetError(skipped)


def _migrate_staged(profile: Profile, stage: str, staged: Path) -> None:
    """Upgrade a staged copy of a store the set holds at an older version.

    The set itself is the copy from before the change, so no backup is
    taken first: one would compare the live import log with a Bronze that
    catch-up has yet to bring up to it.
    """
    store = replace(_STAGES[stage](profile), path=staged)
    migrate_store(store, before_migrating=lambda: None)


def _mark_unfinished(profile: Profile, backup: BackupSet) -> None:
    """Record, durably, that a restore is about to move stores into place.

    Until it is removed, every store in the stores folder is one this
    restore put there, never one of the operator's.
    """
    marker = profile.stores / RESTORE_MARKER
    content = json.dumps({"format": RESTORE_MARKER_FORMAT, "set": backup.name})
    with marker.open("w", encoding="utf-8") as file:
        file.write(content + "\n")
        file.flush()
        os.fsync(file.fileno())
    sync_folder(profile.stores)


class DecisionLogDivergedError(RuntimeError):
    """The live decision log does not begin with the set's copy.

    It is shorter, or was rewritten: it may have lost decisions, or be the
    newer truth. Neither is replaced; the choice is the operator's.
    """

    def __init__(self, name: str) -> None:
        """Name the set, and what to do."""
        super().__init__(
            "the live decision log does not begin with the backup set's copy "
            f"in {name}: it may have lost decisions the set holds; both are "
            "kept as they are. Put back the log to keep, then rerun "
            "`budget restore`; nothing was restored"
        )


class DecisionLogDamagedError(RuntimeError):
    """The live decision log does not read: no decision of it is dropped."""

    def __init__(self, problems: Exception) -> None:
        """Say what is wrong with it, and what to do."""
        super().__init__(
            f"the live decision log is damaged: {problems}; it is kept as it "
            "is, beside the backup set's copy. Repair it, then rerun "
            "`budget restore`; nothing was restored"
        )


def _require_decision_log_extends(profile: Profile, backup: BackupSet) -> None:
    """Refuse, touching nothing, a live decision log the set's does not begin.

    Only the set copy's complete lines count: a final line a crash cut off
    was not an entry yet. A live log that is absent is not refused here.
    """
    live = profile.input_file(DECISION_LOG_FILE_NAME)
    copy = backup.path / INPUTS_FOLDER / DECISION_LOG_FILE_NAME
    try:
        current = live.read_bytes()
    except FileNotFoundError:
        return
    recorded = copy.read_bytes() if copy.is_file() else b""
    if not current.startswith(recorded[: recorded.rfind(b"\n") + 1]):
        raise DecisionLogDivergedError(backup.name)
    try:
        read_decision_log(profile)
    except ConfigurationError as error:
        raise DecisionLogDamagedError(error) from None


class ImportLogDisagreesError(RuntimeError):
    """The live import log does not continue the set's Bronze: nothing is touched.

    The log is kept as it is: it may list runs no set holds, which only the
    operator can decide to give up.
    """

    def __init__(self, name: str, reason: str) -> None:
        """Name the set and the disagreement, and what to do."""
        super().__init__(
            f"the live import log does not agree with backup set {name}: "
            f"{reason}; it is kept as it is. Correct it, or choose another "
            "set, then rerun `budget restore`; nothing was restored"
        )


# What each refusal of `check_log_continues` means for a restore.
_DISAGREEMENTS: Final[dict[type[Exception], str]] = {
    ImportLogInvalidError: "an entry does not read as a logged run",
    RunConflictError: "it records a run the set holds differently",
    NotALogPrefixError: "the set holds runs it does not list first",
}


def _require_import_log_continues(profile: Profile, backup: BackupSet) -> bool:
    """Refuse, touching nothing, a live import log the set's Bronze cannot continue.

    Returns whether the log lists runs beyond the set, to replay.
    """
    with BronzeStore(profile, snapshot=backup.path / BRONZE_STORE_NAME) as snapshot:
        held = snapshot.import_runs()
    try:
        return check_log_continues(profile, held)
    except (ImportLogInvalidError, RunConflictError, NotALogPrefixError) as error:
        raise ImportLogDisagreesError(
            backup.name, _DISAGREEMENTS[type(error)]
        ) from None


class CatchUpRefusedError(RuntimeError):
    """The live import log does not agree with the restored set.

    The stores are in place, but the restore has not finished: the live log
    is kept as it is, for the operator to correct or set aside.
    """

    def __init__(self, name: str, reason: Exception) -> None:
        """Name the set, the replay's reason, and what to do."""
        super().__init__(
            f"backup set {name} was put in place, but the live import log does "
            f"not agree with it: {reason} The import log is kept as it is, and "
            "the restore has not finished: correct the log or move it aside, "
            "then rerun `budget restore`"
        )


class UnfinishedRestoreError(RuntimeError):
    """A restore has not finished: its stores are not a profile to use yet."""

    def __init__(self, name: str) -> None:
        """Name the set being restored, and what to do."""
        super().__init__(
            f"a restore of backup set {name} has not finished; rerun "
            "`budget restore`; nothing was changed"
        )


def require_no_unfinished_restore(profile: Profile) -> None:
    """Refuse, touching nothing, a profile an unfinished restore left.

    A marker that cannot be read still marks one; its set is then unnamed.
    """
    marker = profile.stores / RESTORE_MARKER
    if not marker.exists():
        return
    raise UnfinishedRestoreError(_marked_set(marker))


def _marked_set(marker: Path) -> str:
    """Return the set a restore marker names, or say it cannot be read."""
    try:
        name = json.loads(marker.read_text(encoding="utf-8")).get("set")
    except (OSError, ValueError, AttributeError):
        name = None
    return str(name) if isinstance(name, str) else "(unreadable marker)"


def _clear_unfinished(profile: Profile) -> None:
    """Remove what an unfinished restore moved into place, then its marker.

    Only the stores, their SQLite files and the marker are removed: the
    marker says no store in the folder is the operator's.
    """
    marker = profile.stores / RESTORE_MARKER
    if not marker.exists():
        return
    try:
        for store in _store_files(profile):
            store.unlink(missing_ok=True)
        marker.unlink()
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None


def _copy_whole(
    profile: Profile, backup: BackupSet, stores: Mapping[str, str]
) -> tuple[str, ...]:
    """Copy every store of a set into the stores folder, or none of them.

    Each store is copied into a staging folder beside the live ones first,
    and upgraded there, and moved into place only once every copy is ready,
    so a copy that fails leaves no store a retry would find in its way. Lost
    inputs are put back only then, so such a failure leaves them alone too.
    Returns each input put back.
    """
    staging = profile.stores / RESTORE_STAGING
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for stage, store in stores.items():
            shutil.copyfile(backup.path / store, staging / store)
            _migrate_staged(profile, stage, staging / store)
        put_back = _put_back_lost_inputs(profile, backup)
        _mark_unfinished(profile, backup)
        for store in stores.values():
            (staging / store).replace(profile.stores / store)
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return put_back


def _put_back_lost_inputs(profile: Profile, backup: BackupSet) -> tuple[str, ...]:
    """Copy each household input the profile lacks from the set's copy.

    The live inputs, synchronised apart from the stores, are newer than any
    set, so a file that survived is never replaced. Only missing files are
    copied, so a restore cut off here leaves nothing a retry must undo.
    Returns each file put back, by its path in the set.
    """
    copies = backup.path / INPUTS_FOLDER
    if not copies.is_dir():
        return ()
    put_back = []
    try:
        for copy in sorted(copies.rglob("*")):
            relative = copy.relative_to(copies).as_posix()
            live = profile.input_file(relative)
            if copy.is_file() and not live.exists():
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(copy, live)
                put_back.append(f"{INPUTS_FOLDER}/{relative}")
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None
    return tuple(put_back)


def restore(lock: WriterLock, name: str | None = None) -> Restored:
    """Restore every store of one complete set; report what was restored.

    `name` selects the set; without it, the newest complete set this code
    can read is taken, and every newer set is passed over.
    """
    profile = lock.profile
    _clear_unfinished(profile)
    _require_no_stores(profile)
    sets = complete_backup_sets(profile)
    if name is None:
        selected, skipped = _newest_readable(profile, sets)
    else:
        selected, skipped = _named(profile, sets, name), ()
    _require_decision_log_extends(profile, selected)
    log_runs_ahead = _require_import_log_continues(profile, selected)
    stores = set_store_files(selected)
    put_back = _copy_whole(profile, selected, stores)
    # Catch up: every run the live import log lists beyond the set comes
    # back from the export archive, as logged (`replay_import_log`).
    replayed: tuple[object, ...] = ()
    if log_runs_ahead:
        try:
            replayed = replay_import_log(lock)
        except REPLAY_REFUSALS as error:
            raise CatchUpRefusedError(selected.name, error) from error
    (profile.stores / RESTORE_MARKER).unlink()
    return Restored(
        backup=selected, skipped=skipped, put_back=put_back, replayed=len(replayed)
    )
