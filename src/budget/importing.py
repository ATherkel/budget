# Copyright 2026 Therkel
"""Import one inbox export into Bronze, archive it, and log its import run.

This is the Bronze step `budget import` runs for each file in the inbox. The
file's folder declares its account (`inbox/<account_id>/`), `accounts.toml`
declares the account's source format, and the operator declares what the
export covers. The run is recorded in Bronze, its bytes are archived under
`exports/<account_id>/`, and the run is mirrored in `imports.jsonl`. Only then
does the file leave the inbox.
"""

import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Final

from budget.bronze import BronzeStore, ImportDeclaration, ImportRun
from budget.inputs import Account, load_accounts
from budget.locking import WriterLock
from budget.profiles import Profile

IMPORT_LOG_FORMAT: Final = 1
# How much of the payload hash names an archive folder (operations.md, W1).
HASH_PREFIX_LENGTH: Final = 12
REFUSED_FOLDER: Final = "refused"
# The outcomes a rerun finishes rather than presenting the file again.
RETRIED_OUTCOMES: Final = frozenset({"stored", "repeat"})
# The name a hash folder takes: the payload hash's first characters.
_HASH_FOLDER: Final = re.compile(f"[0-9a-f]{{{HASH_PREFIX_LENGTH}}}")


class ArchiveConflictError(RuntimeError):
    """The archive already holds other bytes everywhere a run's export may go.

    Nothing is overwritten. The run stays recorded in Bronze but not logged,
    and every later import stops before writing until the archive is put
    right. The message names the account and the run, never a filename.
    """

    def __init__(self, run: ImportRun) -> None:
        """Name the account and the import run that cannot be archived."""
        self.account_id = run.declared_account_id
        self.import_run_id = run.import_run_id
        super().__init__(
            f'account "{self.account_id}", import run {self.import_run_id}: the '
            "export archive already holds other bytes everywhere this run's "
            "export may go; nothing was overwritten. Move the conflicting file "
            "aside, then rerun."
        )


class ArchivedCopyReplacedError(RuntimeError):
    """Other bytes stand where a logged run's log entry says it is archived.

    The run is logged, and other imports go on. Nothing is overwritten: the
    remedy is to put the run's own bytes back where its entry says, from the
    file in the inbox or from Bronze. The message names the account and the
    run, never a filename.
    """

    def __init__(self, run: ImportRun) -> None:
        """Name the account and the import run whose copy was replaced."""
        self.account_id = run.declared_account_id
        self.import_run_id = run.import_run_id
        super().__init__(
            f'account "{self.account_id}", import run {self.import_run_id}: the '
            "export archive holds other bytes where this run's log entry says it "
            "is archived; nothing was overwritten, and the file stays in the "
            "inbox. Put the run's own export back there, then rerun."
        )


class ImportLogDamagedError(RuntimeError):
    """`imports.jsonl` holds a line that is not the entry of any run it may hold.

    That is a blank or unreadable line, a second entry for a run, an entry its
    run disagrees with, or a cut-off final line no archived run proves. An
    entry for a run Bronze never recorded is not damage, but a log ahead of
    Bronze (`ImportLogAheadOfBronzeError`). Nothing was written, and the log is
    never repaired by guessing. Restoring it from the newest backup set is
    safe: the next import logs again every run Bronze holds.
    """

    def __init__(self) -> None:
        """State the problem and its remedy, without quoting the log."""
        super().__init__(
            "imports.jsonl holds a line that is not the one entry of a recorded "
            "import run; nothing was written. Restore the log from the newest "
            "backup set: the next import logs again every run Bronze holds."
        )


class ImportLogAheadOfBronzeError(RuntimeError):
    """`imports.jsonl` mirrors a run Bronze never recorded.

    Bronze is older than the log, as after Bronze was restored from an older
    backup. The log's later entries are then the only record of those runs'
    declarations, so it must never be rolled back: Bronze is brought up to it.
    """

    def __init__(self) -> None:
        """State the problem and its remedy, without quoting the log."""
        super().__init__(
            "imports.jsonl mirrors an import run Bronze never recorded, so Bronze "
            "is older than the log; nothing was written. Bring Bronze up to the "
            "log by restoring it, and keep the log as it is."
        )


