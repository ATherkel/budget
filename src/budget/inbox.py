# Copyright 2026 Therkel
"""The `import` application operation: every inbox export, then Silver.

Each export in `inbox/<account_id>/` is previewed, then imported on its own
through `import_inbox_file`, under the one writer lock the command holds, and
Silver is then rebuilt from the Bronze those imports wrote. A payload the
inbox holds under more than one declared account is a cross-account duplicate:
every file in it is refused before the first write, because which account the
bank really exported it for is unknown. A misfiled or
unreadable export, or one its format cannot read, is found by its preview,
before anyone is asked for its range, and never reaches Bronze: it waits
in the inbox for a fresh download or a reader fix.
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
from budget.decision_log import read_decision_log
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
)

# The outcomes that leave a file in the inbox and make `import` exit 3.
LEFT_IN_INBOX: Final = frozenset(
    {"refused", "misfiled", "unreadable", "format failure", "incident"}
)
# Why an incident file is never imported: the same bytes are in the inbox
# under another account, and only a person can say which account they belong
# to.
INCIDENT_REASON: Final = "the same bytes are in the inbox under another account"
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
    declare covers them. Both are `None` when the file has no records.
    `skipped` names why the file is not imported at all, `misfiled`,
    `unreadable` or `format failure`, and `reason` says how; both are
    empty when it can be imported, and then `exported_on` is the date its
    filename carries. `payload_id` names the bytes the preview read, and is
    empty when it read none: a file under no declared account, one whose name
    is misfiled, and one that cannot be read.
    """

    source: Path
    account_id: str
    exported_on: date | None = None
    first_transaction: date | None = None
    last_transaction: date | None = None
    records: int = 0
    skipped: str = ""
    reason: str = ""
    payload_id: str = ""


@dataclass(frozen=True)
class DuplicateIncident:
    """One payload the inbox holds under two or more declared accounts.

    Every file in it is impacted, whichever declared account each one sits
    under: which of them the bank really exported is unknown, so none of them
    is imported and none is guessed at. `files` are the impacted files, in
    the order the listing shows them.
    """

    files: tuple[ExportPreview, ...]


@dataclass(frozen=True)
class FileOutcome:
    """What happened to one inbox file, named by its place in the listing.

    `reason` is empty for a stored or repeat export, and never repeats a
    filename, an amount or a description. `note` says why an accepted export
    is still in the inbox, when it is. `silver_run_id` is the import run
    Silver judged for an accepted export: its own, or for a repeat, the run
    it repeats.
    """

    ordinal: int
    account_id: str
    status: str
    reason: str = ""
    note: str = ""
    silver_run_id: str = ""


@dataclass(frozen=True)
class ImportedInbox:
    """Every inbox file's outcome, the Silver rebuild and production's backup.

    `rebuilt` is `None` when no file reached Bronze: then nothing changed,
    and neither a rebuild nor a backup follows. `backup` is the set
    written after the rebuild; only production writes one.
    `backup_failure` is why production's set could not be written, if so.
    `incidents` are the cross-account duplicates the preflight found, so the
    counts can report them even when a member is refused for another reason.
    """

    files: Sequence[FileOutcome]
    rebuilt: SilverRebuild | None
    incidents: tuple[DuplicateIncident, ...] = ()
    backup: BackupSet | None = None
    backup_failure: Exception | None = None

    def counts(self) -> dict[str, int]:
        """Count the files by outcome, the incidents, and Silver's runs and drops.

        The incident counts are of the groups and of every file each one
        holds, so a member refused for another reason is counted there too.
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
            "incidents": len(self.incidents),
            "incident_files": sum(len(each.files) for each in self.incidents),
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
    log it cannot read; production's backup refuses a stores folder no set
    can cover. Found only after the Bronze writes, any of them would leave
    production written without the build and backup that must follow.
    """
    require_committed_code(profile)
    read_decision_log(profile)
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
    if parsed.failure_reason is not None:
        # The parser's verdict never repeats source content.
        return ExportPreview(
            source=source,
            account_id=account.account_id,
            skipped="format failure",
            reason=parsed.failure_reason,
            payload_id=_payload_id(content),
        )
    return ExportPreview(
        source=source,
        account_id=account.account_id,
        exported_on=exported_on,
        first_transaction=parsed.first_transaction_date,
        last_transaction=parsed.last_transaction_date,
        records=len(parsed.records),
        payload_id=_payload_id(content),
    )


