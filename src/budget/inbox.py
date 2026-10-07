# Copyright 2026 Therkel
"""The `import` application operation: every inbox export, then Silver.

Each export in `inbox/<account_id>/` is imported on its own through
`import_inbox_file`, under the one writer lock the command holds, and Silver
is then rebuilt from the Bronze those imports wrote.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from budget.importing import Coverage, import_inbox_file
from budget.locking import WriterLock
from budget.profiles import Profile
from budget.rebuilding import SilverRebuild, rebuild_from_silver


@dataclass(frozen=True)
class FileOutcome:
    """What happened to one inbox file, named by its place in the listing."""

    ordinal: int
    account_id: str
    status: str


@dataclass(frozen=True)
class InboxImport:
    """Every inbox file's outcome, and the Silver rebuild that followed."""

    files: Sequence[FileOutcome]
    rebuilt: SilverRebuild


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


def import_inbox(
    lock: WriterLock, coverages: Sequence[tuple[Path, Coverage]]
) -> InboxImport:
    """Import each file with its declared range, then rebuild Silver."""
    files = []
    for ordinal, (source, coverage) in enumerate(coverages, start=1):
        imported = import_inbox_file(lock, source, coverage)
        run = imported.import_run
        files.append(FileOutcome(ordinal, run.declared_account_id, run.outcome))
    return InboxImport(files=files, rebuilt=rebuild_from_silver(lock))