class NotAnInboxFileError(ValueError):
    """The file is not directly inside one account's inbox folder.

    The folder is the account declaration, so a file anywhere else has none.
    The message never names the file.
    """

    def __init__(self) -> None:
        """State the rule, without the operator's paths."""
        super().__init__(
            "only a file directly inside inbox/<account_id>/ can be imported"
        )


class UnknownInboxAccountError(ValueError):
    """The file's inbox folder names no account in `accounts.toml`."""

    def __init__(self, account_id: str) -> None:
        """Keep the folder's name, but leave it out of the message.

        The household names inbox folders by hand, so one could carry a bank
        account number, which never belongs in a message that may be logged.
        """
        self.account_id = account_id
        super().__init__(
            "an inbox folder names no account in accounts.toml; move the file "
            "to its account's folder, or add the account"
        )


@dataclass(frozen=True)
class Coverage:
    """What the operator declares about one inbox file's export.

    `exported_on` is needed only when the source format reads no export date
    from the filename.
    """

    covers_from: date
    covers_through: date
    exported_on: date | None = None


@dataclass(frozen=True)
class InboxImport:
    """What happened to one inbox file.

    `archive_path` is where its bytes are archived, relative to the profile's
    export archive and with `/` separators, as the import log records it.
    `left_in_inbox` reports whether the file is still in the inbox when the
    import returns: a refused file, a file saved over with other bytes while it
    was imported, and a file another program holds all stay there.
    """

    import_run: ImportRun
    archive_path: str
    left_in_inbox: bool


def _inbox_account(profile: Profile, source: Path) -> Account:
    """Return the account a file's inbox folder declares, before any write.

    Refuses a file outside `inbox/<account_id>/`, a folder `accounts.toml`
    does not name, and an export whose filename names another bank account.
    """
    folder = source.resolve().parent
    if folder.parent != profile.inbox:
        raise NotAnInboxFileError
    account = load_accounts(profile).get(folder.name)
    if account is None:
        raise UnknownInboxAccountError(folder.name)
    account.check_export_filename(source.name)
    return account


def _archive_candidates(run: ImportRun) -> tuple[str, ...]:
    """Name where a run's bytes may be archived, relative to the export archive.

    An accepted export keeps its original name in its account's folder, or,
    when other bytes already hold that name, the same name in a folder named
    by its hash. A refused run's bytes are copied apart, under `refused/`, so
    the account's folder holds only accepted exports while replay can still
    find them. An export named like one of those folders goes straight to its
    hash folder, so no archived file ever stands where a folder must go.
    """
    account_id = run.declared_account_id
    name = run.original_filename
    hash_prefix = run.payload_id[:HASH_PREFIX_LENGTH]
    in_hash_folder = f"{account_id}/{hash_prefix}/{name}"
    if run.outcome == "refused":
        return (f"{account_id}/{REFUSED_FOLDER}/{hash_prefix}/{name}",)
    if _names_an_archive_folder(name):
        return (in_hash_folder,)
    return (f"{account_id}/{name}", in_hash_folder)


def _names_an_archive_folder(name: str) -> bool:
    """Report whether a file name is one the archive gives its own folders.

    Compared without case, as Windows compares names.
    """
    folded = name.casefold()
    return folded == REFUSED_FOLDER or _HASH_FOLDER.fullmatch(folded) is not None


