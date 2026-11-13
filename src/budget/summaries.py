# Copyright 2026 Therkel
"""The terminal summaries the pipeline commands end with.

These lines reach the operator's terminal, never a routine log. Rebuild and
import summaries carry only identifiers and existing reason codes. Review also
prints the account, date, amount, description, bank category and short handle
needed to classify a target; that financial context is permitted on stdout and
is never passed to routine logging. No balance, original filename, full
transaction id or arbitrary validation message appears.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Protocol

from budget.bronze.models import ImportRun
from budget.completeness import (
    AccountEvidenceStatus,
    AccountMonthCompleteness,
    Completeness,
)
from budget.finding import FindResult
from budget.gold import ClassificationReviewKind
from budget.gold.diff import compare_publications, review_line
from budget.gold.models import GoldReviewTarget
from budget.gold.repository import PublicationUnavailableError
from budget.gold.store import GoldStore, PointerMove
from budget.inbox import LEFT_IN_INBOX, FileOutcome, ImportedInbox
from budget.profiles import Profile
from budget.rebuilding import GoldRebuild, SilverRebuild, SilverReviews
from budget.reviewing import OpenGoldReview, OpenReview, OpenReviews
from budget.silver import ImportRunResult, ReviewItem, SilverResult
from budget.suggesting import BankLabels

_MAX_BYTE_CODE_POINT: Final = 0xFF
_SETTLEMENT_GUIDANCE: Final[Mapping[ClassificationReviewKind, str]] = MappingProxyType(
    {
        "unclassified": "choose a rule or {choice}",
        "rule-conflict": ("adjust rule priority or narrow a rule; otherwise {choice}"),
        "sign-mismatch": (
            "choose a narrower rule; or {choice} "
            "(a category decision cannot apply to zero)"
        ),
        "ambiguous-transfer": (
            "pair the intended legs if their amounts still cancel; otherwise {choice}"
        ),
        "unmatched-transfer": (
            "wait for the next import or pair the transfer if the counterpart "
            "appears and amounts cancel; use one-sided-transfer only if the "
            "counterpart is outside its managed period; otherwise {choice}"
        ),
        "decision-not-applicable": "supersede or retract the decision",
    }
)


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


def completeness_summary(found: Completeness) -> str:
    """Report what `status` found, saying plainly what could not be shown."""
    published = found.published
    if published is None:
        lines = ["Published figures: unavailable, nothing is published"]
    else:
        lines = [f"Published figures: publication {published.publication_id} (current)"]
        lines.extend(_month_line(each) for each in published.months)
        lines.append("Unclassified money, by account and month")
        lines.extend(_unclassified_line(each) for each in published.months)
    lines.extend(_review_lines(found))
    lines.append("Import evidence (operational, apart from published figures)")
    accounts = () if found.evidence is None else found.evidence.accounts
    if found.evidence is not None and found.evidence.unreadable is not None:
        lines.append(f"  unavailable: could not be read: {found.evidence.unreadable}")
    elif not accounts:
        lines.append("  none recorded")
    for each in accounts:
        lines.extend(_evidence_lines(each))
    return "\n".join(lines) + "\n"


def _review_lines(found: Completeness) -> list[str]:
    """Say the open review items per kind, Silver's and Gold's on their own lines."""
    lines: list[str] = []
    if found.evidence is not None:
        silver = (
            "unavailable"
            if found.evidence.unreadable is not None
            else _kinds(found.evidence.review_kinds)
        )
        lines.append(f"  Silver (operational): {silver}")
    if found.published is not None:
        lines.append(
            f"  Gold (publication {found.published.publication_id}): "
            f"{_kinds(found.published.review_kinds)}"
        )
    return ["Open review items", *lines] if lines else []


def _kinds(counts: tuple[tuple[str, int], ...]) -> str:
    """Say review item counts as `kind n`, or `none` when there are none."""
    return ", ".join(f"{kind} {count}" for kind, count in counts) or "none"


def _date_or_none(day: date | None) -> str:
    """Say a date, or `none` when no evidence supplies one."""
    return "none" if day is None else day.isoformat()


def _evidence_lines(each: AccountEvidenceStatus) -> list[str]:
    """Say one account's latest export, Evidence through, and quarantined runs."""
    lines = [
        (
            f"{each.account_id}  latest export {_date_or_none(each.latest_export)}"
            f"  evidence through {_date_or_none(each.evidence_through)}"
        )
    ]
    if not each.quarantined:
        return [*lines, "  quarantined  none"]
    for run in each.quarantined:
        codes = ", ".join(sorted({error.code for error in run.errors}))
        lines.append(
            f"  quarantined  {run.import_run_id}  {run.covered_from}..{run.covered_to}"
            + (f"  {codes}" if codes else "")
        )
    return lines


