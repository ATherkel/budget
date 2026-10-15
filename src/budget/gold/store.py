# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

The store is a view of `gold.db` (ADR-014, `publications.md`). Every result
table is keyed by `publication_id` first, and every read through a repository
filters on its one publication, so no read adds two results together. Opening
the store never creates or changes the schema; `migrate_gold` owns that.

Money crosses this module only as `Decimal` (ADR-013). The conversion to
integer minor units of each account's currency happens here and nowhere else.
"""

import json
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Final, Literal, Self

from budget.gold.models import (
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.gold.recipe import Recipe
from budget.gold.repository import GoldRepository
from budget.gold.result import GoldRecords, GoldResult, refuse_bare_string
from budget.gold.storage import open_gold_connection
from budget.inputs.snapshot import ConfigurationSnapshot
from budget.profiles import Profile
from budget.silver.storage import (
    UnknownAccountCurrencyError,
    from_minor_units,
    to_minor_units,
)

type Rows = tuple[tuple[object, ...], ...]
type PointerCause = Literal["build", "undo", "migration"]


@dataclass(frozen=True)
class PointerMove:
    """One move of the current pointer (`publications.md`, *Pointer history*).

    `from_publication_id` is None for a store's first build. `moved_at` is
    when the move committed, in UTC.
    """

    moved_at: datetime
    from_publication_id: int | None
    to_publication_id: int
    cause: PointerCause


_SELECT_CURRENT_ID: Final = (
    "SELECT to_publication_id FROM pointer_moves ORDER BY move DESC LIMIT 1"
)
_SELECT_RETAINED: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) ORDER BY publication_id"
)
_SELECT_RETAINED_ONE: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) WHERE publication_id = ?"
)

_INSERT_PUBLICATION: Final = (
    "INSERT INTO publications (publication_id, kind, label, known_at, built_at,"
    " replayed_at, contract_version, fingerprint_scheme, result_fingerprint)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_MOVE: Final = (
    "INSERT INTO pointer_moves"
    " (moved_at, from_publication_id, to_publication_id, cause)"
    " VALUES (?, ?, ?, ?)"
)
_SELECT_MOVES: Final = "SELECT * FROM pointer_moves ORDER BY move"
_INSERT_RESULT: Final = "INSERT INTO results (publication_id) VALUES (?)"
_INSERT_ACCOUNTS: Final = (
    "INSERT INTO accounts (publication_id, account_id, display_name,"
    " account_type, ownership_scope, currency, closed_on, coverage_start,"
    " evidence_through) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_CATEGORIES: Final = (
    "INSERT INTO categories (publication_id, category_id, name, group_id,"
    " group_name, direction) VALUES (?, ?, ?, ?, ?, ?)"
)
_INSERT_TRANSACTIONS: Final = (
    "INSERT INTO transactions (publication_id, transaction_id, account_id,"
    " transaction_date, account_sequence, amount, description,"
    " transaction_type, transfer_group_id, balance_after, balance_check)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_ALLOCATIONS: Final = (
    "INSERT INTO category_allocations (publication_id, allocation_id,"
    " transaction_id, account_id, transaction_date, category_id, amount)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_BALANCES: Final = (
    "INSERT INTO monthly_balances (publication_id, account_id, month,"
    " opening_balance, closing_balance, coverage, late_bookings_settled)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)

# Each read names its publication, and `:account_ids` is a JSON array of the
# named accounts, or null for every account. Each query is written out whole,
# never composed, so no text but a bound parameter ever reaches SQLite.
_SELECT_ACCOUNTS: Final = (
    "SELECT * FROM accounts WHERE publication_id = :publication_id ORDER BY account_id"
)
_SELECT_CATEGORIES: Final = (
    "SELECT * FROM categories WHERE publication_id = :publication_id"
    " ORDER BY category_id"
)
_SELECT_TRANSACTIONS: Final = (
    "SELECT transactions.*, accounts.currency FROM transactions"
    " JOIN accounts USING (publication_id, account_id)"
    " WHERE transactions.publication_id = :publication_id"
    " AND transactions.transaction_date BETWEEN :start AND :end"
    " AND (:account_ids IS NULL OR transactions.account_id IN"
    " (SELECT value FROM json_each(:account_ids)))"
    " ORDER BY transactions.account_id, transactions.account_sequence"
)
_SELECT_ALLOCATIONS: Final = (
    "SELECT category_allocations.*, accounts.currency FROM category_allocations"
    " JOIN accounts USING (publication_id, account_id)"
    " WHERE category_allocations.publication_id = :publication_id"
    " AND category_allocations.transaction_date BETWEEN :start AND :end"
    " AND (:account_ids IS NULL OR category_allocations.account_id IN"
    " (SELECT value FROM json_each(:account_ids)))"
    " ORDER BY category_allocations.allocation_id"
)
_SELECT_BALANCES: Final = (
    "SELECT monthly_balances.*, accounts.currency FROM monthly_balances"
    " JOIN accounts USING (publication_id, account_id)"
    " WHERE monthly_balances.publication_id = :publication_id"
    " AND monthly_balances.month BETWEEN :start AND :end"
    " AND (:account_ids IS NULL OR monthly_balances.account_id IN"
    " (SELECT value FROM json_each(:account_ids)))"
    " ORDER BY monthly_balances.account_id, monthly_balances.month"
)


class GoldStore:
    """Publish to and read from the Gold store that one profile names."""

    def __init__(self, profile: Profile) -> None:
        """Open the migrated Gold store that one profile names."""
        self._connection = open_gold_connection(profile)

    def __enter__(self) -> Self:
        """Return the open store for a `with` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the store when the `with` block ends."""
        self.close()

    def close(self) -> None:
        """Release the store's connection."""
        self._connection.close()

    def current(self) -> GoldPublication | None:
        """Return the current publication, or None when it has no result.

        That is before the first publish, and after a Gold migration that
        could not convert the current result until the next build.
        """
        connection = self._connection
        pointer = connection.execute(_SELECT_CURRENT_ID).fetchone()
        if pointer is None:
            return None
        row = connection.execute(_SELECT_RETAINED_ONE, (pointer[0],)).fetchone()
        return None if row is None else _publication(row)

    def available(self) -> Sequence[GoldPublication]:
        """Return the publications whose results are retained, oldest first."""
        rows = self._connection.execute(_SELECT_RETAINED).fetchall()
        return tuple(_publication(row) for row in rows)

    def open(self, publication_id: int) -> GoldRepository:
        """Return a repository bound to one retained publication."""
        row = self._connection.execute(
            _SELECT_RETAINED_ONE, (publication_id,)
        ).fetchone()
        return StoredPublication(self._connection, _publication(row))

    def next_publication_id(self) -> int:
        """Return the id the next publication must carry."""
        raise NotImplementedError

    def pointer_history(self) -> Sequence[PointerMove]:
        """Return every move of the current pointer, oldest first."""
        rows = self._connection.execute(_SELECT_MOVES)
        return tuple(_move(row) for row in rows)

    def publish(
        self,
        result: GoldResult,
        recipe: Recipe,
        configuration: ConfigurationSnapshot,
    ) -> None:
        """Store `result` as a new publication and make it current."""
        del recipe, configuration
        publication = result.publication()
        encoded = _encode(publication.publication_id, result.records)
        with self._connection as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_INSERT_PUBLICATION, _publication_row(publication))
            connection.execute(_INSERT_RESULT, (publication.publication_id,))
            _write(connection, encoded)
            _move_pointer(connection, publication.publication_id, "build")


