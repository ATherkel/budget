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

from budget.analytics.household import HouseholdReports
from budget.analytics.reports import (
    MoneyInOut,
    ProvisionalReason,
    ReportContext,
    SelectionOptions,
)
from budget.gold import Coverage, ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.silver import ImportRunResult, SilverStore
from budget.timezone import COPENHAGEN

# The default completeness output covers this many reporting months.
LATEST_MONTHS: Final = 12


@dataclass(frozen=True)
class AccountMonthCompleteness:
    """What the published figures say about one account in one month."""

    account_id: str
    month: ReportingMonth
    coverage: Coverage
    provisional: tuple[ProvisionalReason, ...]
    currency: str
    # None when the month has no evidence, which is not the same as zero.
    unclassified: MoneyInOut | None


@dataclass(frozen=True)
class PublishedCompleteness:
    """The completeness of one publication, which every figure here comes from."""

    publication_id: int
    months: tuple[AccountMonthCompleteness, ...]


@dataclass(frozen=True)
class AccountEvidenceStatus:
    """What the admitted exports say about one account, as Silver stored them."""

    account_id: str
    latest_export: date
    evidence_through: date
    quarantined: tuple[ImportRunResult, ...] = ()


@dataclass(frozen=True)
class ImportEvidence:
    """Operational import evidence, read apart from any publication's figures."""

    accounts: tuple[AccountEvidenceStatus, ...]


@dataclass(frozen=True)
class Completeness:
    """The completeness of one profile; `published` is None with nothing published."""

    published: PublishedCompleteness | None
    evidence: ImportEvidence | None = None


def completeness(profile: Profile, *, now: datetime) -> Completeness:
    """Read the import evidence and the current publication's figures."""
    return Completeness(
        published=_published(profile, now), evidence=_import_evidence(profile)
    )


def _import_evidence(profile: Profile) -> ImportEvidence | None:
    """Read each account's latest export and Evidence through from Silver."""
    if not profile.silver_store.exists():
        return None
    with SilverStore(profile, read_only=True) as store:
        result = store.read()
    exports: dict[str, date] = {}
    for each in result.evidence_exports:
        exports[each.account_id] = max(
            each.exported_on, exports.get(each.account_id, each.exported_on)
        )
    through: dict[str, date] = {}
    for each in result.account_evidence:
        through[each.account_id] = max(
            each.covers_through, through.get(each.account_id, each.covers_through)
        )
    return ImportEvidence(
        tuple(
            AccountEvidenceStatus(
                account_id,
                exports[account_id],
                through[account_id],
                tuple(
                    run
                    for run in result.import_run_results
                    if run.account_id == account_id and run.status == "quarantined"
                ),
            )
            for account_id in sorted(exports.keys() & through.keys())
        )
    )


def _published(profile: Profile, now: datetime) -> PublishedCompleteness | None:
    """Read the completeness figures of the current publication, as of `now`."""
    if not profile.gold_store.exists():
        return None
    reference_date = now.astimezone(COPENHAGEN).date()
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
        if current is None:
            return None
        reports = HouseholdReports(store)
        options = reports.selection_options(current.publication_id, reference_date)
        months = tuple(
            _account_month(reports, options, account_id, month, reference_date)
            for account_id in (account.account_id for account in options.accounts)
            for month in _latest_months(options)
        )
    return PublishedCompleteness(current.publication_id, months)


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
        account_id,
        month,
        overview.coverage.status,
        tuple(sorted(reasons)),
        overview.currency,
        overview.unclassified,
    )
