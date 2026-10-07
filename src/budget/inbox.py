# Copyright 2026 Therkel
"""The `import` application operation: every inbox export, then Silver.

Each export in `inbox/<account_id>/` is previewed, then imported on its own
through `import_inbox_file`, under the one writer lock the command holds, and
Silver is then rebuilt from the Bronze those imports wrote. A misfiled export
is found by its preview, before anyone is asked for its range, and never
reaches Bronze.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from budget.bronze.models import ImportRun
from budget.bronze.parsers.registry import source_parser
from budget.importing import Coverage, UnknownInboxAccountError, import_inbox_file
from budget.inputs import Account, MisfiledExportError
from budget.locking import WriterLock
from budget.profiles import Profile
from budget.rebuilding import SilverRebuild, rebuild_from_silver

# The outcomes that leave a file in the inbox and make `import` exit 3.
LEFT_IN_INBOX: Final = frozenset({"refused", "misfiled"})
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
    `failure_reason` says why when the format could not read it. `misfiled`
    says why the file cannot be imported where it lies; it is empty when it
    can, and then `exported_on` is the date its filename carries.
    """

    source: Path
    account_id: str
    exported_on: date | None = None
    first_transaction: date | None = None
    last_transaction: date | None = None
    records: int = 0
    failure_reason: str | None = None
    misfiled: str = ""


@dataclass(frozen=True)
class FileOutcome:
    """What happened to one inbox file, named by its place in the listing.

    `reason` is empty for a stored or repeat export, and never repeats a
    filename, an amount or a description.
    """

    ordinal: int
    account_id: str
    status: str
    reason: str = ""


@dataclass(frozen=True)
class InboxImport:
    """Every inbox file's outcome, and the Silver rebuild that followed."""

    files: Sequence[FileOutcome]
    rebuilt: SilverRebuild

    @property
    def any_left_in_inbox(self) -> bool:
        """Whether any file was refused or misfiled, so the command exits 3."""
        return any(each.status in LEFT_IN_INBOX for each in self.files)


def inbox_exports(profile: Profile) -> tuple[Path, ...]:
    """List the files waiting in the inbox's account folders, in order."""
    if not profile.inbox.is_dir():
        return ()
    return tuple(
        sorted(
            source
            for folder in profile.inbox.iterdir()
            if folder.is_dir()
            for source in folder.iterdir()
            if source.is_file()
        )
    )


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


def preview(accounts: Mapping[str, Account], source: Path) -> ExportPreview:
    """Read one inbox file's account and transaction dates, storing nothing."""
    account = accounts.get(source.parent.name)
    if account is None:
        problem = str(UnknownInboxAccountError(source.parent.name))
        return ExportPreview(source=source, account_id=NO_ACCOUNT, misfiled=problem)
    exported_on = _exported_on(account, source)
    if isinstance(exported_on, str):
        return ExportPreview(
            source=source, account_id=account.account_id, misfiled=exported_on
        )
    parsed = source_parser(account.source_format).parse(source.read_bytes())
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


def _outcome(ordinal: int, run: ImportRun, previewed: ExportPreview) -> FileOutcome:
    """Name one imported file's outcome, and why when it was refused."""
    reason = ""
    if run.outcome == "refused":
        reason = "; ".join(refusal_reasons(run, previewed))
    return FileOutcome(ordinal, run.declared_account_id, run.outcome, reason)


def import_inbox(
    lock: WriterLock,
    previews: Sequence[ExportPreview],
    declared: Mapping[Path, Coverage],
) -> InboxImport:
    """Import each file with its declared range, then rebuild Silver.

    `declared` maps each file that is not misfiled to the range the person
    declared for it, all of them settled before this is called. Files are
    numbered in `previews`' order, the order the person was shown them in.
    """
    files = []
    for ordinal, previewed in enumerate(previews, start=1):
        if previewed.misfiled:
            files.append(
                FileOutcome(
                    ordinal, previewed.account_id, "misfiled", previewed.misfiled
                )
            )
            continue
        imported = import_inbox_file(lock, previewed.source, declared[previewed.source])
        files.append(_outcome(ordinal, imported.import_run, previewed))
    return InboxImport(files=files, rebuilt=rebuild_from_silver(lock))
