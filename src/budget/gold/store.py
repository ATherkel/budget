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
import warnings
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
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
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.repository import GoldRepository, PublicationUnavailableError
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


class PublicationIdError(ValueError):
    """A result carries another id than the one the store hands out next."""

    def __init__(self, given: int, expected: int) -> None:
        """Name both ids, so the caller can see which one it built with."""
        super().__init__(
            f"publication {given} cannot be published: the next publication "
            f"in this store is {expected}"
        )


class StaleResultsWarning(UserWarning):
    """A publish committed, but deleting the results no longer retained failed.

    The publication is current all the same; the next publish deletes what
    this one left.
    """


_STALE_RESULTS_KEPT: Final = (
    "the publication is current, but results no longer retained could not be "
    "deleted; the next publish deletes them"
)


class PublicationKindError(ValueError):
    """Only a pipeline build is published, since it becomes current at once."""

    def __init__(self, kind: str) -> None:
        """Name the kind that cannot become current."""
        super().__init__(
            f"a publication of kind {kind!r} can never become current; only "
            "pipeline builds are published"
        )


class ConfigurationMismatchError(ValueError):
    """The configuration given is not the snapshot the recipe names."""

    def __init__(self, named: str, given: str) -> None:
        """Name both fingerprints."""
        super().__init__(
            f"the recipe names configuration {named}, but {given} was given"
        )


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


