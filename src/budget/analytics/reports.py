# Copyright 2026 Therkel
"""Report contract 0.2 types, as `docs/architecture/report-contract.md` defines them.

Every monetary value is a `Decimal` in the report's currency, and every ratio
an unrounded `Decimal`; no float enters a report.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from budget.gold import (
    AccountType,
    Classification,
    Coverage,
    PublicationKind,
    ReportingMonth,
    TransactionType,
)

type AccountMonthStatus = Literal["partial", "no_data", "outside_history"]
type ProvisionalReason = Literal["current_month", "late_bookings_unsettled"]
type SelectionRule = Literal[
    "no_accounts",
    "unknown_account",
    "mixed_currencies",
    "month_out_of_range",
    "unknown_category",
]


@dataclass(frozen=True)
class ReportPublication:
    """The publication a report read, and whether it was current then."""

    publication_id: int
    kind: PublicationKind
    label: str | None
    known_at: datetime
    is_current: bool


@dataclass(frozen=True)
class ReportContext:
    """The one selection every report on a page shares."""

    publication_id: int
    account_ids: frozenset[str]
    month: ReportingMonth
    reference_date: date


@dataclass(frozen=True)
class SelectableAccount:
    """One account a page may select."""

    account_id: str
    display_name: str
    account_type: AccountType
    owner_id: str
    currency: str


@dataclass(frozen=True)
class SelectionOptions:
    """What a page may select within one publication on one reference date."""

    publication: ReportPublication
    accounts: tuple[SelectableAccount, ...]
    first_month: ReportingMonth
    last_month: ReportingMonth
    owners: tuple["SelectableOwner", ...] = ()


@dataclass(frozen=True)
class SelectableOwner:
    """One owner a page may select by; `SelectionOptions.owners` is in display order."""

    owner_id: str
    display_name: str


@dataclass(frozen=True)
class CategorySpending:
    """One expense Category's net spending in the month, summed over allocations."""

    category_id: str
    name: str
    group_id: str
    group_name: str
    spending: Decimal


@dataclass(frozen=True)
class MoneyInOut:
    """Money in and money out, never netted, and how many transactions."""

    money_in: Decimal
    money_out: Decimal
    count: int


type SummaryGroup = Literal["income", "expenses", "transfers", "unclassified"]


@dataclass(frozen=True)
class RowClassification:
    """Why a row sits where it does: what decided it, and its Category and group."""

    classified_by: Classification
    category_name: str | None = None
    group_name: str | None = None


UNCLASSIFIED_ROW = RowClassification(Classification("unclassified"))


@dataclass(frozen=True)
class MovementRow:
    """One transaction behind a summary group: its bank amount and signed effect."""

    transaction_date: date
    description: str
    account_id: str
    account_display_name: str
    amount: Decimal
    contribution: Decimal
    classification: RowClassification = UNCLASSIFIED_ROW


@dataclass(frozen=True)
class MovementGroup:
    """One summary group's rows, their summed contribution and money in and out."""

    group: SummaryGroup
    rows: tuple[MovementRow, ...]
    total: Decimal
    flows: MoneyInOut


@dataclass(frozen=True)
class AccountMonth:
    """One selected account in one month."""

    account_id: str
    display_name: str
    month: ReportingMonth


@dataclass(frozen=True)
class AccountMonthCoverage:
    """One selected account-month that is not `complete`."""

    account_id: str
    display_name: str
    month: ReportingMonth
    status: AccountMonthStatus


@dataclass(frozen=True)
class ReportCoverage:
    """Coverage of every figure in a report, naming each incomplete account-month."""

    status: Coverage
    account_months: tuple[AccountMonthCoverage, ...]


@dataclass(frozen=True)
class Provisional:
    """Why a month's figures may still change."""

    reasons: frozenset[ProvisionalReason]
    unsettled: tuple[AccountMonth, ...]


@dataclass(frozen=True)
class MonthlyOverview:
    """The household's month: income, expenses, money left and where it went."""

    context: ReportContext
    publication: ReportPublication
    currency: str
    income: Decimal | None
    expenses: Decimal | None
    net_cash_flow: Decimal | None
    savings_rate: Decimal | None
    categories: tuple[CategorySpending, ...]
    unclassified: MoneyInOut | None
    adjustments: MoneyInOut | None
    movements: tuple[MovementGroup, ...] | None
    coverage: ReportCoverage
    provisional: Provisional | None


type DetailKind = Literal["category", "group"]
type DetailScope = Literal["month", "year_to_date"]
type TransferPairing = Literal["paired", "one_sided"]


@dataclass(frozen=True)
class DetailSubject:
    """The expense Category, or the group of them, a detail report explains."""

    kind: DetailKind
    id: str


