# Copyright 2026 Therkel
"""Public Gold diagnostics for Kontrol."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal

from budget.analytics.measures import ZERO
from budget.analytics.measures import figures as measure_figures
from budget.analytics.overview import (
    every_row,
    report_publication,
    selected_accounts,
)
from budget.analytics.reports import (
    AccountEvidence,
    Diagnostics,
    MoneyInOut,
    Reconciliation,
    ReportContext,
    TransferSummary,
)
from budget.analytics.trust import trust
from budget.gold import (
    Coverage,
    GoldCategory,
    GoldCategoryAllocation,
    GoldRepository,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
    first_day,
    last_day,
)

_TRANSFER_PAIR_LEGS: Final[int] = 2


@dataclass(frozen=True)
class _ResidualComponents:
    """The explicit activity amounts reconciled against a snapshot."""

    income_minus_expenses: Decimal | None
    transfers: Decimal | None
    unclassified_in: Decimal | None
    unclassified_out: Decimal | None
    adjustments_in: Decimal | None
    adjustments_out: Decimal | None


@dataclass(frozen=True)
class _ReconciliationInput:
    """The public records needed to reconcile one account-month."""

    account_id: str
    display_name: str
    month: ReportingMonth
    transactions: Sequence[GoldTransaction]
    snapshot: MonthlyBalanceSnapshot | None
    previous: MonthlyBalanceSnapshot | None
    coverage: Coverage | Literal["outside_history"]
    allocations: Sequence[GoldCategoryAllocation]
    categories: Sequence[GoldCategory]


def _money_in_out(
    transactions: Sequence[GoldTransaction],
    transaction_type: TransactionType,
) -> MoneyInOut:
    """Sum one type's money in and out separately, with its observed count."""
    of_type = [
        transaction.amount
        for transaction in transactions
        if transaction.transaction_type == transaction_type
    ]
    return MoneyInOut(
        money_in=sum((amount for amount in of_type if amount > 0), ZERO),
        money_out=sum((amount for amount in of_type if amount < 0), ZERO),
        count=len(of_type),
    )


def _transfer_summary(
    gold: GoldRepository,
    selected: Sequence[GoldTransaction],
) -> TransferSummary:
    """Count selected Transfer legs and their unique public pairings."""
    transfers = [
        transaction
        for transaction in selected
        if transaction.transaction_type == "transfer"
    ]
    grouped: dict[str, int] = {}
    for transaction in gold.transactions(
        start_date=date.min,
        end_date=date.max,
        account_ids=None,
    ):
        if transaction.transfer_group_id is not None:
            grouped[transaction.transfer_group_id] = (
                grouped.get(transaction.transfer_group_id, 0) + 1
            )
    paired = sum(
        transaction.transfer_group_id is not None
        and grouped.get(transaction.transfer_group_id, 0) == _TRANSFER_PAIR_LEGS
        for transaction in transfers
    )
    return TransferSummary(
        money_in=sum(
            (transaction.amount for transaction in transfers if transaction.amount > 0),
            ZERO,
        ),
        money_out=sum(
            (transaction.amount for transaction in transfers if transaction.amount < 0),
            ZERO,
        ),
        count=len(transfers),
        paired_count=paired,
        one_sided_count=len(transfers) - paired,
    )


def _previous_month(month: ReportingMonth) -> ReportingMonth:
    """Return the calendar month before `month`."""
    index = month.year * 12 + month.month - 2
    year, zero_based_month = divmod(index, 12)
    return ReportingMonth(year, zero_based_month + 1)


def _known_sum(values: Sequence[Decimal | None]) -> Decimal | None:
    """Sum the values when every one is known."""
    total = ZERO
    for value in values:
        if value is None:
            return None
        total += value
    return total


def _expected_closing(
    opening: Decimal | None,
    components: _ResidualComponents,
) -> Decimal | None:
    """Return the closing balance implied by every explicit component."""
    return _known_sum(
        (
            opening,
            components.income_minus_expenses,
            components.transfers,
            components.unclassified_in,
            components.unclassified_out,
            components.adjustments_in,
            components.adjustments_out,
        )
    )


def _internal_residual(
    expected_closing: Decimal | None,
    closing: Decimal | None,
) -> Decimal | None:
    """Return closing less the known expected closing, or unknown with an endpoint."""
    if expected_closing is None or closing is None:
        return None
    return closing - expected_closing


