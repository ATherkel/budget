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
from datetime import datetime
from pathlib import Path
from typing import Final

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.bronze import BronzeStore
from budget.bronze.storage import bronze_stage
from budget.codeversion import UncommittedCodeError
from budget.decision_log import read_decision_log
from budget.durability import sync_folder
from budget.gold.storage import GOLD_STAGE, gold_stage
from budget.gold.store import GoldStore, RecoveryBoundary
from budget.inputs import ConfigurationError
from budget.locking import WriterLock
from budget.profiles import (
    BRONZE_STORE_NAME,
    DECISION_LOG_FILE_NAME,
    IMPORT_LOG_FILE_NAME,
    INPUTS_FOLDER,
    Profile,
)
from budget.rebuilding import GoldRebuild, rebuild_through_gold
from budget.replaying import (
    REPLAY_REFUSALS,
    ArchivedExportMismatchError,
    ArchivedExportMissingError,
    ImportLogInvalidError,
    NotALogPrefixError,
    RunConflictError,
    check_log_continues,
    replay_import_log,
)
from budget.silver.storage import SILVER_STAGE, silver_stage
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
class UndoAfterCatchUp:
    """Where undo goes after a catch-up build published (`publications.md`).

    Undo returns to `publication_id`, the set's current publication, while
    its result is `usable`; never to one lost after the set. The undo
    command is #177's: this names where its first step from the catch-up
    build must land, which is the pointer's move before that build.
    """

    publication_id: int
    usable: bool


def _start_missing_stages(
    profile: Profile, stores: Mapping[str, str]
) -> tuple[str, ...]:
    """Start each later stage's store the set does not hold; name those stages.

    The set is the copy from before the change, so no backup is taken first.
    """
    started = []
    for stage in (SILVER_STAGE, GOLD_STAGE):
        if stage not in stores:
            migrate_store(
                _STAGES[stage](profile), new_store=True, before_migrating=lambda: None
            )
            started.append(stage)
    return tuple(started)


def _undo_after_catch_up(
    profile: Profile, boundary: RecoveryBoundary, gold: GoldRebuild
) -> UndoAfterCatchUp | None:
    """Name undo's target once catch-up has published, or None.

    Without a build, the restored pointer history keeps its ordinary undo.
    A set without a publication leaves undo nothing to return to.
    """
    target = boundary.restored_current_id
    if not gold.published or target is None:
        return None
    with GoldStore(profile) as gold_store:
        retained = {found.publication_id for found in gold_store.available()}
    return UndoAfterCatchUp(publication_id=target, usable=target in retained)


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
    missing_logs: tuple[str, ...]
    decision_line_cut_off: bool
    gold: GoldRebuild | None
    undo: UndoAfterCatchUp | None
    started: tuple[str, ...] = ()

    @property
    def gold_started(self) -> bool:
        """Whether the set held no Gold store, so Gold began anew."""
        return GOLD_STAGE in self.started

    @property
    def decisions_lost(self) -> bool:
        """Whether the decision log was missing, so only the set's copy stands in.

        Decisions recorded after the set are then lost: a recovery limit.
        """
        return DECISION_LOG_FILE_NAME in self.missing_logs

    @property
    def imports_lost(self) -> bool:
        """Whether the import log was missing, so only the set's copy stands in.

        Runs imported after the set are then not restored: a recovery limit.
        """
        return IMPORT_LOG_FILE_NAME in self.missing_logs


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


