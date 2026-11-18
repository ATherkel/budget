# Copyright 2026 Therkel
"""Public Gold diagnostics for Kontrol."""

from collections.abc import Sequence
from datetime import date
from typing import Final

from budget.analytics.measures import ZERO
from budget.analytics.overview import (
    every_row,
    report_publication,
    selected_accounts,
)
from budget.analytics.reports import (
    AccountEvidence,
    Diagnostics,
    MoneyInOut,
    ReportContext,
    TransferSummary,
)
from budget.analytics.trust import trust
from budget.gold import (
    GoldRepository,
    GoldTransaction,
    TransactionType,
    first_day,
    last_day,
)

_TRANSFER_PAIR_LEGS: Final = 2


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


def diagnostics(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> Diagnostics:
    """Return the diagnostics `context` selects from `gold`."""
    accounts = sorted(selected_accounts(gold, context), key=lambda a: a.account_id)
    rows = every_row(gold, context.account_ids)
    judged = trust(accounts, rows, context.month, context.reference_date)
    transactions = gold.transactions(
        start_date=first_day(context.month),
        end_date=last_day(context.month),
        account_ids=context.account_ids,
    )
    known = judged.coverage.status != "no_data"
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
        reconciliations=(),
    )