class StoredPublication:
    """One retained publication in `gold.db`, read as a `GoldRepository`.

    Every query filters on the bound `publication_id`, so a read never meets
    another publication's records.
    """

    __slots__ = ("_connection", "_publication")

    def __init__(
        self, connection: sqlite3.Connection, publication: GoldPublication
    ) -> None:
        """Bind the store's connection to one publication."""
        self._connection = connection
        self._publication = publication

    def publication(self) -> GoldPublication:
        """Return the publication every other method reads from."""
        return self._publication

    def accounts(self) -> Sequence[GoldAccount]:
        """Return every account inside the reporting boundary."""
        return tuple(map(_account, self._select(_SELECT_ACCOUNTS, {})))

    def categories(self) -> Sequence[GoldCategory]:
        """Return every assignable category."""
        return tuple(map(_category, self._select(_SELECT_CATEGORIES, {})))

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]:
        """Return the transactions dated from `start_date` through `end_date`."""
        rows = self._select_range(
            _SELECT_TRANSACTIONS,
            start_date.isoformat(),
            end_date.isoformat(),
            account_ids,
        )
        return tuple(map(_transaction, rows))

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]:
        """Return the allocations dated from `start_date` through `end_date`."""
        rows = self._select_range(
            _SELECT_ALLOCATIONS,
            start_date.isoformat(),
            end_date.isoformat(),
            account_ids,
        )
        return tuple(map(_allocation, rows))

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]:
        """Return the snapshots for `start_month` through `end_month`."""
        rows = self._select_range(
            _SELECT_BALANCES,
            _month_text(start_month),
            _month_text(end_month),
            account_ids,
        )
        return tuple(map(_snapshot, rows))

    def _select_range(
        self,
        query: str,
        start: str,
        end: str,
        account_ids: Collection[str] | None,
    ) -> sqlite3.Cursor:
        """Read one inclusive range, limited to the named accounts."""
        refuse_bare_string(account_ids)
        named = None if account_ids is None else json.dumps(list(account_ids))
        return self._select(query, {"start": start, "end": end, "account_ids": named})

    def _select(self, query: str, parameters: Mapping[str, object]) -> sqlite3.Cursor:
        """Run one read of the bound publication."""
        bound = {**parameters, "publication_id": self._publication.publication_id}
        return self._connection.execute(query, bound)