# Publications, and which of them keep their results.
_SELECT_RETAINED: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) ORDER BY publication_id"
)
_SELECT_RETAINED_ONE: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) WHERE publication_id = ?"
)
_SELECT_RESULT: Final = "SELECT 1 FROM results WHERE publication_id = ?"
_SELECT_NEXT_ID: Final = "SELECT coalesce(max(publication_id), 0) + 1 FROM publications"
_INSERT_PUBLICATION: Final = (
    "INSERT INTO publications (publication_id, kind, label, known_at, built_at,"
    " replayed_at, contract_version, fingerprint_scheme, result_fingerprint)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_RESULT: Final = "INSERT INTO results (publication_id) VALUES (?)"
# A result is retained while it is current, previous (the last move's
# origin) or labeled (`publications.md`, *Retention*).
_SELECT_STALE_IDS: Final = (
    "WITH last AS (SELECT from_publication_id, to_publication_id"
    " FROM pointer_moves ORDER BY move DESC LIMIT 1)"
    " SELECT publication_id FROM results"
    " WHERE publication_id NOT IN (SELECT to_publication_id FROM last)"
    " AND publication_id NOT IN"
    " (SELECT from_publication_id FROM last WHERE from_publication_id NOT NULL)"
    " AND publication_id NOT IN"
    " (SELECT publication_id FROM publications WHERE label NOT NULL)"
)
# Rows that reference others go first, and `results` last.
_DELETE_RESULT: Final = (
    "DELETE FROM monthly_balances WHERE publication_id = ?",
    "DELETE FROM category_allocations WHERE publication_id = ?",
    "DELETE FROM transactions WHERE publication_id = ?",
    "DELETE FROM categories WHERE publication_id = ?",
    "DELETE FROM accounts WHERE publication_id = ?",
    "DELETE FROM results WHERE publication_id = ?",
)

# The pointer history; the pointer is its last move.
_SELECT_CURRENT_ID: Final = (
    "SELECT to_publication_id FROM pointer_moves ORDER BY move DESC LIMIT 1"
)
_INSERT_MOVE: Final = (
    "INSERT INTO pointer_moves"
    " (moved_at, from_publication_id, to_publication_id, cause)"
    " VALUES (?, ?, ?, ?)"
)
_SELECT_MOVES: Final = "SELECT * FROM pointer_moves ORDER BY move"

# Recipes, kept forever, and each distinct configuration they name.
_INSERT_SNAPSHOT: Final = (
    "INSERT OR IGNORE INTO configuration_snapshots (fingerprint, content) VALUES (?, ?)"
)
_INSERT_RECIPE: Final = (
    "INSERT INTO recipes (publication_id, configuration_fingerprint,"
    " decision_log_position, decision_log_prefix_sha256, code_version,"
    " contract_version, silver_identity_version, python_version,"
    " sqlite_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_RECIPE_RUNS: Final = (
    "INSERT INTO recipe_import_runs (publication_id, import_run_id, payload_id)"
    " VALUES (?, ?, ?)"
)
_SELECT_RECIPE: Final = "SELECT * FROM recipes WHERE publication_id = ?"
_SELECT_RECIPE_RUNS: Final = (
    "SELECT import_run_id, payload_id FROM recipe_import_runs WHERE publication_id = ?"
)

# The result records of one publication.
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
        return _reading(self._connection, _current)

    def available(self) -> Sequence[GoldPublication]:
        """Return the publications whose results are retained, oldest first."""
        return _reading(
            self._connection,
            lambda connection: tuple(
                _publication(row) for row in connection.execute(_SELECT_RETAINED)
            ),
        )

    def open(self, publication_id: int) -> GoldRepository:
        """Return a repository bound to one retained publication.

        Raises `PublicationUnavailable` when the publication does not exist or
        its result is no longer retained.
        """
        publication = _reading(
            self._connection,
            lambda connection: _retained(connection, publication_id),
        )
        return StoredPublication(self._connection, publication)

    def next_publication_id(self) -> int:
        """Return the id the next publication must carry."""
        return _next_publication_id(self._connection)

    def recipe(self, publication_id: int) -> Recipe:
        """Return the recipe a publication was built from, retained or not."""
        return _reading(
            self._connection,
            lambda connection: _stored_recipe(connection, publication_id),
        )

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
        """Store `result` as a new publication and make it current.

        The result must be a `pipeline` build carrying `next_publication_id()`,
        and `configuration` must be the snapshot `recipe` names; each refusal
        writes nothing.
        The records are encoded before anything is written. One transaction
        then stores the publication, its recipe, its configuration if new,
        and its records, and appends a `build` move: that transaction is the
        commit point, and a failure before it leaves the previous publication
        current (`operations.md`, *Publishing a Gold build*). A later
        transaction deletes the results that are no longer retained; if that
        fails, `StaleResultsWarning` is issued and the publish still stands.
        """
        if configuration.fingerprint != recipe.configuration_fingerprint:
            raise ConfigurationMismatchError(
                recipe.configuration_fingerprint, configuration.fingerprint
            )
        publication = result.publication()
        if publication.kind != "pipeline":
            raise PublicationKindError(publication.kind)
        encoded = _encode(publication.publication_id, result.records)
        with self._connection as connection:
            connection.execute("BEGIN IMMEDIATE")
            expected = _next_publication_id(connection)
            if publication.publication_id != expected:
                raise PublicationIdError(publication.publication_id, expected)
            connection.execute(_INSERT_PUBLICATION, _publication_row(publication))
            connection.execute(_INSERT_RESULT, (publication.publication_id,))
            _write_recipe(connection, publication.publication_id, recipe, configuration)
            _write(connection, encoded)
            _move_pointer(connection, publication.publication_id, "build")
        try:
            _delete_stale_results(self._connection)
        except sqlite3.Error:
            # The publish has committed: it is current, and the next publish
            # deletes what is left, so the caller must not see a failure.
            warnings.warn(_STALE_RESULTS_KEPT, StaleResultsWarning, stacklevel=2)


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
        return self._select(_SELECT_ACCOUNTS, {}, _account)

    def categories(self) -> Sequence[GoldCategory]:
        """Return every assignable category."""
        return self._select(_SELECT_CATEGORIES, {}, _category)

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]:
        """Return the transactions dated from `start_date` through `end_date`."""
        return self._select_range(
            _SELECT_TRANSACTIONS,
            (start_date.isoformat(), end_date.isoformat()),
            account_ids,
            _transaction,
        )

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]:
        """Return the allocations dated from `start_date` through `end_date`."""
        return self._select_range(
            _SELECT_ALLOCATIONS,
            (start_date.isoformat(), end_date.isoformat()),
            account_ids,
            _allocation,
        )

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]:
        """Return the snapshots for `start_month` through `end_month`."""
        return self._select_range(
            _SELECT_BALANCES,
            (_month_text(start_month), _month_text(end_month)),
            account_ids,
            _snapshot,
        )

    def _select_range[T](
        self,
        query: str,
        bounds: tuple[str, str],
        account_ids: Collection[str] | None,
        decode: Callable[[sqlite3.Row], T],
    ) -> tuple[T, ...]:
        """Read one inclusive range, limited to the named accounts."""
        refuse_bare_string(account_ids)
        named = None if account_ids is None else json.dumps(list(account_ids))
        start, end = bounds
        parameters = {"start": start, "end": end, "account_ids": named}
        return self._select(query, parameters, decode)

    def _select[T](
        self,
        query: str,
        parameters: Mapping[str, object],
        decode: Callable[[sqlite3.Row], T],
    ) -> tuple[T, ...]:
        """Read and decode records of the bound publication, while it is retained.

        The check and the read share one read transaction, so a result deleted
        in between is never read as an empty one.
        """
        publication_id = self._publication.publication_id
        bound = {**parameters, "publication_id": publication_id}

        def read(connection: sqlite3.Connection) -> tuple[T, ...]:
            retained = connection.execute(_SELECT_RESULT, (publication_id,))
            if retained.fetchone() is None:
                raise PublicationUnavailableError(publication_id)
            return tuple(decode(row) for row in connection.execute(query, bound))

        return _reading(self._connection, read)


