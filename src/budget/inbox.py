# Copyright 2026 Therkel
"""The `import` application operation: every inbox export, then Silver.

Each export in `inbox/<account_id>/` is previewed, then imported on its own
through `import_inbox_file`, under the one writer lock the command holds, and
Silver is then rebuilt from the Bronze those imports wrote. A misfiled or
unreadable export is found by its preview, before anyone is asked for its
range, and never reaches Bronze.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Final

from budget.backups import (
    BACKUP_FAILURES,
    BackupSet,
    back_up,
    require_backup_allowed,
)
from budget.bronze.models import ImportRun
from budget.bronze.parsers.registry import source_parser
from budget.codeversion import require_committed_code
from budget.importing import (
    Coverage,
    NotAnInboxFileError,
    UnknownInboxAccountError,
    import_inbox_file,
)
from budget.importing import InboxImport as InboxFileImport
from budget.inputs import Account, MisfiledExportError
from budget.locking import WriterLock
from budget.profiles import PRODUCTION_PROFILE_NAME, Profile
from budget.rebuilding import (
    SilverRebuild,
    rebuild_from_silver,
    require_no_decisions,
)

# The outcomes that leave a file in the inbox and make `import` exit 3.
LEFT_IN_INBOX: Final = frozenset({"refused", "misfiled", "unreadable"})
# How a file in a folder that names no account is shown: the folder's name is
# typed by hand, so it may carry a bank account number.
NO_ACCOUNT: Final = "(no account)"
_NO_EXPORT_DATE: Final = (
    "the filename carries no export date; keep the name the bank gave it"
)


@dataclass(frozen=True)
class ExportPreview:
    """What one inbox file says about itself before anything is stored.

    The transaction dates are the file's first and last, read by its
    account's source format, so the person can check that the range they
    declare covers them. Both are `None` when the file has no records, and
    `failure_reason` says why when the format could not read it. `skipped`
    names why the file is not imported at all, `misfiled` or `unreadable`,
    and `reason` says how; both are empty when it can be imported, and
    then `exported_on` is the date its filename carries.
    """

    source: Path
    account_id: str
    exported_on: date | None = None
    first_transaction: date | None = None
    last_transaction: date | None = None
    records: int = 0
    failure_reason: str | None = None
    skipped: str = ""
    reason: str = ""


@dataclass(frozen=True)
class FileOutcome:
    """What happened to one inbox file, named by its place in the listing.

    `reason` is empty for a stored or repeat export, and never repeats a
    filename, an amount or a description. `note` says why an accepted export
    is still in the inbox, when it is.
    """

    ordinal: int
    account_id: str
    status: str
    reason: str = ""
    note: str = ""


@dataclass(frozen=True)
class ImportedInbox:
    """Every inbox file's outcome, the Silver rebuild and production's backup.

    `rebuilt` is `None` when no file reached Bronze: then nothing changed,
    and neither a rebuild nor a backup follows. `backup` is the set
    written after the rebuild; only production writes one.
    `backup_failure` is why production's set could not be written, if so.
    """

    files: Sequence[FileOutcome]
    rebuilt: SilverRebuild | None
    backup: BackupSet | None = None
    backup_failure: Exception | None = None

    def counts(self) -> dict[str, int]:
        """Count the files by outcome and Silver's runs and drops, and nothing else.

        These are what the routine log records: never an account, a reason or
        a filename.
        """
        outcomes = Counter(each.status for each in self.files)
        result = None if self.rebuilt is None else self.rebuilt.result
        runs = () if result is None else result.import_run_results
        items = () if result is None else result.review_items
        statuses = Counter(each.status for each in runs)
        return {
            "stored": outcomes["stored"],
            "repeat": outcomes["repeat"],
            "refused": outcomes["refused"],
            "misfiled": outcomes["misfiled"],
            "unreadable": outcomes["unreadable"],
            "format_failure": outcomes["format failure"],
            "admitted": statuses["accepted"],
            "quarantined": statuses["quarantined"],
            "dropped": sum(1 for item in items if item.kind == "dropped-transaction"),
        }

    @property
    def any_left_in_inbox(self) -> bool:
        """Whether any file stays in the inbox unimported: exit 3."""
        return any(each.status in LEFT_IN_INBOX for each in self.files)


def require_import_allowed(profile: Profile) -> None:
    """Refuse, before anything is asked or stored, what would refuse later.

    The Silver rebuild refuses uncommitted code in production and a decision
    log holding a decision; production's backup refuses a stores folder no
    set can cover. Found only after the Bronze writes, any of them would
    leave production written without the build and backup that must follow.
    """
    require_committed_code(profile)
    require_no_decisions(profile)
    if profile.name == PRODUCTION_PROFILE_NAME:
        require_backup_allowed(profile)


def inbox_exports(profile: Profile) -> tuple[Path, ...]:
    """List the files waiting in the inbox, in order.

    That is every file anywhere under the inbox. Only one directly inside an
    account folder can be imported, but an export saved in the inbox itself,
    or in a folder inside an account's, is reported, never skipped without a
    word.
    """
    if not profile.inbox.is_dir():
        return ()
    return tuple(sorted(path for path in profile.inbox.rglob("*") if path.is_file()))


def _exported_on(account: Account, source: Path) -> date | str:
    """Return the export date a file's name carries, or why it does not fit.

    A name that carries another bank account's number, or no export date, is
    misfiled; the returned reason never repeats the name.
    """
    try:
        account.check_export_filename(source.name)
    except MisfiledExportError as error:
        return str(error)
    parser = source_parser(account.source_format)
    try:
        exported_on = parser.exported_on_from_filename(source.name)
    except ValueError as error:
        # The parser contract: a date-shaped suffix that is not a real date.
        return str(error)
    return _NO_EXPORT_DATE if exported_on is None else exported_on


def _misfiled(source: Path, account_id: str, reason: str) -> ExportPreview:
    """Preview a file that cannot be imported where it lies."""
    return ExportPreview(
        source=source, account_id=account_id, skipped="misfiled", reason=reason
    )


def _unreadable(error: OSError) -> str:
    """Say why a file cannot be read, never naming its path.

    On Windows that is most often another program holding it without
    sharing it, as a spreadsheet program can.
    """
    reason = error.strerror or type(error).__name__
    return (
        f"the file cannot be read ({reason}): close the program that holds "
        "it, then rerun import"
    )


def preview(
    profile: Profile, accounts: Mapping[str, Account], source: Path
) -> ExportPreview:
    """Read one inbox file's account and transaction dates, storing nothing."""
    if source.parent.parent != profile.inbox:
        problem = str(NotAnInboxFileError())
        return _misfiled(source, NO_ACCOUNT, problem)
    account = accounts.get(source.parent.name)
    if account is None:
        problem = str(UnknownInboxAccountError(source.parent.name))
        return _misfiled(source, NO_ACCOUNT, problem)
    exported_on = _exported_on(account, source)
    if isinstance(exported_on, str):
        return _misfiled(source, account.account_id, exported_on)
    try:
        content = source.read_bytes()
    except OSError as error:
        return ExportPreview(
            source=source,
            account_id=account.account_id,
            skipped="unreadable",
            reason=_unreadable(error),
        )
    parsed = source_parser(account.source_format).parse(content)
    return ExportPreview(
        source=source,
        account_id=account.account_id,
        exported_on=exported_on,
        first_transaction=parsed.first_transaction_date,
        last_transaction=parsed.last_transaction_date,
        records=len(parsed.records),
        failure_reason=parsed.failure_reason,
    )