@dataclass(frozen=True)
class SpendingDetailRow:
    """One allocation of the subject: what was bought, where, and its spending."""

    transaction_date: date
    description: str
    account_id: str
    account_display_name: str
    category_id: str
    category_name: str
    spending: Decimal


@dataclass(frozen=True)
class SpendingDetail:
    """The entries behind one Category's or group's overview figure."""

    context: ReportContext
    subject: DetailSubject
    scope: DetailScope
    publication: ReportPublication
    currency: str
    name: str
    group_id: str
    group_name: str
    first_month: ReportingMonth
    last_month: ReportingMonth
    spending: Decimal | None
    rows: tuple[SpendingDetailRow, ...]
    coverage: ReportCoverage
    provisional: Provisional | None


@dataclass(frozen=True)
class BankBalanceObservation:
    """The bank-stated balance after one dated transaction."""

    transaction_date: date
    balance_after: Decimal | None


@dataclass(frozen=True)
class MonthlyBalanceObservation:
    """One account-month's published snapshot, separate from dated observations."""

    opening_balance: Decimal | None
    closing_balance: Decimal | None
    coverage: Coverage
    late_bookings_settled: bool


@dataclass(frozen=True)
class AccountActivitySnapshot:
    """One selected account's dated observations and published monthly snapshot."""

    account_id: str
    display_name: str
    dated_balance: BankBalanceObservation | None
    earlier_observation: BankBalanceObservation | None
    monthly_snapshot: MonthlyBalanceObservation | None
    evidence_through: date | None
    coverage: Coverage | Literal["outside_history"]
    money_in_out: MoneyInOut | None


@dataclass(frozen=True)
class ActivityRow:
    """One selected transaction, preserving its published type and public pairing."""

    transaction_date: date
    description: str
    account_id: str
    account_display_name: str
    amount: Decimal
    transaction_type: TransactionType
    transfer_pairing: TransferPairing | None
    counterpart_account_id: str | None
    counterpart_account_display_name: str | None
    counterpart_transaction_date: date | None


@dataclass(frozen=True)
class AccountActivity:
    """Dated balances and transaction activity for the selected account-month."""

    context: ReportContext
    publication: ReportPublication
    currency: str
    accounts: tuple[AccountActivitySnapshot, ...]
    coverage: ReportCoverage
    provisional: Provisional | None
    transactions: tuple[ActivityRow, ...] = ()


@dataclass(frozen=True)
class AccountEvidence:
    """One selected account's public Evidence through value."""

    account_id: str
    display_name: str
    evidence_through: date | None


@dataclass(frozen=True)
class TransferSummary:
    """The selected Transfer legs' signs, count, and public pairing state."""

    money_in: Decimal
    money_out: Decimal
    count: int
    paired_count: int
    one_sided_count: int


@dataclass(frozen=True)
class Reconciliation:
    """One account-month's analytics-supplied balance and activity components."""

    account_id: str
    display_name: str
    month: ReportingMonth
    opening_balance: Decimal | None
    income_minus_expenses: Decimal | None
    transfers: Decimal | None
    unclassified_in: Decimal | None
    unclassified_out: Decimal | None
    adjustments_in: Decimal | None
    adjustments_out: Decimal | None
    expected_closing: Decimal | None
    closing_balance: Decimal | None
    internal_residual: Decimal | None
    previous_closing_balance: Decimal | None
    opening_gap: Decimal | None
    coverage: Coverage | Literal["outside_history"]


@dataclass(frozen=True)
class Diagnostics:
    """Public trust diagnostics and account-month reconciliation components."""

    context: ReportContext
    publication: ReportPublication
    currency: str
    evidence: tuple[AccountEvidence, ...]
    coverage: ReportCoverage
    provisional: Provisional | None
    unclassified: MoneyInOut | None
    adjustments: MoneyInOut | None
    transfers: TransferSummary | None
    reconciliations: tuple[Reconciliation, ...]


class InvalidSelectionError(ValueError):
    """`InvalidSelection`: a report context that breaks one or more selection rules."""

    def __init__(
        self,
        reasons: Collection[SelectionRule],
        unknown_account_ids: Collection[str] = (),
    ) -> None:
        """Name every rule broken and, for `unknown_account`, the unknown IDs."""
        self.reasons: frozenset[SelectionRule] = frozenset(reasons)
        self.unknown_account_ids: tuple[str, ...] = tuple(sorted(unknown_account_ids))
        message = f"invalid selection: {', '.join(sorted(self.reasons))}"
        if self.unknown_account_ids:
            message += f"; unknown accounts: {', '.join(self.unknown_account_ids)}"
        super().__init__(message)
