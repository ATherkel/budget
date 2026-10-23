# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from budget.gold.classification import classify
from budget.gold.decisions import Classify, GoldDecision, OneSidedTransfer, targets
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
from budget.profiles import (
    ACCOUNTS_FILE_NAME,
    DECISION_LOG_FILE_NAME,
    MAX_LATE_BOOKING_DAYS,
)
from budget.silver.models import AccountEvidence, SilverResult


def build(
    *,
    silver: SilverResult,
    configuration: ConfigurationSnapshot,
    decisions: Sequence[GoldDecision],
    publication: GoldPublication,
    late_booking_window: timedelta,
) -> GoldResult:
    """Derive Gold from a Silver result, the household's configuration and decisions.

    Transactions are classified by the effective manual decisions, then
    transfer matching, then the configuration's rules. The result is
    bound to `publication`, which the caller supplies. A month's late bookings
    are settled by an export produced `late_booking_window` or more after it
    ends. A Silver transaction on an account the registry does not declare
    refuses the build, so no fact is published without its account. So does
    an account whose `closed_on` falls before its latest booked transaction,
    so no fact falls outside its account's managed period. A window that is
    negative, not a whole number of days or over 366 days raises
    `ValueError`.
    """
    _require_window(late_booking_window)
    _require_declared_accounts(silver, configuration.accounts)
    transactions = gold_transactions(silver.transactions)
    problems = (
        *_closing_problems(configuration.accounts, transactions),
        *_decision_problems(decisions, configuration),
    )
    if problems:
        raise ConfigurationError(problems)
    gold_accounts = tuple(
        _account(account, silver.account_evidence)
        for account in configuration.accounts.values()
    )
    classified = classify(transactions, silver.transactions, configuration, decisions)
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


def _require_window(window: timedelta) -> None:
    """Refuse a late-booking window that profiles could not have set.

    Profiles set it in whole days from 0 to `MAX_LATE_BOOKING_DAYS`, so anything
    else is refused here too, rather than truncated to the day
    `late_bookings_settled` compares or overflowing the date it is added to.
    """
    # `timedelta` keeps its days signed and its seconds and microseconds
    # positive, so a negative window always has negative days.
    whole = not window.seconds and not window.microseconds
    if not whole or not 0 <= window.days <= MAX_LATE_BOOKING_DAYS:
        message = (
            "late_booking_window must be a whole number of days from 0 to "
            f"{MAX_LATE_BOOKING_DAYS}, not {window}"
        )
        raise ValueError(message)


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


def _decision_problems(
    decisions: Sequence[GoldDecision], configuration: ConfigurationSnapshot
) -> tuple[str, ...]:
    """Name every decision the configuration alone shows cannot hold.

    `classification.md`, *Configuration errors*: a decision may not reference
    a missing category, including a deleted one, and a one-sided transfer's
    counterpart must be in the account registry.
    """
    return (
        *(
            f'{DECISION_LOG_FILE_NAME}: decision "{decision.decision_id}": '
            f"{problem}; record a decision that supersedes it; nothing was published"
            for decision in decisions
            if (problem := _decision_problem(decision, configuration)) is not None
        ),
        *_overlap_problems(decisions),
    )


def _overlap_problems(decisions: Sequence[GoldDecision]) -> tuple[str, ...]:
    """Name every transaction more than one decision targets.

    A transaction is targeted by at most one decision; a `pair` counts for
    both of its transactions (`classification.md`, *Manual Decisions*).
    """
    deciding: dict[str, list[str]] = {}
    for decision in decisions:
        for transaction_id in targets(decision):
            deciding.setdefault(transaction_id, []).append(decision.decision_id)
    return tuple(
        f'{DECISION_LOG_FILE_NAME}: transaction "{transaction_id}" is targeted by '
        f"{', '.join(decision_ids)}; supersede all but one; nothing was published"
        for transaction_id, decision_ids in deciding.items()
        if len(decision_ids) > 1
    )


def _decision_problem(
    decision: GoldDecision, configuration: ConfigurationSnapshot
) -> str | None:
    """Say what the configuration shows wrong with one decision, if anything."""
    match decision:
        case Classify(category_id=category_id) if (
            category_id not in configuration.taxonomy.categories
        ):
            return f'category "{category_id}" is not in the taxonomy'
        case OneSidedTransfer(counterpart_account_id=account_id) if (
            account_id not in configuration.accounts
        ):
            return f'counterpart account "{account_id}" is not in {ACCOUNTS_FILE_NAME}'
        case _:
            return None


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
