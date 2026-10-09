# Copyright 2026 Therkel
"""Gold contract 0.2 records, as `docs/architecture/gold-contract.md` defines them.

Every monetary value is a `Decimal` in its account's currency; no float enters
the contract.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

type AccountType = Literal["current", "savings"]
type OwnershipScope = Literal["household", "person"]
type CategoryDirection = Literal["income", "expense"]
type TransactionType = Literal[
    "income", "expense", "refund", "transfer", "adjustment", "unknown"
]
type BalanceCheck = Literal["opening", "consistent", "break", "missing_balance"]
type Coverage = Literal["complete", "partial", "no_data"]
type PublicationKind = Literal["pipeline", "as_known_at"]
type ClassificationSource = Literal["manual", "transfer_match", "rule", "unclassified"]
type TransferBasis = Literal[
    "same_day", "date_gap", "repeated_legs", "manual_pair", "one_sided"
]
type ClassificationReviewKind = Literal[
    "unclassified",
    "rule-conflict",
    "sign-mismatch",
    "ambiguous-transfer",
    "unmatched-transfer",
    "decision-not-applicable",
]


@dataclass(frozen=True, order=True)
class ReportingMonth:
    """A calendar month, `YYYY-MM`; months order chronologically."""

    year: int
    month: int

    @classmethod
    def of(cls, day: date) -> Self:
        """Return the month `day` falls in."""
        return cls(day.year, day.month)


@dataclass(frozen=True)
class GoldAccount:
    """One account inside the reporting boundary (Type 1)."""

    account_id: str
    display_name: str
    account_type: AccountType
    ownership_scope: OwnershipScope
    currency: str
    closed_on: date | None
    coverage_start: date | None
    evidence_through: date | None


@dataclass(frozen=True)
class GoldCategory:
    """One assignable category, with its group flattened onto it (Type 1)."""

    category_id: str
    name: str
    group_id: str
    group_name: str
    direction: CategoryDirection


@dataclass(frozen=True)
class GoldTransaction:
    """One booked transaction on one account; it carries no category."""

    transaction_id: str
    account_id: str
    transaction_date: date
    account_sequence: int
    amount: Decimal
    description: str
    transaction_type: TransactionType
    transfer_group_id: str | None
    balance_after: Decimal | None
    balance_check: BalanceCheck


@dataclass(frozen=True)
class GoldCategoryAllocation:
    """One category allocation of one booked transaction (ADR-008)."""

    allocation_id: str
    transaction_id: str
    account_id: str
    transaction_date: date
    category_id: str
    amount: Decimal


@dataclass(frozen=True)
class MonthlyBalanceSnapshot:
    """One account for one reporting month of its managed period."""

    account_id: str
    month: ReportingMonth
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    coverage: Coverage
    late_bookings_settled: bool


@dataclass(frozen=True)
class GoldPublication:
    """Metadata of one publication; none of it enters the result fingerprint."""

    publication_id: int
    kind: PublicationKind
    label: str | None
    known_at: datetime
    built_at: datetime
    replayed_at: datetime | None
    contract_version: str
    fingerprint_scheme: str
    result_fingerprint: str


@dataclass(frozen=True)
class TransferEvidence:
    """The named evidence basis for a transfer; not a score."""

    basis: TransferBasis
    counterpart_account_id: str
    counterpart_transaction_id: str | None
    date_gap_days: int | None
    claim_rule_ids: Sequence[str]


@dataclass(frozen=True)
class GoldTransactionLineage:
    """Lineage: where one Gold transaction and its classification came from."""

    transaction_id: str
    silver_transaction_id: str
    classification_source: ClassificationSource
    rule_ids: Sequence[str]
    decision_id: str | None
    classification_version: str
    transfer_evidence: TransferEvidence | None
    review_item_ids: Sequence[str]


@dataclass(frozen=True)
class ClassificationReviewItem:
    """A classification question a person must decide."""

    review_item_id: str
    kind: ClassificationReviewKind
    transaction_ids: Sequence[str]
    rule_ids: Sequence[str]
    decision_id: str | None
    reason: str | None
