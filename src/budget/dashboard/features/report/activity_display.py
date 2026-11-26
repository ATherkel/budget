# Copyright 2026 Therkel
"""Account details prepared for display, so the template only loops and prints."""

from dataclasses import dataclass

from budget.analytics import AccountActivity, AccountActivitySnapshot, ActivityRow
from budget.dashboard.display.amounts import signed_amount
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import (
    balance_observation,
    coverage_label,
    evidence_line,
    monthly_snapshot_line,
    transaction_kind,
)


@dataclass(frozen=True)
class ActivityRowView:
    """One account transaction with every value already formatted."""

    transaction_date: str
    description: str
    transaction_type: str
    amount: str


@dataclass(frozen=True)
class ActivityTableView:
    """One ready table: its accessible label, rows and empty message."""

    aria_label: str
    rows: tuple[ActivityRowView, ...]
    empty_message: str


@dataclass(frozen=True)
class ActivityFlowView:
    """One incoming or outgoing flow disclosure."""

    label: str
    total: str
    table: ActivityTableView


@dataclass(frozen=True)
class AccountActivityView:
    """One account's prepared evidence, flow tables and complete activity."""

    account_id: str
    display_name: str
    evidence: str
    coverage: str
    dated_balance: str
    earlier_observation: str
    monthly_snapshot: str
    flows: tuple[ActivityFlowView, ...]
    transactions: ActivityTableView


@dataclass(frozen=True)
class ActivityView:
    """Every account detail section, ready for its template."""

    accounts: tuple[AccountActivityView, ...]


def _row_view(row: ActivityRow, currency: str) -> ActivityRowView:
    return ActivityRowView(
        transaction_date=danish_date(row.transaction_date),
        description=row.description,
        transaction_type=transaction_kind(row),
        amount=signed_amount(row.amount, currency),
    )


def _table(
    rows: tuple[ActivityRowView, ...],
    aria_label: str,
    empty_message: str,
) -> ActivityTableView:
    return ActivityTableView(
        aria_label=aria_label,
        rows=rows,
        empty_message=empty_message,
    )


def _account_view(
    account: AccountActivitySnapshot,
    account_rows: tuple[ActivityRow, ...],
    currency: str,
) -> AccountActivityView:
    row_views = tuple(_row_view(row, currency) for row in account_rows)
    money_in_out = account.money_in_out
    known_flows = money_in_out is not None
    incoming = tuple(
        view
        for row, view in zip(account_rows, row_views, strict=True)
        if known_flows and row.amount > 0
    )
    outgoing = tuple(
        view
        for row, view in zip(account_rows, row_views, strict=True)
        if known_flows and row.amount < 0
    )
    money_in = money_in_out.money_in if money_in_out is not None else None
    money_out = money_in_out.money_out if money_in_out is not None else None
    return AccountActivityView(
        account_id=account.account_id,
        display_name=account.display_name,
        evidence=evidence_line(account.evidence_through),
        coverage=f"Dækning for måneden: {coverage_label(account.coverage)}.",
        dated_balance=balance_observation(
            account.dated_balance,
            currency,
            "Ingen observation i måneden",
        ),
        earlier_observation=balance_observation(
            account.earlier_observation,
            currency,
            "Ingen tidligere observation",
        ),
        monthly_snapshot=monthly_snapshot_line(
            account.monthly_snapshot,
            currency,
        ),
        flows=(
            ActivityFlowView(
                label="Ind",
                total=signed_amount(money_in, currency),
                table=_table(
                    incoming,
                    f"Indgående posteringer for {account.display_name}",
                    "Ingen observerede indgående posteringer i måneden.",
                ),
            ),
            ActivityFlowView(
                label="Ud",
                total=signed_amount(money_out, currency),
                table=_table(
                    outgoing,
                    f"Udgående posteringer for {account.display_name}",
                    "Ingen observerede udgående posteringer i måneden.",
                ),
            ),
        ),
        transactions=_table(
            row_views,
            f"Posteringer for {account.display_name}",
            "Ingen observerede posteringer i måneden.",
        ),
    )


def activity_view(activity: AccountActivity) -> ActivityView:
    """Return account activity prepared for its template."""
    by_account: dict[str, list[ActivityRow]] = {}
    for transaction in activity.transactions:
        by_account.setdefault(transaction.account_id, []).append(transaction)

    return ActivityView(
        accounts=tuple(
            _account_view(
                account,
                tuple(by_account.get(account.account_id, ())),
                activity.currency,
            )
            for account in activity.accounts
        )
    )