def _archived_at(
    profile: Profile,
    run: ImportRun,
    content: bytes,
    reserved: Mapping[str, str],
) -> tuple[str, bool]:
    """Return where the run's bytes belong, and whether they are there already.

    The first candidate that already holds these bytes is the place, so a
    retry finds it again; otherwise the first free one is. A candidate that
    holds anything else is never overwritten. `reserved` maps each place a log
    entry names, keyed by `_place`, to the payload archived there: a place
    reserved for other bytes is not free even when its copy is missing.
    """
    # A place another payload's entry names is never this run's, whatever it
    # holds now.
    candidates = {
        archive_path: profile.archive_file(archive_path)
        for archive_path in _archive_candidates(run)
        if reserved.get(_place(archive_path), run.payload_id) == run.payload_id
    }
    for archive_path, target in candidates.items():
        if target.is_file() and target.read_bytes() == content:
            return archive_path, True
    for archive_path, target in candidates.items():
        if _is_free(target, profile.exports):
            return archive_path, False
    raise ArchiveConflictError(run)


def _is_free(target: Path, exports: Path) -> bool:
    """Report whether a new file can go at `target` without moving anything.

    An archived export can stand where a folder on the way must go, such as
    one named `refused`; that place is taken, not free.
    """
    folders = [folder for folder in target.parents if folder.is_relative_to(exports)]
    return not target.exists() and all(
        folder.is_dir() or not folder.exists() for folder in folders
    )


def _archive(
    profile: Profile,
    run: ImportRun,
    content: bytes,
    reserved: Mapping[str, str],
) -> str:
    """Archive the run's bytes, unless they are archived already.

    `reserved` maps each place the log's entries name to the payload archived
    there; a new copy never takes a place reserved for other bytes.
    """
    archive_path, archived = _archived_at(profile, run, content, reserved)
    if not archived:
        _write_durably(profile.archive_file(archive_path), content)
    return archive_path


def _keep_archived(
    profile: Profile, run: ImportRun, archive_path: str, content: bytes
) -> None:
    """Make sure a logged run's bytes are where its log entry says.

    A copy that went missing is written there again, never elsewhere, so the
    log stays true. Other bytes in its place are never overwritten.
    """
    target = profile.archive_file(archive_path)
    if target.is_file() and target.read_bytes() == content:
        return
    if not _is_free(target, profile.exports):
        raise ArchivedCopyReplacedError(run)
    _write_durably(target, content)