def _unclassified_line(each: AccountMonthCompleteness) -> str:
    """Say one account-month's unclassified money in and out, and how many."""
    money = each.unclassified
    prefix = f"  {each.account_id}  {each.month.year:04d}-{each.month.month:02d}  "
    if money is None:
        return f"{prefix}unavailable: no data"
    return (
        f"{prefix}in {money.money_in} {each.currency}, "
        f"out {money.money_out} {each.currency}, "
        f"{money.count} {'transaction' if money.count == 1 else 'transactions'}"
    )


def _month_line(each: AccountMonthCompleteness) -> str:
    """Say one account-month's coverage, and why its figures may still change."""
    line = (
        f"{each.account_id}  {each.month.year:04d}-{each.month.month:02d}  "
        f"{each.coverage.replace('_', ' ')}"
    )
    if not each.provisional:
        return line
    reasons = ", ".join(reason.replace("_", " ") for reason in each.provisional)
    return f"{line}  provisional: {reasons}"


def gold_line(rebuilt: GoldRebuild) -> str:
    """Say whether a Gold rebuild published, and which publication is current."""
    number = rebuilt.publication.publication_id
    if rebuilt.published:
        return f"Gold     published publication {number} (cause build)"
    return (
        "Gold     the recipe is unchanged; nothing was published "
        f"(publication {number} stays current)"
    )


def undo_line(move: PointerMove) -> str:
    """Report the publication restored by an undo, and what it replaced."""
    return (
        f"Gold     publication {move.to_publication_id} is current "
        f"(was {move.from_publication_id}; cause {move.cause})"
    )


def _notice(line: str, silver_reviews: SilverReviews) -> str:
    """Add Silver's review changes to a line that compares no publications."""
    reviews = review_line(silver_reviews.before, silver_reviews.after)
    return f"{line}\n" if reviews is None else f"{line}\n{reviews}\n"


def publication_changes(
    profile: Profile, rebuilt: GoldRebuild, silver_reviews: SilverReviews
) -> str:
    """Describe the terminal-only publication change after a successful build."""
    number = rebuilt.publication.publication_id
    if not rebuilt.published:
        return _notice(
            f"Changes  no publication was built; publication {number} remains current.",
            silver_reviews,
        )
    with GoldStore(profile, read_only=True) as gold:
        moves = gold.pointer_history()
        if not moves or moves[-1].from_publication_id is None:
            return _notice(
                "Changes  no previous publication to compare; "
                f"publication {number} is current.",
                silver_reviews,
            )
        previous_id = moves[-1].from_publication_id
        current_id = moves[-1].to_publication_id
        try:
            previous = gold.open(previous_id)
        except PublicationUnavailableError:
            return _notice(
                f"Changes  publication {previous_id} is no longer retained, so "
                f"nothing can be compared; publication {number} is current.",
                silver_reviews,
            )
        lines = compare_publications(
            previous,
            gold.open(current_id),
            previous_reviews=(*silver_reviews.before, *gold.reviews(previous_id).items),
            current_reviews=(*silver_reviews.after, *gold.reviews(current_id).items),
        )
    return "\n".join(lines or ("Changes  no measure or review item changed.",)) + "\n"


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


