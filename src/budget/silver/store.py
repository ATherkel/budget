# Copyright 2026 Therkel
"""Reading and replacing the one persisted SilverResult of a profile.

The store is a view of `silver.db` (ADR-015). `replace` writes one whole
`SilverResult` in one transaction, so a reader sees either the previous result
or the new one and never a mixture. `read` takes one SQLite snapshot for the
whole result, so concurrent tables cannot disagree. Opening never creates or
changes the schema; `migrate_silver` owns that.

Money crosses this module only as `Decimal` (ADR-013). The conversion to
integer minor units happens here, in `budget.silver.storage`, and nowhere else.
"""

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import TracebackType
from typing import Final, Self

from budget.profiles import Profile
from budget.silver.currencies import minor_unit_places
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
    ValidationError,
)
from budget.silver.storage import (
    CurrencySnapshotMismatchError,
    UnknownAccountCurrencyError,
    from_minor_units,
    open_silver_connection,
    to_minor_units,
)

type Rows = tuple[tuple[object, ...], ...]

# Child tables are cleared before the rows they point at, so no cascading
# delete can touch a row this transaction has not yet replaced.
_CLEAR: Final = (
    "DELETE FROM review_item_payloads",
    "DELETE FROM review_items",
    "DELETE FROM import_run_result_review_items",
    "DELETE FROM validation_errors",
    "DELETE FROM import_run_results",
    "DELETE FROM account_evidence",
    "DELETE FROM balance_observations",
    "DELETE FROM unbooked_records",
    "DELETE FROM transaction_evidence",
    "DELETE FROM transactions",
    "DELETE FROM account_currencies",
)

_INSERT_CURRENCIES: Final = (
    "INSERT INTO account_currencies (account_id, currency) VALUES (?, ?)"
)
_INSERT_TRANSACTIONS: Final = (
    "INSERT INTO transactions (ordinal, transaction_id, account_id,"
    " transaction_date, amount, currency, description, source_system, balance,"
    " source_status, booking_status, occurrence, day_sequence,"
    " identity_version, bank_category, bank_subcategory)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_EVIDENCE: Final = (
    "INSERT INTO transaction_evidence"
    " (ordinal, transaction_id, payload_id, record_ordinal, import_run_id)"
    " VALUES (?, ?, ?, ?, ?)"
)
_INSERT_UNBOOKED: Final = (
    "INSERT INTO unbooked_records (ordinal, payload_id, record_ordinal,"
    " import_run_id, account_id, transaction_date, amount, source_status,"
    " booking_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_OBSERVATIONS: Final = (
    "INSERT INTO balance_observations"
    " (ordinal, account_id, balance_date, end_of_day_balance, payload_id)"
    " VALUES (?, ?, ?, ?, ?)"
)
_INSERT_RANGES: Final = (
    "INSERT INTO account_evidence"
    " (ordinal, account_id, covers_from, covers_through) VALUES (?, ?, ?, ?)"
)
_INSERT_RESULTS: Final = (
    "INSERT INTO import_run_results"
    " (ordinal, import_run_id, status, covered_from, covered_to)"
    " VALUES (?, ?, ?, ?, ?)"
)
_INSERT_ERRORS: Final = (
    "INSERT INTO validation_errors (import_run_ordinal, position, payload_id,"
    " record_ordinal, code, message) VALUES (?, ?, ?, ?, ?, ?)"
)
_INSERT_REVIEW_IDS: Final = (
    "INSERT INTO import_run_result_review_items"
    " (import_run_ordinal, position, review_item_id) VALUES (?, ?, ?)"
)
_INSERT_ITEMS: Final = (
    "INSERT INTO review_items (ordinal, review_item_id, kind, account_id,"
    " date_from, date_to, resolved_by, transaction_id)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_INSERT_PAYLOADS: Final = (
    "INSERT INTO review_item_payloads (review_item_ordinal, position, payload_id)"
    " VALUES (?, ?, ?)"
)