def refusal_reasons(run: ImportRun, previewed: ExportPreview) -> tuple[str, ...]:
    """Say why Bronze refused a run, as `declared_range_refused` decides it.

    Bronze records that a run was refused, not why, so the reasons are
    derived again from the declaration and the file's own dates. A run whose
    range Bronze allows was refused because its bytes are stored for another
    account.
    """
    reasons = []
    if run.covers_from > run.covers_through:
        reasons.append("the declared range starts after it ends")
    if run.covers_through > run.exported_on:
        reasons.append("the declared range ends after the export date")
    first, last = previewed.first_transaction, previewed.last_transaction
    if first is not None and first < run.covers_from:
        reasons.append("the file has transactions before the declared range starts")
    if last is not None and last > run.covers_through:
        reasons.append("the file has transactions after the declared range ends")
    if not reasons:
        reasons.append("the same bytes are already stored for another account")
    return tuple(reasons)


def _still_in_inbox(imported: InboxFileImport, source: Path) -> str:
    """Say why an accepted export is still in the inbox, if it is.

    Its bytes are archived and logged, so a rerun finishes it as a retry. The
    file is either held open by another program, or was saved over while it
    was imported, in which case it now holds bytes no run stored.
    """
    if not imported.left_in_inbox:
        return ""
    try:
        changed = (
            sha256(source.read_bytes()).hexdigest() != imported.import_run.payload_id
        )
    except OSError:
        changed = False
    if changed:
        return (
            "it stays in the inbox because it changed while it was imported: "
            "rerun import to import it as it is now"
        )
    return (
        "it stays in the inbox because another program holds it: close that "
        "program, then rerun import"
    )