def _reconciliation(data: _ReconciliationInput) -> Reconciliation:
    """Build one account-month's public reconciliation."""
    known = data.coverage != "no_data"
    measured = (
        measure_figures(data.transactions, data.allocations, data.categories)
        if known
        else None
    )
    unclassified = _money_in_out(data.transactions, "unknown")
    adjustments = _money_in_out(data.transactions, "adjustment")
    opening = None if data.snapshot is None else data.snapshot.opening_balance
    closing = None if data.snapshot is None else data.snapshot.closing_balance
    previous_closing = None if data.previous is None else data.previous.closing_balance
    components = _ResidualComponents(
        income_minus_expenses=(
            None
            if measured is None or measured.income is None or measured.expenses is None
            else measured.income - measured.expenses
        ),
        transfers=(
            sum(
                (
                    transaction.amount
                    for transaction in data.transactions
                    if transaction.transaction_type == "transfer"
                ),
                ZERO,
            )
            if known
            else None
        ),
        unclassified_in=unclassified.money_in if known else None,
        unclassified_out=unclassified.money_out if known else None,
        adjustments_in=adjustments.money_in if known else None,
        adjustments_out=adjustments.money_out if known else None,
    )
    expected_closing = _expected_closing(opening, components)
    return Reconciliation(
        account_id=data.account_id,
        display_name=data.display_name,
        month=data.month,
        opening_balance=opening,
        income_minus_expenses=components.income_minus_expenses,
        transfers=components.transfers,
        unclassified_in=components.unclassified_in,
        unclassified_out=components.unclassified_out,
        adjustments_in=components.adjustments_in,
        adjustments_out=components.adjustments_out,
        expected_closing=expected_closing,
        closing_balance=closing,
        internal_residual=_internal_residual(expected_closing, closing),
        previous_closing_balance=previous_closing,
        opening_gap=(
            opening - previous_closing
            if opening is not None and previous_closing is not None
            else None
        ),
        coverage=data.coverage,
    )


def diagnostics(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> Diagnostics:
    """Return the diagnostics `context` selects from the publication `gold` reads.

    Raise `InvalidSelectionError` for a context that breaks a selection rule,
    and `ValueError` when `gold` reads another publication than `context` names.
    """
    opened = gold.publication().publication_id
    if opened != context.publication_id:
        message = (
            f"context names publication {context.publication_id}, "
            f"but publication {opened} is open"
        )
        raise ValueError(message)
    accounts = sorted(selected_accounts(gold, context), key=lambda a: a.account_id)
    rows = every_row(gold, context.account_ids)
    judged = trust(accounts, rows, context.month, context.reference_date)
    transactions = gold.transactions(
        start_date=first_day(context.month),
        end_date=last_day(context.month),
        account_ids=context.account_ids,
    )
    known = judged.coverage.status != "no_data"
    snapshots = {row.account_id: row for row in rows if row.month == context.month}
    previous_month = _previous_month(context.month)
    previous = {row.account_id: row for row in rows if row.month == previous_month}
    incomplete = {row.account_id: row.status for row in judged.coverage.account_months}
    by_account: dict[str, list[GoldTransaction]] = {
        account.account_id: [] for account in accounts
    }
    for transaction in transactions:
        by_account[transaction.account_id].append(transaction)
    allocations = gold.category_allocations(
        start_date=first_day(context.month),
        end_date=last_day(context.month),
        account_ids=context.account_ids,
    )
    categories = gold.categories()
    return Diagnostics(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        evidence=tuple(
            AccountEvidence(
                account_id=account.account_id,
                display_name=account.display_name,
                evidence_through=account.evidence_through,
            )
            for account in accounts
        ),
        coverage=judged.coverage,
        provisional=judged.provisional,
        unclassified=(_money_in_out(transactions, "unknown") if known else None),
        adjustments=(_money_in_out(transactions, "adjustment") if known else None),
        transfers=_transfer_summary(gold, transactions) if known else None,
        reconciliations=tuple(
            _reconciliation(
                _ReconciliationInput(
                    account_id=account.account_id,
                    display_name=account.display_name,
                    month=context.month,
                    transactions=by_account[account.account_id],
                    snapshot=snapshots.get(account.account_id),
                    previous=previous.get(account.account_id),
                    coverage=(
                        snapshots[account.account_id].coverage
                        if account.account_id in snapshots
                        else incomplete.get(account.account_id, "complete")
                    ),
                    allocations=[
                        allocation
                        for allocation in allocations
                        if allocation.account_id == account.account_id
                    ],
                    categories=categories,
                )
            )
            for account in accounts
        ),
    )
