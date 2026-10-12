# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from budget.gold.models import (
    GoldAccount,
    GoldCategory,
    GoldPublication,
    GoldTransaction,
)
from budget.gold.result import GoldRecords, GoldResult
from budget.gold.snapshots import monthly_balances
from budget.gold.transactions import gold_transactions
from budget.inputs.accounts import Account
from budget.inputs.document import ConfigurationError
from budget.inputs.snapshot import ConfigurationSnapshot
from budget.inputs.taxonomy import Taxonomy
from budget.profiles import ACCOUNTS_FILE_NAME
from budget.silver.models import AccountEvidence, SilverResult


def build(
    *,
    silver: SilverResult,
    configuration: ConfigurationSnapshot,
    publication: GoldPublication,
    late_booking_window: timedelta,
) -> GoldResult:
    """Derive Gold from a Silver result and the household's configuration.

    Nothing is classified yet: every transaction is `unknown`, and no category
    allocation, lineage or review item is published. The result is bound to
    `publication`, which the caller supplies. A month's late bookings are
    settled by an export produced `late_booking_window` or more after it ends.
    """
    transactions = gold_transactions(silver.transactions)
    problems = _closing_problems(configuration.accounts, transactions)
    if problems:
        raise ConfigurationError(problems)
    gold_accounts = tuple(
        _account(account, silver.account_evidence)
        for account in configuration.accounts.values()
    )
    records = GoldRecords(
        accounts=gold_accounts,
        categories=_categories(configuration.taxonomy),
        transactions=transactions,
        monthly_balances=monthly_balances(
            gold_accounts,
            transactions,
            silver.account_evidence,
            silver.evidence_exports,
            late_booking_window,
        ),
    )
    return GoldResult(publication, records)


def _closing_problems(
    accounts: Mapping[str, Account], transactions: Sequence[GoldTransaction]
) -> tuple[str, ...]:
    """Name every account closed before its latest transaction, by account id.

    Invariant 14 of `gold-contract.md`: no `transaction_date` falls after its
    account's `closed_on`. A transaction on the closing date itself is allowed.
    """
    for transaction in transactions:
        account = accounts[transaction.account_id]
        if (
            account.closed_on is not None
            and transaction.transaction_date > account.closed_on
        ):
            return (
                _closed_too_early(
                    account.account_id, account.closed_on, transaction.transaction_date
                ),
            )
    return ()


def _closed_too_early(account_id: str, closed_on: date, latest: date) -> str:
    """Name the account and both dates, and say how to fix it."""
    return (
        f'{ACCOUNTS_FILE_NAME}: account "{account_id}": closed_on '
        f"{closed_on.isoformat()} is before its latest transaction on "
        f"{latest.isoformat()}; correct closed_on in {ACCOUNTS_FILE_NAME}; "
        "nothing was built"
    )


def _account(account: Account, ranges: Sequence[AccountEvidence]) -> GoldAccount:
    """Publish a registry account, spanning its evidence ranges."""
    own = [r for r in ranges if r.account_id == account.account_id]
    return GoldAccount(
        account_id=account.account_id,
        display_name=account.display_name,
        account_type=account.account_type,
        ownership_scope=account.ownership_scope,
        currency=account.currency,
        closed_on=account.closed_on,
        coverage_start=min((r.covers_from for r in own), default=None),
        evidence_through=max((r.covers_through for r in own), default=None),
    )


def _categories(taxonomy: Taxonomy) -> tuple[GoldCategory, ...]:
    """Publish each category with its group flattened onto it."""
    return tuple(
        GoldCategory(
            category_id=category.category_id,
            name=category.name,
            group_id=category.group_id,
            group_name=taxonomy.groups[category.group_id].name,
            direction=taxonomy.groups[category.group_id].direction,
        )
        for category in taxonomy.categories.values()
    )
