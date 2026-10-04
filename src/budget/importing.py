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


class ImportLogDamagedError(RuntimeError):
    """`imports.jsonl` holds what no recorded import run accounts for.

    That is a line that is not the one entry of a run Bronze recorded, or a
    cut-off final line no archived run proves. Nothing was written. The log is
    never repaired by guessing: an operator restores it from the newest backup
    set, as for the decision log.
    """

    def __init__(self) -> None:
        """State the problem without quoting the log's content."""
        super().__init__(
            "imports.jsonl holds a line that is not the one entry of a recorded "
            "import run; nothing was written. Restore the log from the newest "
            "backup set."
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
    export archive and with `/` separators, as the import log records it. A
    refused run leaves the file in the inbox, and so does a file saved over
    with other bytes while it was imported.
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
    find them.
    """
    account_id = run.declared_account_id
    name = run.original_filename
    hash_prefix = run.payload_id[:HASH_PREFIX_LENGTH]
    if run.outcome == "refused":
        return (f"{account_id}/{REFUSED_FOLDER}/{hash_prefix}/{name}",)
    return (f"{account_id}/{name}", f"{account_id}/{hash_prefix}/{name}")


def _archived_at(profile: Profile, run: ImportRun, content: bytes) -> tuple[str, bool]:
    """Return where the run's bytes belong, and whether they are there already.

    The first candidate that already holds these bytes is the place, so a
    retry finds it again; otherwise the first free one is. A candidate that
    holds anything else is never overwritten.
    """
    candidates = {
        archive_path: profile.archive_file(archive_path)
        for archive_path in _archive_candidates(run)
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


def _archive(profile: Profile, run: ImportRun, content: bytes) -> str:
    """Archive the run's bytes, unless they are archived already."""
    archive_path, archived = _archived_at(profile, run, content)
    if not archived:
        _write_durably(profile.archive_file(archive_path), content)
    return archive_path


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
    """Write a new file whole: a crash leaves only a temporary file behind.

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
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    Path(partial_name).rename(path)
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


def _entry_fields(run: ImportRun, archive_path: str) -> dict[str, object]:
    """Mirror one import run as the fields of its `imports.jsonl` entry."""
    return {
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


def _log_entry(run: ImportRun, archive_path: str) -> bytes:
    """Mirror one import run as an `imports.jsonl` line, with its line feed."""
    entry = _entry_fields(run, archive_path)
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
    """The entries `imports.jsonl` holds by run, and any final one cut off."""

    entries: Mapping[str, Mapping[str, object]]
    cut_off: bytes

    @property
    def logged(self) -> frozenset[str]:
        """The runs the log mirrors."""
        return frozenset(self.entries)


def _logged_entry(line: bytes) -> tuple[str, Mapping[str, object]]:
    """Return the run one complete line mirrors, and its fields.

    Any line that is not a JSON object naming a run is damage.
    """
    try:
        entry = json.loads(line)
        run_id = entry["import_run_id"]
    except (ValueError, KeyError, TypeError):
        raise ImportLogDamagedError from None
    if not isinstance(entry, dict) or not isinstance(run_id, str):
        raise ImportLogDamagedError
    # Rebuilt so the values are typed `object`, not the `Any` `json` returns;
    # JSON keys are always strings, so `str` changes nothing.
    fields: dict[str, object] = {str(key): value for key, value in entry.items()}
    return run_id, fields


def _read_log(path: Path) -> _LogState:
    """Read the log's complete entries apart from a final line without a feed.

    Every complete line, blank ones included, must be the one entry of a run.
    """
    if not path.exists():
        return _LogState(entries={}, cut_off=b"")
    complete, feed, cut_off = path.read_bytes().rpartition(b"\n")
    entries: dict[str, Mapping[str, object]] = {}
    for line in complete.split(b"\n") if feed else []:
        run_id, entry = _logged_entry(line)
        if run_id in entries:
            raise ImportLogDamagedError
        entries[run_id] = entry
    return _LogState(entries=entries, cut_off=cut_off)


def _require_entries_match_runs(state: _LogState, store: BronzeStore) -> None:
    """Refuse an entry Bronze recorded no run for, or one its run disagrees with.

    Every field but `archive_path` restates the run, so it must say the same;
    `archive_path` is only known from the archive, and must be text.
    """
    runs = {run.import_run_id: run for run in store.import_runs()}
    for run_id, entry in state.entries.items():
        run = runs.get(run_id)
        archive_path = entry.get("archive_path")
        if run is None or not isinstance(archive_path, str):
            raise ImportLogDamagedError
        if entry != _entry_fields(run, archive_path):
            raise ImportLogDamagedError


def _proving_entry(
    profile: Profile, store: BronzeStore, state: _LogState
) -> bytes | None:
    """Return the entry of an unlogged, archived run that the cut-off begins."""
    for run in store.import_runs():
        if run.import_run_id in state.logged:
            continue
        content = store.get_payload(run.payload_id).content
        try:
            archive_path, archived = _archived_at(profile, run, content)
        except ArchiveConflictError:
            continue
        entry = _log_entry(run, archive_path)
        if archived and entry.startswith(state.cut_off):
            return entry
    return None


def _recovered_log(profile: Profile, store: BronzeStore) -> frozenset[str]:
    """Bring a log a crash cut off back to whole entries, before any write.

    A cut-off final entry is completed only when an unlogged run that is
    already archived proves what it was going to say: the entry is written
    after the archive, so no other run can be the one it began. Anything else
    is refused, and the log is left exactly as it was found. So is an entry
    for a run Bronze never recorded, such as when Bronze is older than the log,
    and an entry its run disagrees with.
    """
    state = _read_log(profile.import_log_file)
    _require_entries_match_runs(state, store)
    if not state.cut_off:
        return state.logged
    entry = _proving_entry(profile, store, state)
    if entry is None:
        raise ImportLogDamagedError
    _append_to_log(profile.import_log_file, entry[len(state.cut_off) :])
    return _read_log(profile.import_log_file).logged


def _bring_log_up_to_date(
    profile: Profile, store: BronzeStore, logged: frozenset[str]
) -> frozenset[str]:
    """Archive and log every run Bronze holds that the log does not, oldest first.

    A crash can leave a run in Bronze and nowhere else. A refused run's file
    stays in the inbox, so no retry of that file would finish it; this does,
    from the bytes Bronze retains. Returns every run the log now mirrors.
    """
    now_logged = set(logged)
    for run in store.import_runs():
        if run.import_run_id in now_logged:
            continue
        content = store.get_payload(run.payload_id).content
        archive_path = _archive(profile, run, content)
        _append_to_log(profile.import_log_file, _log_entry(run, archive_path))
        now_logged.add(run.import_run_id)
    return frozenset(now_logged)


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
        if sha256(source.read_bytes()).hexdigest() != run.payload_id:
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
    identity = (account_id, source.name, sha256(source.read_bytes()).hexdigest())
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
        logged = _bring_log_up_to_date(profile, store, _recovered_log(profile, store))
        run = _earlier_run(store, account.account_id, source)
        if run is None:
            run = store.import_file(source, declaration)
        content = store.get_payload(run.payload_id).content
        archive_path = _archive(profile, run, content)
        _bring_log_up_to_date(profile, store, logged)

    left_in_inbox = _clear_from_inbox(source, run)
    return InboxImport(
        import_run=run, archive_path=archive_path, left_in_inbox=left_in_inbox
    )
