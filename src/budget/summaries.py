# Copyright 2026 Therkel
"""The terminal summaries the pipeline commands end with.

These lines reach the operator's terminal, never a routine log, and they carry
only identifiers and existing reason codes: a run's validation-error codes and
the kinds of the review items it raised. No amount, balance, description, bank
category, original filename, transaction id or validation message appears.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from budget.bronze.models import ImportRun
from budget.inbox import LEFT_IN_INBOX, FileOutcome, ImportedInbox
from budget.rebuilding import SilverRebuild
from budget.reviewing import OpenReview
from budget.silver import ImportRunResult, ReviewItem, SilverResult


@dataclass(frozen=True)
class _Row:
    """One import run's terminal line: its own status and reason codes."""

    import_run_id: str
    account_id: str
    status: str
    reasons: tuple[str, ...]


def rebuild_summary(rebuild: SilverRebuild) -> str:
    """Report one rebuild's import runs and counts, by account and by run."""
    rows = [_row(run, rebuild) for run in rebuild.runs]
    lines = [_bronze_line(rebuild.runs), *_account_lines(rows, rebuild.result)]
    lines.extend(_run_line(row) for row in rows)
    return "\n".join(lines) + "\n"


def _row(run: ImportRun, rebuild: SilverRebuild) -> _Row:
    """Name one run's status and reasons, following a repeat to its original."""
    if run.outcome == "refused":
        return _Row(run.import_run_id, run.declared_account_id, "refused", ())
    if run.outcome == "repeat":
        original = _original(run, rebuild.runs)
        status, reasons = (
            ("repeat", ()) if original is None else _repeat(original, rebuild.result)
        )
        return _Row(run.import_run_id, run.declared_account_id, status, reasons)
    status, reasons = _outcome(run, rebuild.result)
    return _Row(run.import_run_id, run.declared_account_id, status, reasons)


def _original(run: ImportRun, runs: Sequence[ImportRun]) -> ImportRun | None:
    """Return the canonical run a repeat repeats, when Bronze recorded one."""
    return next((each for each in runs if each.import_run_id == run.repeat_of), None)


def _repeat(original: ImportRun, result: SilverResult) -> tuple[str, tuple[str, ...]]:
    """Report a repeat as the outcome of the run it repeats."""
    status, reasons = _outcome(original, result)
    return f"repeat {status}", reasons


def _outcome(run: ImportRun, result: SilverResult) -> tuple[str, tuple[str, ...]]:
    """Return a stored run's Silver status and its existing reason codes."""
    found = _result_of(run, result)
    if found is None:
        return "unrecorded", ()
    return found.status, _reasons(found, result.review_items)


def _result_of(run: ImportRun, result: SilverResult) -> ImportRunResult | None:
    """Find the Silver verdict for one stored run, if the build recorded one."""
    return next(
        (
            each
            for each in result.import_run_results
            if each.import_run_id == run.import_run_id
        ),
        None,
    )


def _reasons(found: ImportRunResult, items: Sequence[ReviewItem]) -> tuple[str, ...]:
    """Return the run's error codes and review kinds, each named once."""
    kinds = {item.review_item_id: item.kind for item in items}
    raised = {kinds[item_id] for item_id in found.review_item_ids if item_id in kinds}
    return tuple(sorted({error.code for error in found.errors} | raised))


def _bronze_line(runs: Sequence[ImportRun]) -> str:
    """Count every Bronze run by its recorded outcome."""
    counted = Counter(run.outcome for run in runs)
    noun = "import run" if len(runs) == 1 else "import runs"
    return (
        f"Bronze   {len(runs)} {noun}: {counted['stored']} stored,"
        f" {counted['repeat']} repeat, {counted['refused']} refused"
    )


def _account_lines(rows: Sequence[_Row], result: SilverResult) -> list[str]:
    """One line per account, with its runs' outcomes and its dropped count."""
    drops = Counter(
        item.account_id
        for item in result.review_items
        if item.kind == "dropped-transaction"
    )
    accounts = sorted({row.account_id for row in rows})
    return [_account_line(account, rows, drops[account]) for account in accounts]


def _account_line(account_id: str, rows: Sequence[_Row], dropped: int) -> str:
    """Count one account's runs by outcome, plus its dropped transactions."""
    counted = Counter(
        _bucket(row.status) for row in rows if row.account_id == account_id
    )
    return (
        f"Account  {account_id}: {counted['accepted']} admitted,"
        f" {counted['quarantined']} quarantined, {counted['refused']} refused,"
        f" {counted['repeat']} repeat, {dropped} dropped"
    )


def _bucket(status: str) -> str:
    """Name the bucket a run's status counts in, a repeat counted as repeat."""
    return "repeat" if status.startswith("repeat") else status


def _run_line(row: _Row) -> str:
    """One import run's line: its identifiers, status and reason codes."""
    reasons = f"  {', '.join(row.reasons)}" if row.reasons else ""
    return f"Run  {row.import_run_id}  {row.account_id}  {row.status}{reasons}"


def import_summary(imported: ImportedInbox) -> str:
    """Report each inbox file by its number, then Silver's counts.

    A file is named by its number in the listing the prompt showed, never by
    its filename, which can carry a bank account number.
    """
    lines = [_file_line(each) for each in imported.files]
    if imported.rebuilt is None:
        lines.append("Nothing was imported.")
        return "\n".join(lines) + "\n"
    counts = imported.counts()
    lines.append(
        f"Silver   {counts['admitted']} admitted, {counts['quarantined']}"
        f" quarantined, {counts['dropped']} dropped"
    )
    if imported.backup is not None:
        lines.append(f"Backup   backup set {imported.backup.name} written")
    return "\n".join(lines) + "\n"


def _file_line(outcome: FileOutcome) -> str:
    """One inbox file's line: its number, account, outcome and reason."""
    line = f"[{outcome.ordinal}] {outcome.account_id}  {outcome.status}"
    if outcome.reason:
        line += f": {outcome.reason}"
    if outcome.status in LEFT_IN_INBOX:
        line += "; it stays in the inbox"
    if outcome.note:
        line += f"; {outcome.note}"
    return line


def review_summary(items: Sequence[OpenReview]) -> str:
    """Report each open review item, and nothing at all when there are none."""
    return "".join(_review_line(entry) for entry in items)


def _review_line(entry: OpenReview) -> str:
    """One open item: its references, kind, dates, and what settles it."""
    item = entry.item
    parts = [
        item.review_item_id,
        item.kind,
        item.account_id,
        f"{item.date_from}..{item.date_to}",
    ]
    if entry.import_run_id is not None:
        parts.append(f"run {entry.import_run_id}")
    if item.payload_ids:
        parts.append(f"payload {', '.join(item.payload_ids)}")
    if item.transaction_id is not None:
        # A transaction is named by its 8-character handle, never in full.
        parts.append(f"handle {item.transaction_id[:8]}")
    return "  ".join(parts) + "\n"