def _payload_id(content: bytes) -> str:
    """Name bytes as Bronze names a payload: the SHA-256 of the bytes."""
    return sha256(content).hexdigest()


def _read_payload_id(source: Path) -> str | None:
    """Name a file's bytes now, or `None` when they cannot be read."""
    try:
        return _payload_id(source.read_bytes())
    except OSError:
        return None


def cross_account_duplicates(
    previews: Sequence[ExportPreview],
) -> tuple[DuplicateIncident, ...]:
    """Find every payload the whole inbox holds under two or more accounts.

    A preview that read its bytes has already named the payload, and that name
    is what the groups are built from: a second read could fail after the
    preview, and a group must never be lost because one did. Only a preview
    that read nothing - a misfiled name, say - is read here. A file under no
    declared account has no account to compare, and one whose bytes cannot be
    read has no bytes to compare, so neither takes part. Copies under one
    account alone are repeats, not an incident.
    """
    groups: dict[str, list[ExportPreview]] = {}
    for previewed in previews:
        if previewed.account_id == NO_ACCOUNT:
            continue
        payload_id = previewed.payload_id or _read_payload_id(previewed.source)
        if payload_id is None:
            continue
        groups.setdefault(payload_id, []).append(previewed)
    return tuple(
        DuplicateIncident(files=tuple(files))
        for files in groups.values()
        if len({each.account_id for each in files}) > 1
    )


def incident_files(incidents: Sequence[DuplicateIncident]) -> frozenset[Path]:
    """Name every file the incidents hold, so none of them is imported."""
    return frozenset(
        previewed.source for incident in incidents for previewed in incident.files
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
    """Name one imported file's outcome, and why when it was refused."""
    run = imported.import_run
    account_id = run.declared_account_id
    if run.outcome == "refused":
        reason = "; ".join(refusal_reasons(run, previewed))
        return FileOutcome(ordinal, account_id, "refused", reason)
    note = _still_in_inbox(imported, previewed.source)
    judged = run.repeat_of or run.import_run_id
    return FileOutcome(
        ordinal, account_id, run.outcome, note=note, silver_run_id=judged
    )


def import_inbox(
    lock: WriterLock,
    previews: Sequence[ExportPreview],
    declared: Mapping[Path, Coverage],
    incidents: Sequence[DuplicateIncident],
) -> ImportedInbox:
    """Import each file with its declared range, then rebuild Silver.

    `declared` maps each file that is not skipped to the range the person
    declared for it, all of them settled before this is called, and
    `incidents` are the cross-account duplicates the preflight found: every
    file they hold is refused as an incident file and never presented to
    Bronze. Files are numbered in `previews`' order, the order the person was
    shown them in.
    """
    excluded = incident_files(incidents)
    files: list[FileOutcome] = []
    for ordinal, previewed in enumerate(previews, start=1):
        if previewed.skipped:
            files.append(
                FileOutcome(
                    ordinal, previewed.account_id, previewed.skipped, previewed.reason
                )
            )
            continue
        if previewed.source in excluded:
            files.append(
                FileOutcome(ordinal, previewed.account_id, "incident", INCIDENT_REASON)
            )
            continue
        imported = import_inbox_file(lock, previewed.source, declared[previewed.source])
        files.append(_outcome(ordinal, imported, previewed))
    found = tuple(incidents)
    # Nothing was presented to Bronze when every file was skipped or held by
    # an incident: then nothing changed, and Silver is left as it stands.
    if all(previewed.skipped or previewed.source in excluded for previewed in previews):
        return ImportedInbox(files=files, incidents=found, rebuilt=None)
    rebuilt = rebuild_from_silver(lock)
    if lock.profile.name != PRODUCTION_PROFILE_NAME:
        return ImportedInbox(files=files, incidents=found, rebuilt=rebuilt)
    # Every production write is followed by a set covering Bronze and the
    # Silver just rebuilt from it. The imports are committed by now, so a set
    # that cannot be written is reported beside them, not instead of them.
    try:
        backup = back_up(lock, now=datetime.now(UTC))
    except BACKUP_FAILURES as error:
        return ImportedInbox(
            files=files, incidents=found, rebuilt=rebuilt, backup_failure=error
        )
    return ImportedInbox(files=files, incidents=found, rebuilt=rebuilt, backup=backup)
