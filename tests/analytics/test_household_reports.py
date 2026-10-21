# Copyright 2026 Therkel
"""The production household reports over a real test-profile Gold store."""

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    NothingPublishedError,
    PublicationUnavailableError,
    ReportContext,
    ReportPublication,
)
from budget.gold import GoldPublication, GoldRecords, GoldResult, ReportingMonth
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.gold.test_store import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    """Create and migrate the ephemeral Gold store this module tests."""
    migrated = make_test_profile(tmp_path)
    migrate_gold(migrated)
    return migrated


@pytest.fixture
def gold_store(profile: Profile) -> Iterator[GoldStore]:
    """Yield the one real Gold store used by a test."""
    with GoldStore(profile) as store:
        yield store


def _publish(store: GoldStore, publication_id: int) -> GoldPublication:
    publication = replace(PUBLICATION, publication_id=publication_id)
    store.publish(GoldResult(publication, RECORDS), RECIPE, CONFIGURATION)
    return publication


def _make_known_at(profile: Profile, publication_id: int) -> None:
    """Make an already retained publication an explicit as-known-at view."""
    with sqlite3.connect(profile.gold_store) as connection:
        connection.execute(
            "UPDATE publications SET kind = 'as_known_at' WHERE publication_id = ?",
            (publication_id,),
        )


def test_current_publication_returns_the_current_build(gold_store: GoldStore) -> None:
    publication = _publish(gold_store, 1)

    assert HouseholdReports(gold_store).current_publication() == ReportPublication(
        publication_id=1,
        kind="pipeline",
        label=None,
        known_at=publication.known_at,
        is_current=True,
    )


def test_before_the_first_build_nothing_is_published(gold_store: GoldStore) -> None:
    reports = HouseholdReports(gold_store)

    with pytest.raises(NothingPublishedError):
        reports.current_publication()
    assert gold_store.current() is None


def test_selection_options_open_the_requested_superseded_publication(
    gold_store: GoldStore,
) -> None:
    old_records = replace(
        RECORDS,
        accounts=tuple(
            replace(account, display_name=f"Old {account.display_name}")
            for account in RECORDS.accounts
        ),
    )
    old = replace(PUBLICATION, publication_id=1)
    gold_store.publish(GoldResult(old, old_records), RECIPE, CONFIGURATION)
    _publish(gold_store, 2)

    options = HouseholdReports(gold_store).selection_options(1, date(2026, 5, 14))

    assert (options.publication.publication_id, options.publication.is_current) == (
        1,
        False,
    )
    assert [account.display_name for account in options.accounts] == [
        "Old Joint current",
        "Old Joint savings",
    ]


def test_monthly_overview_keeps_reading_a_superseded_pipeline_page(
    gold_store: GoldStore,
) -> None:
    old_records = replace(
        RECORDS,
        accounts=tuple(
            replace(account, display_name=f"Pinned {account.display_name}")
            for account in RECORDS.accounts
        ),
    )
    old = replace(PUBLICATION, publication_id=1)
    gold_store.publish(GoldResult(old, old_records), RECIPE, CONFIGURATION)
    _publish(gold_store, 2)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 6),
        reference_date=date(2026, 6, 3),
    )

    report = HouseholdReports(gold_store).monthly_overview(context)

    assert (report.publication.publication_id, report.publication.is_current) == (
        1,
        False,
    )
    assert report.context == context
    assert [row.display_name for row in report.coverage.account_months] == [
        "Pinned Joint current",
        "Pinned Joint savings",
    ]


def test_an_unavailable_pinned_result_offers_the_current_id(
    gold_store: GoldStore,
) -> None:
    for publication_id in (1, 2, 3):
        _publish(gold_store, publication_id)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )

    with pytest.raises(PublicationUnavailableError) as raised:
        HouseholdReports(gold_store).monthly_overview(context)

    assert (raised.value.publication_id, raised.value.current_publication_id) == (1, 3)


def test_selection_options_expose_the_same_unavailable_recovery(
    gold_store: GoldStore,
) -> None:
    for publication_id in (1, 2, 3):
        _publish(gold_store, publication_id)

    with pytest.raises(PublicationUnavailableError) as raised:
        HouseholdReports(gold_store).selection_options(1, date(2026, 5, 14))

    assert (raised.value.publication_id, raised.value.current_publication_id) == (1, 3)


def test_monthly_overview_keeps_the_existing_selection_failure(
    gold_store: GoldStore,
) -> None:
    _publish(gold_store, 1)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset(),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )

    with pytest.raises(InvalidSelectionError) as raised:
        HouseholdReports(gold_store).monthly_overview(context)

    assert raised.value.reasons == {"no_accounts"}


def test_as_known_at_uses_the_known_date_in_copenhagen(
    profile: Profile, gold_store: GoldStore
) -> None:
    # 22:30 UTC on 30 June is already 1 July in Copenhagen.
    known_at = datetime(2026, 6, 30, 22, 30, tzinfo=UTC)
    view = replace(
        PUBLICATION,
        publication_id=1,
        kind="pipeline",
        label="Known at",
        known_at=known_at,
    )
    gold_store.publish(GoldResult(view, RECORDS), RECIPE, CONFIGURATION)
    _publish(gold_store, 2)
    _publish(gold_store, 3)
    _make_known_at(profile, 1)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 7),
        reference_date=date(2026, 5, 14),
    )

    reports = HouseholdReports(gold_store)
    report = reports.monthly_overview(context)
    options = reports.selection_options(1, date(2026, 5, 14))

    assert report.context == replace(context, reference_date=date(2026, 7, 1))
    assert (report.publication.kind, report.publication.is_current) == (
        "as_known_at",
        False,
    )
    assert options.last_month == ReportingMonth(2026, 7)


def test_as_known_at_uses_historical_copenhagen_summer_time(
    profile: Profile, gold_store: GoldStore
) -> None:
    # Denmark's summer-time period ended in September in 1995.
    known_at = datetime(1995, 9, 30, 22, 30, tzinfo=UTC)
    view = replace(
        PUBLICATION,
        publication_id=1,
        kind="pipeline",
        label="1995 known at",
        known_at=known_at,
    )
    gold_store.publish(GoldResult(view, GoldRecords()), RECIPE, CONFIGURATION)
    _publish(gold_store, 2)
    _make_known_at(profile, 1)

    options = HouseholdReports(gold_store).selection_options(1, date(1995, 9, 1))

    assert options.first_month == ReportingMonth(1995, 9)
    assert options.last_month == ReportingMonth(1995, 9)
