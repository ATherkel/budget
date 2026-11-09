# Copyright 2026 Therkel
"""Find transaction handles in the current Gold publication, without writing."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.analytics import NothingPublishedError
from budget.gold.models import ReportingMonth
from budget.gold.store import GoldStore
from budget.inputs import load_accounts
from budget.profiles import Profile
from budget.silver import SilverStore


class FindInputError(ValueError):
    """The find command received an invalid option value."""


class InvalidMonthError(FindInputError):
    """A requested reporting month is invalid."""

    def __init__(self, month: str) -> None:
        """Name the invalid option value."""
        super().__init__(
            f'--month "{month}" is not YYYY-MM; expected a calendar month '
            "such as 2026-03"
        )


class UnknownAccountError(FindInputError):
    """The requested account is not declared in household configuration."""

    def __init__(self, account: str) -> None:
        """Name the undeclared account."""
        super().__init__(f'--account "{account}" is not declared in accounts.toml')


class PublicationSilverMismatchError(RuntimeError):
    """A Gold match cannot be resolved against the current Silver result."""

    def __init__(self) -> None:
        """Explain the state and name the command that realigns Gold."""
        super().__init__(
            "the current Gold publication has matching transactions that are "
            "not in current Silver; run `budget rebuild` to publish Gold from "
            "current Silver before using `budget find`"
        )


@dataclass(frozen=True)
class FoundTransaction:
    """One matching published transaction and its current category."""

    transaction_id: str
    handle: str
    account_id: str
    transaction_date: date
    amount: Decimal
    currency: str
    description: str
    category_id: str | None


@dataclass(frozen=True)
class FindResult:
    """Every matching transaction, ordered by date and then handle."""

    publication_id: int
    matches: tuple[FoundTransaction, ...]


def find_transactions(
    profile: Profile,
    text: str,
    *,
    month: ReportingMonth | None = None,
    account: str | None = None,
) -> FindResult:
    """Search current published descriptions without changing either store."""
    if account is not None and account not in load_accounts(profile):
        raise UnknownAccountError(account)
    start_date, end_date = date.min, date.max
    if month is not None:
        start_date = date(month.year, month.month, 1)
        end_date = date(
            month.year,
            month.month,
            monthrange(month.year, month.month)[1],
        )
    account_ids = None if account is None else {account}
    if not profile.gold_store.exists():
        raise NothingPublishedError
    with GoldStore(profile, read_only=True) as store:
        publication = store.current()
        if publication is None:
            raise NothingPublishedError
        gold = store.open(publication.publication_id)
        transactions = gold.transactions(
            start_date=start_date,
            end_date=end_date,
            account_ids=account_ids,
        )
        allocations = gold.category_allocations(
            start_date=date.min,
            end_date=date.max,
            account_ids=account_ids,
        )
        currencies = {
            account_record.account_id: account_record.currency
            for account_record in gold.accounts()
        }
    with SilverStore(profile, read_only=True) as silver:
        silver_ids = tuple(
            transaction.transaction_id for transaction in silver.read().transactions
        )
    search = text.casefold()
    matching_transactions = tuple(
        transaction
        for transaction in transactions
        if search in transaction.description.casefold()
    )
    silver_id_set = set(silver_ids)
    if any(
        transaction.transaction_id not in silver_id_set
        for transaction in matching_transactions
    ):
        raise PublicationSilverMismatchError
    category_ids = {
        allocation.transaction_id: allocation.category_id for allocation in allocations
    }
    matches = tuple(
        FoundTransaction(
            transaction_id=transaction.transaction_id,
            handle=transaction_handle(transaction.transaction_id, silver_ids),
            account_id=transaction.account_id,
            transaction_date=transaction.transaction_date,
            amount=transaction.amount,
            currency=currencies[transaction.account_id],
            description=transaction.description,
            category_id=category_ids.get(transaction.transaction_id),
        )
        for transaction in matching_transactions
    )
    return FindResult(
        publication.publication_id,
        tuple(
            sorted(matches, key=lambda match: (match.transaction_date, match.handle))
        ),
    )


def transaction_handle(transaction_id: str, transaction_ids: tuple[str, ...]) -> str:
    """Return the shortest resolving prefix, never shorter than eight characters."""
    minimum = min(8, len(transaction_id))
    for length in range(minimum, len(transaction_id) + 1):
        prefix = transaction_id[:length]
        if sum(each.startswith(prefix) for each in transaction_ids) == 1:
            return prefix
    return transaction_id