_SELECT_CURRENCIES: Final = (
    "SELECT account_id, currency FROM account_currencies ORDER BY account_id"
)
_SELECT_TRANSACTIONS: Final = "SELECT * FROM transactions ORDER BY ordinal"
_SELECT_EVIDENCE: Final = "SELECT * FROM transaction_evidence ORDER BY ordinal"
_SELECT_UNBOOKED: Final = "SELECT * FROM unbooked_records ORDER BY ordinal"
_SELECT_OBSERVATIONS: Final = "SELECT * FROM balance_observations ORDER BY ordinal"
_SELECT_RANGES: Final = "SELECT * FROM account_evidence ORDER BY ordinal"
_SELECT_RESULTS: Final = "SELECT * FROM import_run_results ORDER BY ordinal"
_SELECT_ITEMS: Final = "SELECT * FROM review_items ORDER BY ordinal"


@dataclass(frozen=True)
class _Encoded:
    """One SilverResult as rows of plain SQLite values, table by table."""

    account_currencies: Rows
    transactions: Rows
    transaction_evidence: Rows
    unbooked_records: Rows
    balance_observations: Rows
    account_evidence: Rows
    import_run_results: Rows
    validation_errors: Rows
    import_run_result_review_items: Rows
    review_items: Rows
    review_item_payloads: Rows


class SilverStore:
    """Read and replace the Silver store that one profile names."""

    def __init__(self, profile: Profile, *, read_only: bool = False) -> None:
        """Open the migrated Silver store that one profile names.

        With `read_only`, the connection cannot write the file, so a command
        that only reads the stored result takes no write lock on it.
        """
        self._connection = open_silver_connection(profile, read_only=read_only)

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
        """Release resources when the store is closed."""
        self._connection.close()

    def replace(self, result: SilverResult, *, currencies: Mapping[str, str]) -> None:
        """Replace every stored row with one complete `SilverResult`.

        The rows are encoded first, so an amount the store cannot hold exactly
        is refused before anything is written, and the write itself is one
        transaction: a failure anywhere in it leaves the previous result
        readable, down to the last row.
        """
        encoded = _encode(result, currencies)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _CLEAR:
                self._connection.execute(statement)
            _write(self._connection, encoded)

    def read(self) -> SilverResult:
        """Return the complete stored result, with Decimal money.

        Every table is read inside one transaction, so a concurrent replacement
        cannot make two of them disagree about which build they describe.
        """
        connection = self._connection
        try:
            connection.execute("BEGIN")
            result = _decode(connection)
        finally:
            connection.rollback()
        return result


def _write(connection: sqlite3.Connection, encoded: _Encoded) -> None:
    """Insert every table, parents before the rows that reference them."""
    connection.executemany(_INSERT_CURRENCIES, encoded.account_currencies)
    connection.executemany(_INSERT_TRANSACTIONS, encoded.transactions)
    connection.executemany(_INSERT_EVIDENCE, encoded.transaction_evidence)
    connection.executemany(_INSERT_UNBOOKED, encoded.unbooked_records)
    connection.executemany(_INSERT_OBSERVATIONS, encoded.balance_observations)
    connection.executemany(_INSERT_RANGES, encoded.account_evidence)
    connection.executemany(_INSERT_RESULTS, encoded.import_run_results)
    connection.executemany(_INSERT_ERRORS, encoded.validation_errors)
    connection.executemany(_INSERT_REVIEW_IDS, encoded.import_run_result_review_items)
    connection.executemany(_INSERT_ITEMS, encoded.review_items)
    connection.executemany(_INSERT_PAYLOADS, encoded.review_item_payloads)


