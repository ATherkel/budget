# Copyright 2026 Therkel
"""Account activity and its public Transfer evidence."""

from datetime import date, timedelta

from budget.analytics.measures import money_in_out
from budget.analytics.overview import (
    every_row,
    report_publication,
    selected_accounts,
)
from budget.analytics.reports import (
    AccountActivity,
    AccountActivitySnapshot,
    ActivityRow,
    BankBalanceObservation,
    MonthlyBalanceObservation,
    ReportContext,
    TransferPairing,
)
from budget.analytics.trust import trust
from budget.gold import (
    GoldAccount,
    GoldRepository,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    first_day,
    last_day,
)


def _last_transaction(
    gold: GoldRepository,
    account_id: str,
    start: date,
    end: date,
) -> GoldTransaction | None:
    """Return the highest-sequence transaction of one account in the dates."""
    transactions = gold.transactions(
        start_date=start, end_date=end, account_ids={account_id}
    )
    if not transactions:
        return None
    return max(
        transactions,
        key=lambda transaction: transaction.account_sequence,
    )


def _observation(transaction: GoldTransaction | None) -> BankBalanceObservation | None:
    """Return the transaction's dated bank observation without substituting a value."""
    if transaction is None:
        return None
    return BankBalanceObservation(
        transaction_date=transaction.transaction_date,
        balance_after=transaction.balance_after,
    )


def _monthly_snapshot(
    row: MonthlyBalanceSnapshot | None,
) -> MonthlyBalanceObservation | None:
    """Return the published snapshot separately from transaction observations."""
    if row is None:
        return None
    return MonthlyBalanceObservation(
        opening_balance=row.opening_balance,
        closing_balance=row.closing_balance,
        coverage=row.coverage,
        late_bookings_settled=row.late_bookings_settled,
    )


def _public_pair(
    groups: dict[str, list[GoldTransaction]],
    transaction: GoldTransaction,
) -> tuple[TransferPairing | None, GoldTransaction | None]:
    """Return a Transfer's public pairing and uniquely identifiable other leg."""
    if transaction.transaction_type != "transfer":
        return None, None
    if transaction.transfer_group_id is None:
        return "one_sided", None
    other_legs = [
        leg
        for leg in groups[transaction.transfer_group_id]
        if leg.transaction_id != transaction.transaction_id
    ]
    if len(other_legs) == 1:
        return "paired", other_legs[0]
    return "one_sided", None


def _activity_rows(
    gold: GoldRepository,
    context: ReportContext,
) -> tuple[ActivityRow, ...]:
    """Return selected transactions and the public account of a Transfer's other leg."""
    month_start = first_day(context.month)
    month_end = last_day(context.month)
    selected = gold.transactions(
        start_date=month_start,
        end_date=month_end,
        account_ids=context.account_ids,
    )
    every_transaction = gold.transactions(
        start_date=date.min,
        end_date=date.max,
        account_ids=None,
    )
    groups: dict[str, list[GoldTransaction]] = {}
    for transaction in every_transaction:
        if transaction.transfer_group_id is not None:
            groups.setdefault(transaction.transfer_group_id, []).append(transaction)
    names = {account.account_id: account.display_name for account in gold.accounts()}
    ordered = sorted(
        selected,
        key=lambda transaction: (
            transaction.transaction_date,
            transaction.account_id,
            transaction.account_sequence,
        ),
        reverse=True,
    )

    def row(transaction: GoldTransaction) -> ActivityRow:
        pairing, counterpart = _public_pair(groups, transaction)
        return ActivityRow(
            transaction_date=transaction.transaction_date,
            description=transaction.description,
            account_id=transaction.account_id,
            account_display_name=names[transaction.account_id],
            amount=transaction.amount,
            transaction_type=transaction.transaction_type,
            transfer_pairing=pairing,
            counterpart_account_id=(
                None if counterpart is None else counterpart.account_id
            ),
            counterpart_account_display_name=(
                None if counterpart is None else names[counterpart.account_id]
            ),
            counterpart_transaction_date=(
                None if counterpart is None else counterpart.transaction_date
            ),
        )

    return tuple(row(transaction) for transaction in ordered)


def account_activity(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> AccountActivity:
    """Return the account activity `context` selects from `gold`."""
    opened = gold.publication().publication_id
    if opened != context.publication_id:
        message = (
            f"context names publication {context.publication_id}, "
            f"but publication {opened} is open"
        )
        raise ValueError(message)
    accounts = sorted(selected_accounts(gold, context), key=lambda a: a.account_id)
    rows = every_row(gold, context.account_ids)
    judged = trust(
        accounts,
        rows,
        context.month,
        context.reference_date,
    )
    month_start = first_day(context.month)
    month_end = last_day(context.month)
    snapshots = {row.account_id: row for row in rows if row.month == context.month}
    incomplete = {row.account_id: row.status for row in judged.coverage.account_months}

    def account(
        account: GoldAccount,
    ) -> AccountActivitySnapshot:
        snapshot = snapshots.get(account.account_id)
        earlier_end = month_start - timedelta(days=1)
        return AccountActivitySnapshot(
            account_id=account.account_id,
            display_name=account.display_name,
            dated_balance=_observation(
                _last_transaction(
                    gold,
                    account.account_id,
                    month_start,
                    month_end,
                )
            ),
            earlier_observation=_observation(
                _last_transaction(
                    gold,
                    account.account_id,
                    date.min,
                    earlier_end,
                )
            ),
            monthly_snapshot=_monthly_snapshot(snapshot),
            evidence_through=account.evidence_through,
            coverage=(
                snapshot.coverage
                if snapshot is not None
                else incomplete.get(account.account_id, "complete")
            ),
            money_in_out=money_in_out(
                gold.transactions(
                    start_date=month_start,
                    end_date=month_end,
                    account_ids={account.account_id},
                )
            ),
        )

    return AccountActivity(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        accounts=tuple(account(a) for a in accounts),
        coverage=judged.coverage,
        provisional=judged.provisional,
        transactions=_activity_rows(gold, context),
    )
