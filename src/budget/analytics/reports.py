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
    Coverage,
    OwnershipScope,
    PublicationKind,
    ReportingMonth,
)

type AccountMonthStatus = Literal["partial", "no_data", "outside_history"]
type ProvisionalReason = Literal["current_month", "late_bookings_unsettled"]
type SelectionRule = Literal[
    "no_accounts", "unknown_account", "mixed_currencies", "month_out_of_range"
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
    ownership_scope: OwnershipScope
    currency: str


@dataclass(frozen=True)
class SelectionOptions:
    """What a page may select within one publication on one reference date."""

    publication: ReportPublication
    accounts: tuple[SelectableAccount, ...]
    first_month: ReportingMonth
    last_month: ReportingMonth


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
    coverage: ReportCoverage
    provisional: Provisional | None


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


class NothingPublishedError(LookupError):
    """`NothingPublished`: Gold has no current publication to report from."""
