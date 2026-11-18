# Copyright 2026 Therkel
"""Account activity and its public Transfer evidence."""

from datetime import date, timedelta

from budget.analytics.overview import (
    every_row,
    report_publication,
    selected_accounts,
)
from budget.analytics.reports import (
    AccountActivity,
    AccountActivitySnapshot,
    BankBalanceObservation,
    MonthlyBalanceObservation,
    ReportContext,
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


def account_activity(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> AccountActivity:
    """Return the account activity `context` selects from `gold`."""
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
        )

    return AccountActivity(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        accounts=tuple(account(a) for a in accounts),
        coverage=judged.coverage,
        provisional=judged.provisional,
    )