def import_summary(imported: ImportedInbox, *, diff_text: str = "") -> str:
    """Report each inbox file by its number, then Silver's counts.

    A file is named by its number in the listing the prompt showed, never by
    its filename, which can carry a bank account number.
    """
    if imported.held_back is not None:
        lines = [_file_line(each, {}) for each in imported.files]
        lines.append("The rebuild stopped before Gold was published.")
        if imported.backup is not None:
            lines.append(f"Backup   backup set {imported.backup.name} written")
        return "\n".join(lines) + "\n"
    if imported.rebuilt is None:
        lines = [_file_line(each, {}) for each in imported.files]
        lines.append("Nothing was imported.")
        return "\n".join(lines) + "\n"
    quarantined = _quarantined(imported.rebuilt.result)
    lines = [_file_line(each, quarantined) for each in imported.files]
    counts = imported.counts()
    lines.append(
        f"Silver   {counts['admitted']} admitted, {counts['quarantined']}"
        f" quarantined, {counts['dropped']} dropped"
    )
    if imported.published is not None:
        lines.append(gold_line(imported.published))
        lines.extend(diff_text.rstrip().splitlines())
    if imported.backup is not None:
        lines.append(f"Backup   backup set {imported.backup.name} written")
    return "\n".join(lines) + "\n"


def _quarantined(result: SilverResult) -> dict[str, tuple[str, ...]]:
    """Map each run Silver quarantined to its reason codes."""
    return {
        found.import_run_id: _reasons(found, result.review_items)
        for found in result.import_run_results
        if found.status == "quarantined"
    }


def _file_line(outcome: FileOutcome, quarantined: Mapping[str, tuple[str, ...]]) -> str:
    """One inbox file's line: its number, account, outcome and reasons.

    An accepted export Silver quarantined says so, with Silver's reason
    codes, so a quarantine is read beside the file it belongs to.
    """
    line = f"[{outcome.ordinal}] {outcome.account_id}  {outcome.status}"
    if outcome.reason:
        line += f": {outcome.reason}"
    if outcome.status in LEFT_IN_INBOX:
        line += "; it stays in the inbox"
    codes = quarantined.get(outcome.silver_run_id)
    if codes is not None:
        line += f"; Silver quarantined it: {', '.join(codes)}"
    if outcome.note:
        line += f"; {outcome.note}"
    return line


def review_summary(reviews: OpenReviews) -> str:
    """Report Silver and Gold items, then each unshown quarantined run."""
    return "".join(
        [
            *(_review_line(entry) for entry in reviews.items),
            *(_gold_review_line(entry) for entry in reviews.gold_items),
            *(_quarantined_line(run) for run in reviews.runs),
        ]
    )


def _gold_review_line(entry: OpenGoldReview) -> str:
    """One Gold item: stable references, publication and target contexts."""
    item = entry.item
    handles = ", ".join(transaction_id[:8] for transaction_id in item.transaction_ids)
    parts = [
        item.review_item_id,
        item.kind,
        "gold",
        f"publication {entry.publication_id}",
    ]
    if handles:
        parts.append(f"targets {handles}")
    if item.rule_ids:
        parts.append(f"rules {', '.join(item.rule_ids)}")
    if item.decision_id is not None:
        parts.append(f"decision {item.decision_id}")
    header = "  ".join(parts)
    targets = "".join(
        f"\n{gold_target_line(target, _bank_category(target))}"
        for target in entry.targets
    )
    return f"{header}{targets}\n{_gold_settlement_line(entry)}\n"


def _gold_settlement_line(entry: OpenGoldReview) -> str:
    """Name the decisions that can settle this kind, and their conditions."""
    item = entry.item
    if item.kind == "decision-not-applicable" and item.decision_id is not None:
        guidance = f"supersede or retract decision {item.decision_id}"
    else:
        guidance = _SETTLEMENT_GUIDANCE[item.kind].format(
            choice=_classification_choice(entry.targets)
        )
    return f"  settle  {guidance}"