def _sync_folder(folder: Path) -> None:
    """Force a folder's new entries to disk, where the platform allows it.

    Windows cannot open a folder to fsync it; NTFS journals a rename itself.
    """
    if sys.platform == "win32":
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_durably(path: Path, content: bytes) -> None:
    """Write a new file whole, or not at all.

    A write that fails removes its temporary file; only a crash can leave
    one behind, under a name no later write reuses.

    The caller has checked under the writer lock that `path` is free. That
    check is what keeps archived bytes from being overwritten: Windows refuses
    to rename onto an existing file, but POSIX replaces it.
    """
    created = _missing_folders(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Created exclusively under a new name, so it never truncates a file the
    # archive already holds, whatever that file is called.
    descriptor, partial_name = tempfile.mkstemp(
        dir=path.parent, prefix=".", suffix=".partial"
    )
    partial = Path(partial_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        partial.rename(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    _sync_folder(path.parent)
    # A new folder is an entry in its parent, which needs forcing to disk too.
    for folder in created:
        _sync_folder(folder.parent)


def _missing_folders(folder: Path) -> list[Path]:
    """List `folder` and its parents that do not exist yet, innermost first."""
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    return missing


def _log_entry(run: ImportRun, archive_path: str) -> bytes:
    """Mirror one import run as an `imports.jsonl` line, with its line feed."""
    entry = {
        "format": IMPORT_LOG_FORMAT,
        "import_run_id": run.import_run_id,
        "account_id": run.declared_account_id,
        "source_format": run.source_format,
        "archive_path": archive_path,
        "payload_sha256": run.payload_id,
        "exported_on": run.exported_on.isoformat(),
        "exported_on_source": run.exported_on_source,
        "covers_from": run.covers_from.isoformat(),
        "covers_through": run.covers_through.isoformat(),
        "started_at": run.started_at.isoformat(),
        "outcome": run.outcome,
        "repeat_of": run.repeat_of,
    }
    return (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")


def _append_to_log(path: Path, data: bytes) -> None:
    """Append to the log and force it to disk before going on."""
    created = not path.exists()
    with path.open("ab") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    if created:
        _sync_folder(path.parent)


@dataclass(frozen=True)
class _LogState:
    """Each complete entry of `imports.jsonl` by run, and any final one cut off.

    An entry is kept as its exact bytes, line feed included.
    """

    lines: Mapping[str, bytes]
    cut_off: bytes


def _logged_run_id(line: bytes) -> str:
    """Return the run one complete line names; any other line is damage."""
    try:
        run_id = json.loads(line)["import_run_id"]
    except (ValueError, KeyError, TypeError):
        raise ImportLogDamagedError from None
    if not isinstance(run_id, str):
        raise ImportLogDamagedError
    return run_id


def _read_log(path: Path) -> _LogState:
    """Read the log's complete entries apart from a final line without a feed.

    Every complete line, blank ones included, must name a run, and only once.
    """
    if not path.exists():
        return _LogState(lines={}, cut_off=b"")
    complete, feed, cut_off = path.read_bytes().rpartition(b"\n")
    lines: dict[str, bytes] = {}
    for line in complete.split(b"\n") if feed else []:
        run_id = _logged_run_id(line)
        if run_id in lines:
            raise ImportLogDamagedError
        lines[run_id] = line + b"\n"
    return _LogState(lines=lines, cut_off=cut_off)


def _logged_archive_path(run: ImportRun, line: bytes) -> str:
    """Return where a logged run's export is archived, as its entry says.

    The entry must be exactly what this code writes for the run, at one of
    the places the run's export may be archived; anything else is damage.
    """
    for archive_path in _archive_candidates(run):
        if line == _log_entry(run, archive_path):
            return archive_path
    raise ImportLogDamagedError


def _logged_archive_paths(state: _LogState, store: BronzeStore) -> dict[str, str]:
    """Return where each logged run is archived, refusing a log Bronze lacks."""
    runs = {run.import_run_id: run for run in store.import_runs()}
    archive_paths = {}
    for run_id, line in state.lines.items():
        run = runs.get(run_id)
        if run is None:
            raise ImportLogAheadOfBronzeError
        archive_paths[run_id] = _logged_archive_path(run, line)
    return archive_paths


def _proving_entry(
    profile: Profile,
    store: BronzeStore,
    state: _LogState,
    reserved: Mapping[str, str],
) -> tuple[str, str, bytes] | None:
    """Find the unlogged, archived run whose entry the cut-off begins.

    The run is placed as archiving placed it: with the places the complete
    entries reserve, which are the ones before it. Returns the run, its
    archive path and its whole entry.
    """
    for run in store.import_runs():
        if run.import_run_id in state.lines:
            continue
        content = store.get_payload(run.payload_id).content
        try:
            archive_path, archived = _archived_at(profile, run, content, reserved)
        except ArchiveConflictError:
            continue
        entry = _log_entry(run, archive_path)
        if archived and entry.startswith(state.cut_off):
            return run.import_run_id, archive_path, entry
    return None


def _recover_log(profile: Profile, store: BronzeStore) -> dict[str, str]:
    """Bring a log a crash cut off back to whole entries, before any write.

    A cut-off final entry is completed only when an unlogged run that is
    already archived proves what it was going to say: the entry is written
    after the archive, so no other run can be the one it began. Anything else
    is refused, and the log is left exactly as it was found. So is an entry
    for a run Bronze never recorded, such as when Bronze is older than the log,
    and an entry that does not restate its run exactly.

    Returns where each logged run is archived, by run.
    """
    state = _read_log(profile.import_log_file)
    logged = _logged_archive_paths(state, store)
    if not state.cut_off:
        return logged
    proof = _proving_entry(profile, store, state, _reserved_places(store, logged))
    if proof is None:
        raise ImportLogDamagedError
    run_id, archive_path, entry = proof
    _append_to_log(profile.import_log_file, entry[len(state.cut_off) :])
    logged[run_id] = archive_path
    return logged


def _place(archive_path: str) -> str:
    """Key an archive path as the file system compares names.

    Windows ignores case, so `A.csv` and `a.csv` are one place there.
    """
    return os.path.normcase(archive_path)


def _reserved_places(store: BronzeStore, logged: Mapping[str, str]) -> dict[str, str]:
    """Map each place a log entry names, by `_place`, to its run's payload."""
    payloads = {run.import_run_id: run.payload_id for run in store.import_runs()}
    return {
        _place(archive_path): payloads[run_id]
        for run_id, archive_path in logged.items()
    }


def _bring_log_up_to_date(
    profile: Profile, store: BronzeStore, logged: Mapping[str, str]
) -> dict[str, str]:
    """Archive and log every run Bronze holds that the log does not, oldest first.

    A crash can leave a run in Bronze and nowhere else. A refused run's file
    stays in the inbox, so no retry of that file would finish it; this does,
    from the bytes Bronze retains. Takes and returns where each logged run is
    archived, by run.
    """
    now_logged = dict(logged)
    reserved = _reserved_places(store, now_logged)
    for run in store.import_runs():
        if run.import_run_id in now_logged:
            continue
        content = store.get_payload(run.payload_id).content
        archive_path = _archive(profile, run, content, reserved)
        reserved[_place(archive_path)] = run.payload_id
        _append_to_log(profile.import_log_file, _log_entry(run, archive_path))
        now_logged[run.import_run_id] = archive_path
    return now_logged


def _payload_id(source: Path) -> str:
    """Name the bytes a file holds now, as Bronze names a payload."""
    return sha256(source.read_bytes()).hexdigest()


def _clear_from_inbox(source: Path, run: ImportRun) -> bool:
    """Remove a finished, accepted export from the inbox; report if it is left.

    A refused file stays. So does a file saved over since it was read: it is
    another presentation. A file someone already removed needs nothing more.
    A file another program holds stays too; the import is finished, and the
    next one removes the file as a retry of this run.
    """
    if run.outcome == "refused":
        return source.exists()
    try:
        if _payload_id(source) != run.payload_id:
            return True
        source.unlink()
    except FileNotFoundError:
        return False
    except PermissionError:
        return True
    return False


def _earlier_run(store: BronzeStore, account_id: str, source: Path) -> ImportRun | None:
    """Return the accepted run an interrupted import of this file left behind.

    The retry identity is the account, the original filename and the payload
    hash. A refused run never matches: presenting the file again is new.
    """
    identity = (account_id, source.name, _payload_id(source))
    for run in store.import_runs():
        found = (run.declared_account_id, run.original_filename, run.payload_id)
        if found == identity and run.outcome in RETRIED_OUTCOMES:
            return run
    return None


def import_inbox_file(
    lock: WriterLock,
    source: Path,
    coverage: Coverage,
) -> InboxImport:
    """Import one inbox file under the held writer lock."""
    profile = lock.profile
    account = _inbox_account(profile, source)
    declaration = ImportDeclaration(
        declared_account_id=account.account_id,
        source_format=account.source_format,
        covers_from=coverage.covers_from,
        covers_through=coverage.covers_through,
        exported_on=coverage.exported_on,
    )
    with BronzeStore(profile) as store:
        # Earlier runs are finished first, so one that cannot be stops this
        # import before it records anything of its own.
        logged = _bring_log_up_to_date(profile, store, _recover_log(profile, store))
        run = _earlier_run(store, account.account_id, source)
        if run is None:
            run = store.import_file(source, declaration)
        content = store.get_payload(run.payload_id).content
        # An earlier run is logged by now, so its log entry names its place.
        archive_path = logged.get(run.import_run_id)
        if archive_path is None:
            reserved = _reserved_places(store, logged)
            archive_path = _archive(profile, run, content, reserved)
            _bring_log_up_to_date(profile, store, logged)
        else:
            _keep_archived(profile, run, archive_path, content)

    left_in_inbox = _clear_from_inbox(source, run)
    return InboxImport(
        import_run=run, archive_path=archive_path, left_in_inbox=left_in_inbox
    )