def _reading[T](
    connection: sqlite3.Connection, read: Callable[[sqlite3.Connection], T]
) -> T:
    """Run `read` inside one read transaction, so it sees one state of the store.

    A publish committed by another process lands wholly before or after it.
    """
    try:
        connection.execute("BEGIN")
        return read(connection)
    finally:
        connection.rollback()


def _current(connection: sqlite3.Connection) -> GoldPublication | None:
    """Return the publication the pointer names, while its result is retained."""
    pointer = connection.execute(_SELECT_CURRENT_ID).fetchone()
    if pointer is None:
        return None
    row = connection.execute(_SELECT_RETAINED_ONE, (pointer[0],)).fetchone()
    return None if row is None else _publication(row)


def _retained(connection: sqlite3.Connection, publication_id: int) -> GoldPublication:
    """Return a publication whose result is retained, or refuse it."""
    row = connection.execute(_SELECT_RETAINED_ONE, (publication_id,)).fetchone()
    if row is None:
        raise PublicationUnavailableError(publication_id)
    return _publication(row)


def _stored_recipe(connection: sqlite3.Connection, publication_id: int) -> Recipe:
    """Read one publication's recipe, or refuse a publication never published."""
    row = connection.execute(_SELECT_RECIPE, (publication_id,)).fetchone()
    if row is None:
        raise PublicationUnavailableError(publication_id)
    return _recipe(row, connection.execute(_SELECT_RECIPE_RUNS, (publication_id,)))


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


def _delete_stale_results(connection: sqlite3.Connection) -> None:
    """Delete, in one transaction, every result that is no longer retained.

    It runs after the publish it follows has committed, so a failure here
    never undoes a publish; the next publish deletes what this one left.
    The publications' metadata and recipes stay.
    """
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        stale = connection.execute(_SELECT_STALE_IDS).fetchall()
        for statement in _DELETE_RESULT:
            connection.executemany(statement, stale)


def _next_publication_id(connection: sqlite3.Connection) -> int:
    """Return one more than the highest id the store has ever published.

    A publication's metadata is never deleted, so no id is handed out twice.
    """
    row = connection.execute(_SELECT_NEXT_ID).fetchone()
    return int(row[0])


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


def _write_recipe(
    connection: sqlite3.Connection,
    publication_id: int,
    recipe: Recipe,
    configuration: ConfigurationSnapshot,
) -> None:
    """Store a publication's recipe, and its configuration if it is new."""
    connection.execute(
        _INSERT_SNAPSHOT, (configuration.fingerprint, configuration.canonical_text)
    )
    connection.execute(
        _INSERT_RECIPE,
        (
            publication_id,
            recipe.configuration_fingerprint,
            recipe.decision_log_position,
            recipe.decision_log_prefix_sha256,
            recipe.code_version,
            recipe.contract_version,
            recipe.silver_identity_version,
            recipe.python_version,
            recipe.sqlite_version,
        ),
    )
    connection.executemany(
        _INSERT_RECIPE_RUNS,
        sorted(
            (publication_id, run.import_run_id, run.payload_id)
            for run in recipe.import_runs
        ),
    )


def _recipe(row: sqlite3.Row, runs: Iterable[sqlite3.Row]) -> Recipe:
    """Read one `recipes` row and its import runs back as the recipe."""
    return Recipe(
        import_runs=frozenset(
            RecipeImportRun(run["import_run_id"], run["payload_id"]) for run in runs
        ),
        configuration_fingerprint=row["configuration_fingerprint"],
        decision_log_position=row["decision_log_position"],
        decision_log_prefix_sha256=row["decision_log_prefix_sha256"],
        code_version=row["code_version"],
        contract_version=row["contract_version"],
        silver_identity_version=row["silver_identity_version"],
        python_version=row["python_version"],
        sqlite_version=row["sqlite_version"],
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