@dataclass(frozen=True)
class _Encoded:
    """One result as rows of plain SQLite values, table by table."""

    accounts: Rows
    categories: Rows
    transactions: Rows
    allocations: Rows
    balances: Rows


def _encode(publication_id: int, records: GoldRecords) -> _Encoded:
    """Encode every record before anything is written.

    Money its currency cannot hold exactly is refused here, so a refusal
    writes nothing.
    """
    currencies = {a.account_id: a.currency for a in records.accounts}
    return _Encoded(
        accounts=tuple(_account_row(publication_id, a) for a in records.accounts),
        categories=tuple(_category_row(publication_id, c) for c in records.categories),
        transactions=tuple(
            _transaction_row(publication_id, t, _currency(currencies, t.account_id))
            for t in records.transactions
        ),
        allocations=tuple(
            _allocation_row(publication_id, a, _currency(currencies, a.account_id))
            for a in records.category_allocations
        ),
        balances=tuple(
            _balance_row(publication_id, s, _currency(currencies, s.account_id))
            for s in records.monthly_balances
        ),
    )


def _move_pointer(
    connection: sqlite3.Connection, to_publication_id: int, cause: PointerCause
) -> None:
    """Append one move from the current publication to `to_publication_id`.

    The move is the last statement of its transaction, so `moved_at` is read
    just before the commit it records.
    """
    pointer = connection.execute(_SELECT_CURRENT_ID).fetchone()
    from_publication_id = None if pointer is None else pointer[0]
    moved_at = datetime.now(UTC).isoformat()
    connection.execute(
        _INSERT_MOVE, (moved_at, from_publication_id, to_publication_id, cause)
    )


