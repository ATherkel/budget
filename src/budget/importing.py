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
from pathlib import Path
from typing import Final

from budget.bronze import BronzeStore, ImportDeclaration, ImportRun
from budget.inputs import load_accounts
from budget.locking import WriterLock

IMPORT_LOG_FORMAT: Final = 1


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


def import_inbox_file(
    lock: WriterLock,
    source: Path,
    coverage: Coverage,
) -> InboxImport:
    """Import one inbox file under the held writer lock."""
    profile = lock.profile
    account_id = source.parent.name
    account = load_accounts(profile)[account_id]
    declaration = ImportDeclaration(
        declared_account_id=account_id,
        source_format=account.source_format,
        covers_from=coverage.covers_from,
        covers_through=coverage.covers_through,
        exported_on=coverage.exported_on,
    )
    with BronzeStore(profile) as store:
        run = store.import_file(source, declaration)
        content = store.get_payload(run.payload_id).content

    archive_path = f"{account_id}/{source.name}"
    _write_durably(profile.exports / account_id / source.name, content)
    _append_to_log(profile.import_log_file, _log_entry(run, archive_path))
    source.unlink()
    return InboxImport(import_run=run, archive_path=archive_path, left_in_inbox=False)
