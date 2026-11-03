# Copyright 2026 Therkel
"""The `status` application operation: what a report can be trusted for.

Completeness reads the current Gold publication and nothing else, with no
writer lock and no write of any kind, so a store that does not exist yet stays
absent. It reuses the figures analytics already publishes and defines none of
its own.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from budget.analytics.household import HouseholdReports
from budget.analytics.reports import (
    ProvisionalReason,
    ReportContext,
    SelectionOptions,
)
from budget.gold import Coverage, ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile

# The default completeness output covers this many reporting months.
LATEST_MONTHS: Final = 12
_COPENHAGEN: Final = ZoneInfo("Europe/Copenhagen")


@dataclass(frozen=True)
class AccountMonthCompleteness:
    """What the published figures say about one account in one month."""

    account_id: str
    month: ReportingMonth
    coverage: Coverage
    provisional: tuple[ProvisionalReason, ...]


@dataclass(frozen=True)
class PublishedCompleteness:
    """The completeness of one publication, which every figure here comes from."""

    publication_id: int
    months: tuple[AccountMonthCompleteness, ...]


@dataclass(frozen=True)
class Completeness:
    """The completeness of one profile; `published` is None with nothing published."""

    published: PublishedCompleteness | None


def completeness(profile: Profile, *, now: datetime) -> Completeness:
    """Read the completeness figures of the current publication, as of `now`."""
    if not profile.gold_store.exists():
        return Completeness(published=None)
    reference_date = now.astimezone(_COPENHAGEN).date()
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
        if current is None:
            return Completeness(published=None)
        reports = HouseholdReports(store)
        options = reports.selection_options(current.publication_id, reference_date)
        months = tuple(
            _account_month(reports, options, account_id, month, reference_date)
            for account_id in (account.account_id for account in options.accounts)
            for month in _latest_months(options)
        )
    return Completeness(PublishedCompleteness(current.publication_id, months))


def _latest_months(options: SelectionOptions) -> list[ReportingMonth]:
    """Return the selectable months, no more than the latest `LATEST_MONTHS`."""
    first, last = options.first_month, options.last_month
    ordinals = range(first.year * 12 + first.month - 1, last.year * 12 + last.month)
    return [
        ReportingMonth(ordinal // 12, ordinal % 12 + 1)
        for ordinal in ordinals[-LATEST_MONTHS:]
    ]


def _account_month(
    reports: HouseholdReports,
    options: SelectionOptions,
    account_id: str,
    month: ReportingMonth,
    reference_date: date,
) -> AccountMonthCompleteness:
    """Read one account-month of the publication `options` pins."""
    overview = reports.monthly_overview(
        ReportContext(
            publication_id=options.publication.publication_id,
            account_ids=frozenset({account_id}),
            month=month,
            reference_date=reference_date,
        )
    )
    reasons = () if overview.provisional is None else overview.provisional.reasons
    return AccountMonthCompleteness(
        account_id, month, overview.coverage.status, tuple(sorted(reasons))
    )
