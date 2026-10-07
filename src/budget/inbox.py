# Copyright 2026 Therkel
"""The `import` application operation: every inbox export, then Silver.

Each export in `inbox/<account_id>/` is imported on its own through
`import_inbox_file`, under the one writer lock the command holds, and Silver
is then rebuilt from the Bronze those imports wrote.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from budget.bronze.models import ImportRun
from budget.bronze.parsers.registry import source_parser
from budget.importing import Coverage, import_inbox_file
from budget.inputs import load_accounts
from budget.locking import WriterLock
from budget.profiles import Profile
from budget.rebuilding import SilverRebuild, rebuild_from_silver

# The outcomes that leave a file in the inbox and make `import` exit 3.
LEFT_IN_INBOX: Final = frozenset({"refused"})


@dataclass(frozen=True)
class ExportPreview:
    """What one inbox file says about itself before anything is stored.

    The transaction dates are the file's first and last, read by its
    account's source format, so the person can check that the range they
    declare covers them. Both are `None` when the file has no records.
    """

    source: Path
    account_id: str
    first_transaction: date | None
    last_transaction: date | None


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
        """Whether any file was refused, so the command exits 3."""
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


def preview(profile: Profile, source: Path) -> ExportPreview:
    """Read one inbox file's transaction dates, storing nothing."""
    account_id = source.parent.name
    account = load_accounts(profile)[account_id]
    parsed = source_parser(account.source_format).parse(source.read_bytes())
    return ExportPreview(
        source=source,
        account_id=account_id,
        first_transaction=parsed.first_transaction_date,
        last_transaction=parsed.last_transaction_date,
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
    lock: WriterLock, coverages: Sequence[tuple[ExportPreview, Coverage]]
) -> InboxImport:
    """Import each file with its declared range, then rebuild Silver."""
    files = []
    for ordinal, (previewed, coverage) in enumerate(coverages, start=1):
        imported = import_inbox_file(lock, previewed.source, coverage)
        files.append(_outcome(ordinal, imported.import_run, previewed))
    return InboxImport(files=files, rebuilt=rebuild_from_silver(lock))