def _move(row: sqlite3.Row) -> PointerMove:
    """Read one `pointer_moves` row."""
    return PointerMove(
        moved_at=datetime.fromisoformat(row["moved_at"]),
        from_publication_id=row["from_publication_id"],
        to_publication_id=row["to_publication_id"],
        cause=row["cause"],
    )


def _write(connection: sqlite3.Connection, encoded: _Encoded) -> None:
    """Insert every result table, parents before the rows that reference them."""
    connection.executemany(_INSERT_ACCOUNTS, encoded.accounts)
    connection.executemany(_INSERT_CATEGORIES, encoded.categories)
    connection.executemany(_INSERT_TRANSACTIONS, encoded.transactions)
    connection.executemany(_INSERT_ALLOCATIONS, encoded.allocations)
    connection.executemany(_INSERT_BALANCES, encoded.balances)


def _currency(currencies: Mapping[str, str], account_id: str) -> str:
    """Return the currency of an account the result publishes."""
    try:
        return currencies[account_id]
    except KeyError:
        raise UnknownAccountCurrencyError(account_id) from None


def _optional_minor(amount: Decimal | None, currency: str) -> int | None:
    """Write an amount that may be absent as minor units."""
    return None if amount is None else to_minor_units(amount, currency)


def _optional_decimal(minor: int | None, currency: str) -> Decimal | None:
    """Read minor units that may be absent back as a Decimal."""
    return None if minor is None else from_minor_units(minor, currency)


def _optional_iso(day: date | datetime | None) -> str | None:
    """Write a date or a moment that may be absent as ISO 8601 text."""
    return None if day is None else day.isoformat()


def _optional_date(text: str | None) -> date | None:
    """Read a stored date that may be absent."""
    return None if text is None else date.fromisoformat(text)


def _optional_time(text: str | None) -> datetime | None:
    """Read a stored moment that may be absent."""
    return None if text is None else datetime.fromisoformat(text)


def _month_text(month: ReportingMonth) -> str:
    """Write a month as `YYYY-MM`, which orders as text does."""
    return f"{month.year:04d}-{month.month:02d}"


def _month(text: str) -> ReportingMonth:
    """Read a `YYYY-MM` month."""
    year, month = text.split("-")
    return ReportingMonth(int(year), int(month))


def _publication_row(publication: GoldPublication) -> tuple[object, ...]:
    """Spell one publication's metadata as its `publications` row."""
    return (
        publication.publication_id,
        publication.kind,
        publication.label,
        publication.known_at.isoformat(),
        publication.built_at.isoformat(),
        _optional_iso(publication.replayed_at),
        publication.contract_version,
        publication.fingerprint_scheme,
        publication.result_fingerprint,
    )


def _publication(row: sqlite3.Row) -> GoldPublication:
    """Read one `publications` row back as the metadata it stores."""
    return GoldPublication(
        publication_id=row["publication_id"],
        kind=row["kind"],
        label=row["label"],
        known_at=datetime.fromisoformat(row["known_at"]),
        built_at=datetime.fromisoformat(row["built_at"]),
        replayed_at=_optional_time(row["replayed_at"]),
        contract_version=row["contract_version"],
        fingerprint_scheme=row["fingerprint_scheme"],
        result_fingerprint=row["result_fingerprint"],
    )


def _account_row(publication_id: int, account: GoldAccount) -> tuple[object, ...]:
    """Spell one account as its `accounts` row."""
    return (
        publication_id,
        account.account_id,
        account.display_name,
        account.account_type,
        account.ownership_scope,
        account.currency,
        _optional_iso(account.closed_on),
        _optional_iso(account.coverage_start),
        _optional_iso(account.evidence_through),
    )


def _account(row: sqlite3.Row) -> GoldAccount:
    """Read one `accounts` row."""
    return GoldAccount(
        account_id=row["account_id"],
        display_name=row["display_name"],
        account_type=row["account_type"],
        ownership_scope=row["ownership_scope"],
        currency=row["currency"],
        closed_on=_optional_date(row["closed_on"]),
        coverage_start=_optional_date(row["coverage_start"]),
        evidence_through=_optional_date(row["evidence_through"]),
    )


