# Copyright 2026 Therkel
"""Public Silver contracts, as `docs/architecture/silver-layer.md` defines them."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

type BookingStatus = Literal["booked", "pending", "cancelled"]


@dataclass(frozen=True)
class Transaction:
    """One booked transaction, after duplicates are collapsed."""

    transaction_id: str
    account_id: str
    transaction_date: date
    amount: Decimal
    currency: str
    description: str
    source_system: str
    balance: Decimal | None
    source_status: str
    booking_status: BookingStatus
    occurrence: int
    day_sequence: int
    identity_version: str
    bank_category: str | None
    bank_subcategory: str | None


@dataclass(frozen=True)
class TransactionEvidence:
    """Lineage: one source record that shows a transaction."""

    transaction_id: str
    payload_id: str
    record_ordinal: int
    import_run_id: str


@dataclass(frozen=True)
class UnbookedRecord:
    """A pending or cancelled source record, retained as provenance."""

    payload_id: str
    record_ordinal: int
    import_run_id: str
    account_id: str
    transaction_date: date
    amount: Decimal
    source_status: str
    booking_status: BookingStatus


@dataclass(frozen=True)
class BalanceObservation:
    """One export's bank-stated end-of-day balance for one date."""

    account_id: str
    balance_date: date
    end_of_day_balance: Decimal | None
    payload_id: str


@dataclass(frozen=True)
class AccountEvidence:
    """The last date an account's admitted exports are known to cover."""

    account_id: str
    evidence_through: date


@dataclass(frozen=True)
class ValidationError:
    """One problem with a payload, or with one of its source records."""

    payload_id: str
    record_ordinal: int | None
    code: str
    message: str


@dataclass(frozen=True)
class ImportRunResult:
    """Whether a stored import run was admitted, and why not."""

    import_run_id: str
    status: Literal["accepted", "quarantined"]
    covered_from: date | None
    covered_to: date
    errors: Sequence[ValidationError]
    review_item_ids: Sequence[str]


@dataclass(frozen=True)
class ReviewItem:
    """An ambiguity a person must decide."""

    review_item_id: str
    kind: Literal["export-disagreement", "dropped-transactions", "balance-break"]
    account_id: str
    date_from: date
    date_to: date
    payload_ids: Sequence[str]
    resolved_by: str | None
    # The dropped transaction, for `dropped-transactions`; issue #80, option A.
    transaction_id: str | None = None


@dataclass(frozen=True)
class SilverResult:
    """Everything one Silver build produces, each in a deterministic order."""

    transactions: Sequence[Transaction]
    transaction_evidence: Sequence[TransactionEvidence]
    unbooked_records: Sequence[UnbookedRecord]
    balance_observations: Sequence[BalanceObservation]
    account_evidence: Sequence[AccountEvidence]
    import_run_results: Sequence[ImportRunResult]
    review_items: Sequence[ReviewItem]