def _classification_choice(targets: Sequence[GoldReviewTarget]) -> str:
    """Offer category decisions only for nonzero targets in the published item."""
    has_zero = any(target.amount.is_zero() for target in targets)
    has_nonzero = any(not target.amount.is_zero() for target in targets)
    if has_zero and has_nonzero:
        return (
            "classify zero-amount targets as adjustments and nonzero targets as a "
            "category or adjustment"
        )
    if has_zero:
        return "classify a zero-amount target as an adjustment"
    return "classify a target as a category or adjustment"


class _TargetContext(Protocol):
    """The shared fields of a transaction-shaped target line."""

    @property
    def transaction_id(self) -> str:
        """Return the full transaction identifier."""
        ...

    @property
    def account_id(self) -> str:
        """Return the account identifier."""
        ...

    @property
    def transaction_date(self) -> date:
        """Return the transaction date."""
        ...

    @property
    def amount(self) -> Decimal:
        """Return the signed amount."""
        ...

    @property
    def currency(self) -> str:
        """Return the account currency."""
        ...

    @property
    def description(self) -> str:
        """Return the transaction description."""
        ...


def _bank_category(target: GoldReviewTarget) -> str:
    """Render the review target's bank category as its target-line detail."""
    category = (
        "unavailable"
        if target.bank_category is None
        else _terminal_text(target.bank_category)
    )
    return f"bank category {category}"


def gold_target_line(
    target: _TargetContext, detail: str, *, handle: str | None = None
) -> str:
    """One target's account, date, money, description, and contextual detail."""
    shown_handle = target.transaction_id[:8] if handle is None else handle
    return (
        f"  target {shown_handle}  {target.account_id}"
        f"  {target.transaction_date.isoformat()}"
        f"  {target.amount} {target.currency}"
        f"  {_quoted_terminal_text(target.description)}"
        f"  {detail}"
    )


def find_summary(found: FindResult) -> str:
    """Render each found transaction through the review target formatter."""
    if not found.matches:
        return "No transactions matched.\n"
    lines: list[str] = []
    for match in found.matches:
        category = match.category_id or "unclassified"
        lines.append(
            f"{gold_target_line(match, f'category {category}', handle=match.handle)}\n"
        )
    return "".join(lines)


def suggest_rules_summary(labels: BankLabels) -> str:
    """One line per bank label pair, then one for the transactions with none."""
    lines: list[str] = []
    for pair in labels.pairs:
        sums = ", ".join(
            f"{total} {currency}" for currency, total in sorted(pair.sums.items())
        )
        lines.append(
            f"{pair.category} / {pair.subcategory or '(none)'}"
            f"  {_transactions(pair.transactions)}  {sums}\n"
        )
    if labels.uncategorized:
        lines.append(f"No bank category  {_transactions(labels.uncategorized)}\n")
    return "".join(lines)


def _transactions(count: int) -> str:
    """`count` with the noun `transaction`, singular for exactly one."""
    return f"{count} {'transaction' if count == 1 else 'transactions'}"


def _quoted_terminal_text(text: str) -> str:
    """Quote free text and escape control characters so it stays on one line."""
    escaped = _terminal_text(text).replace('"', '\\"')
    return f'"{escaped}"'


def _terminal_text(text: str) -> str:
    """Escape backslashes and non-printing characters without hiding Unicode."""
    escaped: list[str] = []
    for character in text:
        if character == "\\":
            escaped.append("\\\\")
        elif character.isprintable():
            escaped.append(character)
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\t":
            escaped.append("\\t")
        else:
            codepoint = ord(character)
            escaped.append(
                f"\\x{codepoint:02x}"
                if codepoint <= _MAX_BYTE_CODE_POINT
                else f"\\u{codepoint:04x}"
            )
    return "".join(escaped)


def _quarantined_line(run: ImportRunResult) -> str:
    """One quarantined run: its identifiers, covered dates and error codes."""
    parts = [
        "Run",
        run.import_run_id,
        run.account_id,
        f"{run.covered_from}..{run.covered_to}",
    ]
    codes = sorted({error.code for error in run.errors})
    if codes:
        parts.append(", ".join(codes))
    return "  ".join(parts) + "\n"


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
