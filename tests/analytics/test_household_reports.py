# Copyright 2026 Therkel
"""The production household reports over a real test-profile Gold store."""

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    MonthlyOverview,
    NothingPublishedError,
    PublicationUnavailableError,
    ReportContext,
    ReportPublication,
)
from budget.gold import (
    GoldPublication,
    GoldRecords,
    GoldResult,
    GoldStoreClosedError,
    ReportingMonth,
)
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


SECOND_BUILD_AT = datetime(2026, 5, 16, 7, 30, tzinfo=UTC)


def _publish_known_at(
    store: GoldStore, publication_id: int, known_at: datetime
) -> None:
    """Publish the worked example as `publication_id`, known at `known_at`.

    It was built an hour later, so a report that shows `built_at` is caught.
    """
    published = replace(
        PUBLICATION,
        publication_id=publication_id,
        known_at=known_at,
        built_at=known_at + timedelta(hours=1),
    )
    store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)


def test_the_current_publication_is_the_one_gold_marks_current(
    gold_store: GoldStore,
) -> None:
    _publish_known_at(gold_store, 1, PUBLICATION.known_at)
    _publish_known_at(gold_store, 2, SECOND_BUILD_AT)

    assert HouseholdReports(gold_store).current_publication() == ReportPublication(
        publication_id=2,
        kind="pipeline",
        label=None,
        known_at=SECOND_BUILD_AT,
        is_current=True,
    )


def test_a_pinned_overview_turns_not_current_once_a_newer_build_is_current(
    gold_store: GoldStore,
) -> None:
    reports = HouseholdReports(gold_store)
    _publish_known_at(gold_store, 1, PUBLICATION.known_at)
    pinned = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current"}),
        month=ReportingMonth(2026, 4),
        reference_date=date(2026, 5, 14),
    )
    p1 = ReportPublication(
        publication_id=1,
        kind="pipeline",
        label=None,
        known_at=PUBLICATION.known_at,
        is_current=True,
    )

    before = reports.monthly_overview(pinned)
    _publish_known_at(gold_store, 2, SECOND_BUILD_AT)
    after = reports.monthly_overview(pinned)

    assert (before.publication, after.publication) == (
        p1,
        replace(p1, is_current=False),
    )


def test_before_the_first_build_nothing_is_published(gold_store: GoldStore) -> None:
    reports = HouseholdReports(gold_store)

    with pytest.raises(NothingPublishedError):
        reports.current_publication()
    assert gold_store.current() is None


def test_a_report_data_object_survives_a_read_only_request_scope(
    profile: Profile,
) -> None:
    with GoldStore(profile) as writer:
        _publish(writer, 1)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )

    def read() -> MonthlyOverview:
        with GoldStore(profile, read_only=True) as reader:
            return HouseholdReports(reader).monthly_overview(context)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(read) for _ in range(2)]

    reports = [future.result() for future in futures]
    assert [report.context for report in reports] == [context, context]


def test_closed_store_lifecycle_errors_propagate_from_reports(
    gold_store: GoldStore,
) -> None:
    _publish(gold_store, 1)
    reports = HouseholdReports(gold_store)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )
    gold_store.close()

    with pytest.raises(GoldStoreClosedError):
        reports.current_publication()
    with pytest.raises(GoldStoreClosedError):
        reports.selection_options(1, date(2026, 5, 14))
    with pytest.raises(GoldStoreClosedError):
        reports.monthly_overview(context)


def test_read_only_reports_keep_superseded_and_deleted_recovery(
    profile: Profile,
) -> None:
    with GoldStore(profile) as writer:
        _publish(writer, 1)
        _publish(writer, 2)
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset({"joint-current", "joint-savings"}),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )

    with GoldStore(profile, read_only=True) as reader:
        report = HouseholdReports(reader).monthly_overview(context)

    assert (report.publication.publication_id, report.publication.is_current) == (
        1,
        False,
    )

    with GoldStore(profile) as writer:
        _publish(writer, 3)
    with (
        GoldStore(profile, read_only=True) as reader,
        pytest.raises(PublicationUnavailableError) as raised,
    ):
        HouseholdReports(reader).monthly_overview(context)

    assert (raised.value.publication_id, raised.value.current_publication_id) == (1, 3)


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


def test_unavailable_selection_options_without_current_offer_no_replacement(
    gold_store: GoldStore,
) -> None:
    with pytest.raises(PublicationUnavailableError) as raised:
        HouseholdReports(gold_store).selection_options(42, date(2026, 5, 14))

    assert (raised.value.publication_id, raised.value.current_publication_id) == (
        42,
        None,
    )


def test_unavailable_overview_without_current_offers_no_replacement(
    gold_store: GoldStore,
) -> None:
    context = ReportContext(
        publication_id=42,
        account_ids=frozenset({"joint-current"}),
        month=ReportingMonth(2026, 2),
        reference_date=date(2026, 5, 14),
    )

    with pytest.raises(PublicationUnavailableError) as raised:
        HouseholdReports(gold_store).monthly_overview(context)

    assert (raised.value.publication_id, raised.value.current_publication_id) == (
        42,
        None,
    )


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