def newest_readable(
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


def _mark_unfinished(
    profile: Profile, backup: BackupSet, put_back: tuple[str, ...]
) -> None:
    """Record, durably, that a restore is about to move stores into place.

    Until it is removed, every store in the stores folder is one this
    restore put there, never one of the operator's. `put_back` names the
    inputs it puts back from the set, so a retry still reports them.
    """
    marker = profile.stores / RESTORE_MARKER
    content = json.dumps(
        {
            "format": RESTORE_MARKER_FORMAT,
            "set": backup.name,
            "put_back": list(put_back),
        }
    )
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


def _ends_cut_off(log: Path) -> bool:
    """Report whether a log's final line lacks its line feed, as a crash leaves it.

    Such a line counts as never written (`operations.md`, *Failure and
    Retry*); restore reports it and leaves it for the operator to delete.
    """
    try:
        content = log.read_bytes()
    except FileNotFoundError:
        return False
    return bool(content) and not content.endswith(b"\n")


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
        """Name the set, what catch-up found, and what to do."""
        found = _CATCH_UP_PROBLEMS.get(
            type(reason), "a run the import log lists could not be replayed"
        )
        super().__init__(
            f"backup set {name} is in place, but catch-up stopped: {found}. "
            "The import log is kept as it is, and the restore has not "
            "finished: put the export back where the log says, then rerun "
            "`budget restore`"
        )


# What a replay refusal found, once the log is known to continue the set.
_CATCH_UP_PROBLEMS: Final[dict[type[Exception], str]] = {
    ArchivedExportMissingError: "a run the import log lists has no export in "
    "the archive",
    ArchivedExportMismatchError: "a run the import log lists has an archived "
    "export that does not match its hash",
}


def _build_refused(name: str, reason: Exception) -> str:
    """Say a catch-up build was refused, and that the restore is unfinished.

    The build's own refusal ends by saying nothing was written, which is
    true of its build but not of the restore: the stores are in place.
    """
    found = str(reason).removesuffix("; nothing was written")
    return (
        f"backup set {name} is in place, but its catch-up build was refused: "
        f"{found}; the restore has not finished: put that right, then rerun "
        "`budget restore`"
    )


class CatchUpInputsRefusedError(RuntimeError):
    """The household's inputs refuse the catch-up build: restore is unfinished."""

    def __init__(self, name: str, reason: Exception) -> None:
        """Name the set, the build's refusal, and what to do."""
        super().__init__(_build_refused(name, reason))


class CatchUpCodeRefusedError(RuntimeError):
    """The running code cannot build production: restore is unfinished."""

    def __init__(self, name: str, reason: Exception) -> None:
        """Name the set, the build's refusal, and what to do."""
        super().__init__(_build_refused(name, reason))


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


def _marked_put_back(marker: Path) -> tuple[str, ...]:
    """Return the inputs an unfinished restore's marker says it put back."""
    try:
        put_back = json.loads(marker.read_text(encoding="utf-8")).get("put_back")
    except (OSError, ValueError, AttributeError):
        return ()
    if not isinstance(put_back, list):
        return ()
    return tuple(str(path) for path in put_back)


def _clear_unfinished(profile: Profile) -> tuple[str, ...]:
    """Remove what an unfinished restore moved into place, then its marker.

    Only the stores, their SQLite files and the marker are removed: the
    marker says no store in the folder is the operator's. Returns the inputs
    that restore put back, which are still only the set's copies.
    """
    marker = profile.stores / RESTORE_MARKER
    if not marker.exists():
        return ()
    put_back = _marked_put_back(marker)
    try:
        for store in _store_files(profile):
            store.unlink(missing_ok=True)
        marker.unlink()
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None
    return put_back


def _copy_whole(
    profile: Profile,
    backup: BackupSet,
    stores: Mapping[str, str],
    earlier: tuple[str, ...],
) -> tuple[str, ...]:
    """Copy every store of a set into the stores folder, or none of them.

    Each store is copied into a staging folder beside the live ones first,
    and upgraded there, and moved into place only once every copy is ready,
    so a copy that fails leaves no store a retry would find in its way. Lost
    inputs are put back only then, so such a failure leaves them alone too.
    The marker records them first, with `earlier`, those an unfinished
    restore put back. Returns every input put back, `earlier` first.
    """
    staging = profile.stores / RESTORE_STAGING
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for stage, store in stores.items():
            shutil.copyfile(backup.path / store, staging / store)
            _migrate_staged(profile, stage, staging / store)
        lost = _lost_inputs(profile, backup)
        put_back = (*earlier, *(name for name in lost if name not in earlier))
        _mark_unfinished(profile, backup, put_back)
        for name, copy in lost.items():
            live = profile.input_file(name.removeprefix(f"{INPUTS_FOLDER}/"))
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(copy, live)
        for store in stores.values():
            (staging / store).replace(profile.stores / store)
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return put_back


def _lost_inputs(profile: Profile, backup: BackupSet) -> dict[str, Path]:
    """Name each household input the profile lacks and the set holds a copy of.

    The live inputs, synchronised apart from the stores, are newer than any
    set, so a file that survived is never replaced. Maps each file's path in
    the set to the set's copy.
    """
    copies = backup.path / INPUTS_FOLDER
    if not copies.is_dir():
        return {}
    return {
        f"{INPUTS_FOLDER}/{relative}": copy
        for copy in sorted(copies.rglob("*"))
        if copy.is_file()
        and not profile.input_file(
            relative := copy.relative_to(copies).as_posix()
        ).exists()
    }


def restore(lock: WriterLock, name: str | None = None, *, now: datetime) -> Restored:
    """Restore every store of one complete set; report what was restored.

    `name` selects the set; without it, the newest complete set this code
    can read is taken, and every newer set is passed over.
    """
    profile = lock.profile
    sets = complete_backup_sets(profile)
    if name is None:
        selected, skipped = newest_readable(profile, sets)
    else:
        selected, skipped = _named(profile, sets, name), ()
    _require_decision_log_extends(profile, selected)
    decision_line_cut_off = _ends_cut_off(profile.input_file(DECISION_LOG_FILE_NAME))
    log_runs_ahead = _require_import_log_continues(profile, selected)
    # Only now is an unfinished restore's work cleared: a refusal above keeps
    # its marker, and with it the record of the inputs it put back.
    earlier = _clear_unfinished(profile)
    _require_no_stores(profile)
    stores = set_store_files(selected)
    put_back = _copy_whole(profile, selected, stores, earlier)
    # A log the profile lost and the set holds: only the set's copy stands
    # in. A log neither has was never written, so nothing of it is lost.
    missing_logs = tuple(
        log
        for log in (IMPORT_LOG_FILE_NAME, DECISION_LOG_FILE_NAME)
        if f"{INPUTS_FOLDER}/{log}" in put_back
    )
    # Catch up: every run the live import log lists beyond the set comes
    # back from the export archive, as logged (`replay_import_log`).
    replayed: tuple[object, ...] = ()
    if log_runs_ahead:
        try:
            replayed = replay_import_log(lock)
        except REPLAY_REFUSALS as error:
            raise CatchUpRefusedError(selected.name, error) from error
    # A set from before sets held Silver or Gold restores none: those stages
    # start empty, so no history of them is recovered, and none invented.
    started = _start_missing_stages(profile, stores)
    # Recorded before the build, so the boundary names the set's current
    # publication and the first id any later build takes.
    with GoldStore(profile) as gold_store:
        boundary = gold_store.record_recovery_boundary(
            selected.name, selected.created_at, now
        )
    # Then Silver and Gold from everything recovered: the replayed runs,
    # the decisions and configuration since the set, and the running code.
    # Gold publishes only when that recipe differs from the restored one.
    try:
        gold = rebuild_through_gold(lock, now=now).gold
    except ConfigurationError as error:
        raise CatchUpInputsRefusedError(selected.name, error) from error
    except UncommittedCodeError as error:
        raise CatchUpCodeRefusedError(selected.name, error) from error
    undo = _undo_after_catch_up(profile, boundary, gold)
    # Durably: a marker that came back after a crash would let a later
    # restore remove a finished profile's stores as its own.
    (profile.stores / RESTORE_MARKER).unlink()
    sync_folder(profile.stores)
    return Restored(
        backup=selected,
        skipped=skipped,
        put_back=put_back,
        replayed=len(replayed),
        missing_logs=missing_logs,
        decision_line_cut_off=decision_line_cut_off,
        gold=gold,
        undo=undo,
        started=started,
    )