def _category_row(publication_id: int, category: GoldCategory) -> tuple[object, ...]:
    """Spell one category as its `categories` row."""
    return (
        publication_id,
        category.category_id,
        category.name,
        category.group_id,
        category.group_name,
        category.direction,
    )


def _category(row: sqlite3.Row) -> GoldCategory:
    """Read one `categories` row."""
    return GoldCategory(
        category_id=row["category_id"],
        name=row["name"],
        group_id=row["group_id"],
        group_name=row["group_name"],
        direction=row["direction"],
    )


def _transaction_row(
    publication_id: int, transaction: GoldTransaction, currency: str
) -> tuple[object, ...]:
    """Spell one transaction as its `transactions` row."""
    return (
        publication_id,
        transaction.transaction_id,
        transaction.account_id,
        transaction.transaction_date.isoformat(),
        transaction.account_sequence,
        to_minor_units(transaction.amount, currency),
        transaction.description,
        transaction.transaction_type,
        transaction.transfer_group_id,
        _optional_minor(transaction.balance_after, currency),
        transaction.balance_check,
    )


def _transaction(row: sqlite3.Row) -> GoldTransaction:
    """Read one `transactions` row, in its account's currency."""
    currency = row["currency"]
    return GoldTransaction(
        transaction_id=row["transaction_id"],
        account_id=row["account_id"],
        transaction_date=date.fromisoformat(row["transaction_date"]),
        account_sequence=row["account_sequence"],
        amount=from_minor_units(row["amount"], currency),
        description=row["description"],
        transaction_type=row["transaction_type"],
        transfer_group_id=row["transfer_group_id"],
        balance_after=_optional_decimal(row["balance_after"], currency),
        balance_check=row["balance_check"],
    )


def _allocation_row(
    publication_id: int, allocation: GoldCategoryAllocation, currency: str
) -> tuple[object, ...]:
    """Spell one allocation as its `category_allocations` row."""
    return (
        publication_id,
        allocation.allocation_id,
        allocation.transaction_id,
        allocation.account_id,
        allocation.transaction_date.isoformat(),
        allocation.category_id,
        to_minor_units(allocation.amount, currency),
    )


def _allocation(row: sqlite3.Row) -> GoldCategoryAllocation:
    """Read one `category_allocations` row, in its account's currency."""
    return GoldCategoryAllocation(
        allocation_id=row["allocation_id"],
        transaction_id=row["transaction_id"],
        account_id=row["account_id"],
        transaction_date=date.fromisoformat(row["transaction_date"]),
        category_id=row["category_id"],
        amount=from_minor_units(row["amount"], row["currency"]),
    )


def _balance_row(
    publication_id: int, snapshot: MonthlyBalanceSnapshot, currency: str
) -> tuple[object, ...]:
    """Spell one snapshot as its `monthly_balances` row."""
    return (
        publication_id,
        snapshot.account_id,
        _month_text(snapshot.month),
        _optional_minor(snapshot.opening_balance, currency),
        _optional_minor(snapshot.closing_balance, currency),
        snapshot.coverage,
        int(snapshot.late_bookings_settled),
    )


def _snapshot(row: sqlite3.Row) -> MonthlyBalanceSnapshot:
    """Read one `monthly_balances` row, in its account's currency."""
    currency = row["currency"]
    return MonthlyBalanceSnapshot(
        account_id=row["account_id"],
        month=_month(row["month"]),
        opening_balance=_optional_decimal(row["opening_balance"], currency),
        closing_balance=_optional_decimal(row["closing_balance"], currency),
        coverage=row["coverage"],
        late_bookings_settled=bool(row["late_bookings_settled"]),
    )
