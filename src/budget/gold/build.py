# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from budget.gold.classification import classify
from budget.gold.models import (
    GoldAccount,
    GoldCategory,
    GoldPublication,
    GoldTransaction,
)
from budget.gold.result import GoldLineageRecords, GoldRecords, GoldResult
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

    Transactions are classified by the configuration's rules. The result is
    bound to `publication`, which the caller supplies. A month's late bookings
    are settled by an export produced `late_booking_window` or more after it
    ends. A Silver transaction on an account the registry does not declare
    refuses the build, so no fact is published without its account. So does
    an account whose `closed_on` falls before its latest booked transaction,
    so no fact falls outside its account's managed period.
    """
    _require_declared_accounts(silver, configuration.accounts)
    transactions = gold_transactions(silver.transactions)
    problems = _closing_problems(configuration.accounts, transactions)
    if problems:
        raise ConfigurationError(problems)
    gold_accounts = tuple(
        _account(account, silver.account_evidence)
        for account in configuration.accounts.values()
    )
    classified = classify(transactions, silver.transactions, configuration)
    records = GoldRecords(
        accounts=gold_accounts,
        categories=_categories(configuration.taxonomy),
        transactions=classified.transactions,
        category_allocations=classified.allocations,
        monthly_balances=monthly_balances(
            gold_accounts,
            classified.transactions,
            silver.account_evidence,
            silver.evidence_exports,
            late_booking_window,
        ),
    )
    lineage = GoldLineageRecords(
        classification_review_items=classified.review_items,
        transaction_lineage=classified.lineage,
    )
    return GoldResult(publication, records, lineage)


def _require_declared_accounts(
    silver: SilverResult, accounts: Mapping[str, Account]
) -> None:
    """Refuse Silver transactions on accounts the registry no longer declares.

    An account is retired with `closed_on`, never by deleting it, so a missing
    one is a configuration error rather than a reason to drop its facts.
    """
    undeclared = sorted({t.account_id for t in silver.transactions} - accounts.keys())
    if undeclared:
        raise ConfigurationError(tuple(map(_undeclared_account, undeclared)))


def _undeclared_account(account_id: str) -> str:
    """Name a Silver account that the registry does not declare."""
    return (
        f'{ACCOUNTS_FILE_NAME}: account "{account_id}" is not declared, but '
        "Silver holds transactions for it; restore it, with closed_on set if "
        "the account has closed, before rebuilding; nothing was published"
    )


def _closing_problems(
    accounts: Mapping[str, Account], transactions: Sequence[GoldTransaction]
) -> tuple[str, ...]:
    """Name every account closed before its latest transaction, by account id.

    Invariant 14 of `gold-contract.md`: no `transaction_date` falls after its
    account's `closed_on`. A transaction on the closing date itself is allowed.
    """
    latest_transaction: dict[str, date] = {}
    for transaction in transactions:
        account_id = transaction.account_id
        latest_transaction[account_id] = max(
            latest_transaction.get(account_id, transaction.transaction_date),
            transaction.transaction_date,
        )

    return tuple(
        _closed_too_early(account_id, closed_on, latest)
        for account_id in sorted(accounts)
        if (closed_on := accounts[account_id].closed_on) is not None
        and (latest := latest_transaction.get(account_id)) is not None
        and closed_on < latest
    )


def _closed_too_early(account_id: str, closed_on: date, latest: date) -> str:
    """Name the account and both dates, and say how to fix it."""
    return (
        f'{ACCOUNTS_FILE_NAME}: account "{account_id}": closed_on '
        f"{closed_on.isoformat()} is before its latest transaction on "
        f"{latest.isoformat()}; correct closed_on in {ACCOUNTS_FILE_NAME}; "
        "nothing was published"
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