def _encode(result: SilverResult, currencies: Mapping[str, str]) -> _Encoded:
    """Turn one result into the rows every table will hold."""
    return _Encoded(
        account_currencies=tuple(sorted(currencies.items())),
        transactions=_encode_transactions(result.transactions, currencies),
        transaction_evidence=_encode_evidence(result.transaction_evidence),
        unbooked_records=_encode_unbooked(result.unbooked_records, currencies),
        balance_observations=_encode_observations(
            result.balance_observations, currencies
        ),
        account_evidence=_encode_ranges(result.account_evidence),
        import_run_results=_encode_results(result.import_run_results),
        validation_errors=_encode_errors(result.import_run_results),
        import_run_result_review_items=_encode_review_ids(result.import_run_results),
        review_items=_encode_items(result.review_items),
        review_item_payloads=_encode_payloads(result.review_items),
    )


def _currency_for(currencies: Mapping[str, str], account_id: str) -> str:
    """Return the snapshot's currency for one account, refusing a gap."""
    try:
        return currencies[account_id]
    except KeyError:
        raise UnknownAccountCurrencyError(account_id) from None


def _configured_currency(
    currencies: Mapping[str, str], account_id: str, row_currency: str
) -> str:
    """Return an account's configured currency, refusing a row that disagrees.

    The configured currency must be one the ISO 4217 table knows, and it must
    be the currency the row itself was written in.
    """
    currency = _currency_for(currencies, account_id)
    minor_unit_places(currency)
    if currency != row_currency:
        raise CurrencySnapshotMismatchError(account_id, row_currency, currency)
    return currency


def _optional_minor(amount: Decimal | None, currency: str) -> int | None:
    """Write an optional amount, preserving a null balance as a null."""
    return None if amount is None else to_minor_units(amount, currency)


def _encode_transactions(
    items: Sequence[Transaction], currencies: Mapping[str, str]
) -> Rows:
    return tuple(
        _transaction_row(ordinal, item, currencies)
        for ordinal, item in enumerate(items, start=1)
    )


def _transaction_row(
    ordinal: int, item: Transaction, currencies: Mapping[str, str]
) -> tuple[object, ...]:
    """Encode one transaction under its account's configured currency."""
    currency = _configured_currency(currencies, item.account_id, item.currency)
    return (
        ordinal,
        item.transaction_id,
        item.account_id,
        item.transaction_date.isoformat(),
        to_minor_units(item.amount, currency),
        currency,
        item.description,
        item.source_system,
        _optional_minor(item.balance, currency),
        item.source_status,
        item.booking_status,
        item.occurrence,
        item.day_sequence,
        item.identity_version,
        item.bank_category,
        item.bank_subcategory,
    )