def _outcome(
    ordinal: int, imported: InboxFileImport, previewed: ExportPreview
) -> FileOutcome:
    """Name one imported file's outcome, and why when it was not a clean store.

    A stored payload its format could not read is a format failure: it is
    archived like any accepted export, and Silver quarantines it. Its reason
    is the parser's verdict, which never repeats source content.
    """
    run = imported.import_run
    account_id = run.declared_account_id
    if run.outcome == "refused":
        reason = "; ".join(refusal_reasons(run, previewed))
        return FileOutcome(ordinal, account_id, "refused", reason)
    note = _still_in_inbox(imported, previewed.source)
    if run.outcome == "stored" and previewed.failure_reason is not None:
        return FileOutcome(
            ordinal, account_id, "format failure", previewed.failure_reason, note
        )
    return FileOutcome(ordinal, account_id, run.outcome, note=note)


def import_inbox(
    lock: WriterLock,
    previews: Sequence[ExportPreview],
    declared: Mapping[Path, Coverage],
) -> ImportedInbox:
    """Import each file with its declared range, then rebuild Silver.

    `declared` maps each file that is not skipped to the range the person
    declared for it, all of them settled before this is called. Files are
    numbered in `previews`' order, the order the person was shown them in.
    """
    files: list[FileOutcome] = []
    for ordinal, previewed in enumerate(previews, start=1):
        if previewed.skipped:
            files.append(
                FileOutcome(
                    ordinal, previewed.account_id, previewed.skipped, previewed.reason
                )
            )
            continue
        imported = import_inbox_file(lock, previewed.source, declared[previewed.source])
        files.append(_outcome(ordinal, imported, previewed))
    if all(previewed.skipped for previewed in previews):
        return ImportedInbox(files=files, rebuilt=None)
    rebuilt = rebuild_from_silver(lock)
    if lock.profile.name != PRODUCTION_PROFILE_NAME:
        return ImportedInbox(files=files, rebuilt=rebuilt)
    # Every production write is followed by a set covering Bronze and the
    # Silver just rebuilt from it. The imports are committed by now, so a set
    # that cannot be written is reported beside them, not instead of them.
    try:
        backup = back_up(lock, now=datetime.now(UTC))
    except BACKUP_FAILURES as error:
        return ImportedInbox(files=files, rebuilt=rebuilt, backup_failure=error)
    return ImportedInbox(files=files, rebuilt=rebuilt, backup=backup)
