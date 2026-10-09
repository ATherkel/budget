# Copyright 2026 Therkel
"""The worked example's records are the tables in `gold-layer.md`.

`tests/gold/worked_example.py` names each transaction by its row in the doc
(`current-04` is row 4 of the `joint-current` table), and every Gold
implementation's contract tests expect those records. So when the doc's worked
example changes, these tests fail until the records follow it.
"""

from datetime import date
from decimal import Decimal
from itertools import dropwhile, takewhile
from pathlib import Path

from budget.gold import ReportingMonth
from tests.gold.worked_example import (
    CATEGORY_ALLOCATIONS,
    CURRENT,
    MONTHLY_BALANCES,
    SAVINGS,
    TRANSACTIONS,
)

GOLD_LAYER = Path(__file__).resolve().parents[2] / "docs/architecture/gold-layer.md"
HEADING = "\n## Worked Example (synthetic)\n"


def _table_after(lead: str) -> list[list[str]]:
    """Return the body rows of the first table after the line starting `lead`."""
    text = GOLD_LAYER.read_text(encoding="utf-8")
    assert HEADING in text, "gold-layer.md lost its worked example heading"
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert f"\n{lead}" in section, f"the worked example lost its {lead!r} table"
    lines = section.split(f"\n{lead}", 1)[1].splitlines()
    table = takewhile(
        lambda line: line.startswith("|"),
        dropwhile(lambda line: not line.startswith("|"), lines),
    )
    return [[cell.strip() for cell in row.strip("|").split("|")] for row in table][2:]


def _money(cell: str) -> Decimal | None:
    return Decimal(cell.replace(",", "")) if cell else None


def _doc_transactions(lead: str) -> list[tuple[object, ...]]:
    return [
        (
            int(seq),
            date.fromisoformat(day),
            _money(amount),
            kind,
            category or None,
            transfer or None,
            _money(balance_after),
            check.split()[0],  # drops an explanation such as "(expected …)"
        )
        for seq, day, amount, kind, category, transfer, balance_after, check in (
            _table_after(lead)
        )
    ]


def _example_transactions(account_id: str) -> list[tuple[object, ...]]:
    category_of = {a.transaction_id: a.category_id for a in CATEGORY_ALLOCATIONS}
    return [
        (
            t.account_sequence,
            t.transaction_date,
            t.amount,
            t.transaction_type,
            category_of.get(t.transaction_id),
            t.transfer_group_id,
            t.balance_after,
            t.balance_check,
        )
        for t in TRANSACTIONS
        if t.account_id == account_id
    ]


def test_the_current_account_transactions_are_the_docs() -> None:
    assert _example_transactions(CURRENT) == _doc_transactions(
        "`joint-current` transactions"
    )


def test_the_savings_account_transactions_are_the_docs() -> None:
    assert _example_transactions(SAVINGS) == _doc_transactions(
        "`joint-savings` transactions"
    )


def test_the_february_allocations_are_the_docs() -> None:
    seq_of = {t.transaction_id: t.account_sequence for t in TRANSACTIONS}
    example = [
        (
            seq_of[a.transaction_id],
            a.account_id,
            a.transaction_date,
            a.category_id,
            a.amount,
        )
        for a in CATEGORY_ALLOCATIONS
        if a.account_id == CURRENT and a.transaction_date.month == 2
    ]

    doc = [
        (
            int(seq.removeprefix("seq ")),
            account,
            date.fromisoformat(day),
            category,
            _money(amount),
        )
        for _, seq, account, day, category, amount in _table_after(
            "February's allocations"
        )
    ]

    assert example == doc


def test_the_monthly_balances_are_the_docs() -> None:
    example = [
        (s.account_id, s.month, s.opening_balance, s.closing_balance, s.coverage)
        for s in MONTHLY_BALANCES
    ]

    doc = [
        (
            account,
            ReportingMonth(int(month[:4]), int(month[5:])),
            _money(opening),
            _money(closing),
            coverage,
        )
        for account, month, opening, closing, coverage, _ in _table_after(
            "Monthly balance snapshots"
        )
    ]

    assert example == doc