def _encode_evidence(items: Sequence[TransactionEvidence]) -> Rows:
    return tuple(
        (
            ordinal,
            item.transaction_id,
            item.payload_id,
            item.record_ordinal,
            item.import_run_id,
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_unbooked(
    items: Sequence[UnbookedRecord], currencies: Mapping[str, str]
) -> Rows:
    return tuple(
        (
            ordinal,
            item.payload_id,
            item.record_ordinal,
            item.import_run_id,
            item.account_id,
            item.transaction_date.isoformat(),
            to_minor_units(item.amount, _currency_for(currencies, item.account_id)),
            item.source_status,
            item.booking_status,
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_observations(
    items: Sequence[BalanceObservation], currencies: Mapping[str, str]
) -> Rows:
    return tuple(
        (
            ordinal,
            item.account_id,
            item.balance_date.isoformat(),
            _optional_minor(
                item.end_of_day_balance, _currency_for(currencies, item.account_id)
            ),
            item.payload_id,
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_ranges(items: Sequence[AccountEvidence]) -> Rows:
    return tuple(
        (
            ordinal,
            item.account_id,
            item.covers_from.isoformat(),
            item.covers_through.isoformat(),
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_results(items: Sequence[ImportRunResult]) -> Rows:
    return tuple(
        (
            ordinal,
            item.import_run_id,
            item.status,
            item.covered_from.isoformat(),
            item.covered_to.isoformat(),
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_errors(items: Sequence[ImportRunResult]) -> Rows:
    return tuple(
        (
            run_ordinal,
            position,
            error.payload_id,
            error.record_ordinal,
            error.code,
            error.message,
        )
        for run_ordinal, item in enumerate(items, start=1)
        for position, error in enumerate(item.errors, start=1)
    )


def _encode_review_ids(items: Sequence[ImportRunResult]) -> Rows:
    return tuple(
        (run_ordinal, position, review_item_id)
        for run_ordinal, item in enumerate(items, start=1)
        for position, review_item_id in enumerate(item.review_item_ids, start=1)
    )


def _encode_items(items: Sequence[ReviewItem]) -> Rows:
    return tuple(
        (
            ordinal,
            item.review_item_id,
            item.kind,
            item.account_id,
            item.date_from.isoformat(),
            item.date_to.isoformat(),
            item.resolved_by,
            item.transaction_id,
        )
        for ordinal, item in enumerate(items, start=1)
    )


def _encode_payloads(items: Sequence[ReviewItem]) -> Rows:
    return tuple(
        (item_ordinal, position, payload_id)
        for item_ordinal, item in enumerate(items, start=1)
        for position, payload_id in enumerate(item.payload_ids, start=1)
    )


def _decode(connection: sqlite3.Connection) -> SilverResult:
    """Read one complete result from one snapshot."""
    currencies: dict[str, str] = {
        row["account_id"]: row["currency"]
        for row in connection.execute(_SELECT_CURRENCIES)
    }
    errors = _stored_errors(connection)
    review_ids = _stored_review_ids(connection)
    payloads = _stored_payloads(connection)
    return SilverResult(
        transactions=tuple(
            _transaction(row) for row in connection.execute(_SELECT_TRANSACTIONS)
        ),
        transaction_evidence=tuple(
            _evidence(row) for row in connection.execute(_SELECT_EVIDENCE)
        ),
        unbooked_records=tuple(
            _unbooked(row, currencies) for row in connection.execute(_SELECT_UNBOOKED)
        ),
        balance_observations=tuple(
            _observation(row, currencies)
            for row in connection.execute(_SELECT_OBSERVATIONS)
        ),
        account_evidence=tuple(
            _range(row) for row in connection.execute(_SELECT_RANGES)
        ),
        import_run_results=tuple(
            _result(row, errors, review_ids)
            for row in connection.execute(_SELECT_RESULTS)
        ),
        review_items=tuple(
            _item(row, payloads) for row in connection.execute(_SELECT_ITEMS)
        ),
    )


def _transaction(row: sqlite3.Row) -> Transaction:
    """Rebuild one canonical transaction from its stored row."""
    currency = row["currency"]
    return Transaction(
        transaction_id=row["transaction_id"],
        account_id=row["account_id"],
        transaction_date=date.fromisoformat(row["transaction_date"]),
        amount=from_minor_units(row["amount"], currency),
        currency=currency,
        description=row["description"],
        source_system=row["source_system"],
        balance=_stored_minor(row["balance"], currency),
        source_status=row["source_status"],
        booking_status=row["booking_status"],
        occurrence=row["occurrence"],
        day_sequence=row["day_sequence"],
        identity_version=row["identity_version"],
        bank_category=row["bank_category"],
        bank_subcategory=row["bank_subcategory"],
    )


def _evidence(row: sqlite3.Row) -> TransactionEvidence:
    return TransactionEvidence(
        transaction_id=row["transaction_id"],
        payload_id=row["payload_id"],
        record_ordinal=row["record_ordinal"],
        import_run_id=row["import_run_id"],
    )


def _unbooked(row: sqlite3.Row, currencies: Mapping[str, str]) -> UnbookedRecord:
    account_id = row["account_id"]
    return UnbookedRecord(
        payload_id=row["payload_id"],
        record_ordinal=row["record_ordinal"],
        import_run_id=row["import_run_id"],
        account_id=account_id,
        transaction_date=date.fromisoformat(row["transaction_date"]),
        amount=from_minor_units(row["amount"], currencies[account_id]),
        source_status=row["source_status"],
        booking_status=row["booking_status"],
    )


def _observation(row: sqlite3.Row, currencies: Mapping[str, str]) -> BalanceObservation:
    account_id = row["account_id"]
    currency = currencies[account_id]
    return BalanceObservation(
        account_id=account_id,
        balance_date=date.fromisoformat(row["balance_date"]),
        end_of_day_balance=_stored_minor(row["end_of_day_balance"], currency),
        payload_id=row["payload_id"],
    )


def _range(row: sqlite3.Row) -> AccountEvidence:
    return AccountEvidence(
        account_id=row["account_id"],
        covers_from=date.fromisoformat(row["covers_from"]),
        covers_through=date.fromisoformat(row["covers_through"]),
    )


def _result(
    row: sqlite3.Row,
    errors: Mapping[int, tuple[ValidationError, ...]],
    review_ids: Mapping[int, tuple[str, ...]],
) -> ImportRunResult:
    ordinal = row["ordinal"]
    return ImportRunResult(
        import_run_id=row["import_run_id"],
        status=row["status"],
        covered_from=date.fromisoformat(row["covered_from"]),
        covered_to=date.fromisoformat(row["covered_to"]),
        errors=errors.get(ordinal, ()),
        review_item_ids=review_ids.get(ordinal, ()),
    )


def _item(row: sqlite3.Row, payloads: Mapping[int, tuple[str, ...]]) -> ReviewItem:
    return ReviewItem(
        review_item_id=row["review_item_id"],
        kind=row["kind"],
        account_id=row["account_id"],
        date_from=date.fromisoformat(row["date_from"]),
        date_to=date.fromisoformat(row["date_to"]),
        payload_ids=payloads.get(row["ordinal"], ()),
        resolved_by=row["resolved_by"],
        transaction_id=row["transaction_id"],
    )


def _stored_minor(value: int | None, currency: str) -> Decimal | None:
    """Read an optional minor-unit count back, keeping a null as a null."""
    return None if value is None else from_minor_units(value, currency)


def _stored_errors(
    connection: sqlite3.Connection,
) -> dict[int, tuple[ValidationError, ...]]:
    """Group each run's validation errors, in their stored order."""
    found: dict[int, list[ValidationError]] = {}
    rows = connection.execute(
        "SELECT * FROM validation_errors ORDER BY import_run_ordinal, position"
    )
    for row in rows:
        found.setdefault(row["import_run_ordinal"], []).append(
            ValidationError(
                payload_id=row["payload_id"],
                record_ordinal=row["record_ordinal"],
                code=row["code"],
                message=row["message"],
            )
        )
    return {ordinal: tuple(errors) for ordinal, errors in found.items()}


def _stored_review_ids(connection: sqlite3.Connection) -> dict[int, tuple[str, ...]]:
    """Group each run's review-item identifiers, in their stored order."""
    found: dict[int, list[str]] = {}
    rows = connection.execute(
        "SELECT * FROM import_run_result_review_items"
        " ORDER BY import_run_ordinal, position"
    )
    for row in rows:
        found.setdefault(row["import_run_ordinal"], []).append(row["review_item_id"])
    return {ordinal: tuple(ids) for ordinal, ids in found.items()}


def _stored_payloads(connection: sqlite3.Connection) -> dict[int, tuple[str, ...]]:
    """Group each review item's payloads, in their stored order."""
    found: dict[int, list[str]] = {}
    rows = connection.execute(
        "SELECT * FROM review_item_payloads ORDER BY review_item_ordinal, position"
    )
    for row in rows:
        found.setdefault(row["review_item_ordinal"], []).append(row["payload_id"])
    return {ordinal: tuple(payloads) for ordinal, payloads in found.items()}
