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
    """The archive already holds different bytes where this export must go.

    Nothing is overwritten. The import run is recorded in Bronze and the file
    stays in the inbox, so the import resumes once the archive is put right.
    The message names the account only, never a filename.
    """

    def __init__(self, account_id: str) -> None:
        """Name the account whose archive folder holds the conflicting bytes."""
        self.account_id = account_id
        super().__init__(
            f'account "{account_id}": the export archive already holds other '
            "bytes under this export's name and under its hash folder; nothing "
            "was overwritten, and the file stays in the inbox"
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
        """Name the folder, which is the account ID it declares."""
        self.account_id = account_id
        super().__init__(
            f'inbox folder "{account_id}" names no account in accounts.toml'
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
    refused run leaves the file in the inbox.
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


def _archive(exports: Path, run: ImportRun, content: bytes) -> str:
    """Archive the bytes where they are, or where nothing is yet.

    A candidate that already holds these bytes is reused, so a retry finds the
    same place. One that holds anything else is never overwritten.
    """
    for archive_path in _archive_candidates(run):
        target = exports / archive_path
        if not target.exists():
            _write_durably(target, content)
            return archive_path
        if target.is_file() and target.read_bytes() == content:
            return archive_path
    raise ArchiveConflictError(run.declared_account_id)


def _write_durably(path: Path, content: bytes) -> None:
    """Write a new file whole: a crash leaves only a temporary file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    with partial.open("wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    partial.rename(path)


def _log_entry(run: ImportRun, archive_path: str) -> dict[str, object]:
    """Mirror one import run as an `imports.jsonl` entry."""
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


def _append_to_log(path: Path, entry: dict[str, object]) -> None:
    """Append one entry and force it to disk before going on."""
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with path.open("ab") as file:
        file.write(line.encode("utf-8"))
        file.flush()
        os.fsync(file.fileno())


def _logged_run_ids(path: Path) -> set[str]:
    """Return the import runs `imports.jsonl` already mirrors."""
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {json.loads(line)["import_run_id"] for line in lines}


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
        run = _earlier_run(store, account.account_id, source)
        if run is None:
            run = store.import_file(source, declaration)
        content = store.get_payload(run.payload_id).content

    archive_path = _archive(profile.exports, run, content)
    if run.import_run_id not in _logged_run_ids(profile.import_log_file):
        _append_to_log(profile.import_log_file, _log_entry(run, archive_path))
    refused = run.outcome == "refused"
    if not refused:
        source.unlink()
    return InboxImport(import_run=run, archive_path=archive_path, left_in_inbox=refused)
