# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

Every store is the test profile's, in a temporary folder, created by
`migrate_gold`. All data is the synthetic worked example.
"""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from budget.gold import (
    GoldPublication,
    GoldPublications,
    GoldRepository,
    GoldResult,
    PublicationUnavailable,
)
from budget.gold.models import ReportingMonth
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.storage import migrate_gold
from budget.gold.store import (
    ConfigurationMismatchError,
    GoldStore,
    PointerMove,
    PublicationIdError,
    StaleResultsWarning,
)
from budget.inputs import ConfigurationSnapshot
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.gold.contract import GoldRepositoryContract
from tests.gold.worked_example import MONTHLY_BALANCES, PUBLICATION, RECORDS
from tests.gold.worked_silver import REGISTRY, TAXONOMY

CONFIGURATION = ConfigurationSnapshot(accounts=REGISTRY, taxonomy=TAXONOMY, rules={})
RECIPE = Recipe(
    import_runs=frozenset(
        {
            RecipeImportRun("run-current", "a" * 64),
            RecipeImportRun("run-savings", "b" * 64),
        }
    ),
    configuration_fingerprint=CONFIGURATION.fingerprint,
    decision_log_position=0,
    decision_log_prefix_sha256="c" * 64,
    code_version=None,
    contract_version="0.2",
    silver_identity_version="1",
    python_version="3.12.14",
    sqlite_version="3.53.1",
)


def publication(publication_id: int) -> GoldPublication:
    """The worked example's publication metadata, under another id."""
    return replace(PUBLICATION, publication_id=publication_id)


def publish(store: GoldStore, publication_id: int) -> GoldPublication:
    """Publish the worked example as `publication_id`, and return its metadata."""
    published = publication(publication_id)
    store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)
    return published


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    migrated = make_test_profile(tmp_path)
    migrate_gold(migrated)
    return migrated


@pytest.fixture
def store(profile: Profile) -> Iterator[GoldStore]:
    with GoldStore(profile) as opened:
        yield opened


def test_a_new_store_has_no_current_publication(tmp_path: Path) -> None:
    profile = make_test_profile(tmp_path)

    migrate_gold(profile)
    with GoldStore(profile) as store:
        current = store.current()
        available = list(store.available())

    assert current is None
    assert available == []


class TestStoredPublication(GoldRepositoryContract):
    """The worked example, published to `gold.db` and opened again."""

    @pytest.fixture
    def repository(self, store: GoldStore) -> GoldRepository:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
        return store.open(PUBLICATION.publication_id)


def test_a_first_publish_becomes_current(store: GoldStore) -> None:
    before = datetime.now(UTC)

    first = publish(store, 1)

    after = datetime.now(UTC)
    assert store.current() == first
    assert list(store.available()) == [first]
    [move] = store.pointer_history()
    assert move == PointerMove(
        moved_at=move.moved_at,
        from_publication_id=None,
        to_publication_id=1,
        cause="build",
    )
    assert before <= move.moved_at <= after


def test_the_store_hands_out_increasing_publication_ids(store: GoldStore) -> None:
    first = store.next_publication_id()
    publish(store, first)

    assert (first, store.next_publication_id()) == (1, 2)


@pytest.mark.parametrize("given", [1, 3], ids=["reused", "skipped"])
def test_a_publish_under_another_id_is_refused(store: GoldStore, given: int) -> None:
    first = publish(store, 1)

    with pytest.raises(PublicationIdError):
        publish(store, given)

    assert store.current() == first
    assert list(store.available()) == [first]
    assert len(store.pointer_history()) == 1


def test_only_the_current_and_previous_results_are_retained(store: GoldStore) -> None:
    publications: GoldPublications = store
    first, second, third = (publish(store, n) for n in (1, 2, 3))

    assert list(publications.available()) == [second, third]
    assert publications.open(2).publication() == second
    with pytest.raises(PublicationUnavailable):
        publications.open(first.publication_id)


def test_a_publication_never_published_is_unavailable(store: GoldStore) -> None:
    publish(store, 1)

    with pytest.raises(PublicationUnavailable):
        store.open(2)


def test_a_publish_that_fails_before_its_commit_changes_nothing(
    store: GoldStore,
) -> None:
    first = publish(store, 1)
    # A snapshot repeated at the end fails on the last table written, after
    # the publication row and every other result row.
    failing = replace(
        RECORDS, monthly_balances=(*MONTHLY_BALANCES, MONTHLY_BALANCES[0])
    )

    with pytest.raises(sqlite3.IntegrityError):
        store.publish(GoldResult(publication(2), failing), RECIPE, CONFIGURATION)

    assert store.current() == first
    assert list(store.available()) == [first]
    assert [move.to_publication_id for move in store.pointer_history()] == [1]
    assert store.next_publication_id() == 2


def test_a_publish_retried_after_a_failure_publishes_normally(
    store: GoldStore,
) -> None:
    first = publish(store, 1)
    failing = replace(
        RECORDS, monthly_balances=(*MONTHLY_BALANCES, MONTHLY_BALANCES[0])
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.publish(GoldResult(publication(2), failing), RECIPE, CONFIGURATION)

    second = publish(store, 2)

    assert store.current() == second
    assert list(store.available()) == [first, second]
    assert store.open(2).accounts() == store.open(1).accounts()


def test_a_recipe_is_kept_after_its_result_is_deleted(store: GoldStore) -> None:
    for publication_id in (1, 2, 3):
        publish(store, publication_id)

    kept = store.recipe(1)

    assert kept == RECIPE
    # Equality leaves the diagnostic versions out, so they are compared alone.
    assert (kept.python_version, kept.sqlite_version) == ("3.12.14", "3.53.1")


def test_a_configuration_other_than_the_recipes_is_refused(store: GoldStore) -> None:
    other = replace(CONFIGURATION, taxonomy=replace(TAXONOMY, categories={}))

    with pytest.raises(ConfigurationMismatchError):
        store.publish(GoldResult(publication(1), RECORDS), RECIPE, other)

    assert store.current() is None
    assert store.next_publication_id() == 1


def test_a_configuration_is_stored_once_by_its_fingerprint(
    store: GoldStore, profile: Profile
) -> None:
    publish(store, 1)
    publish(store, 2)

    with closing(sqlite3.connect(profile.gold_store)) as connection:
        stored = connection.execute(
            "SELECT fingerprint, content FROM configuration_snapshots"
        ).fetchall()

    assert stored == [(CONFIGURATION.fingerprint, CONFIGURATION.canonical_text)]


START, END = date(2026, 1, 1), date(2026, 5, 31)
READS: dict[str, Callable[[GoldRepository], object]] = {
    "accounts": lambda gold: gold.accounts(),
    "categories": lambda gold: gold.categories(),
    "transactions": lambda gold: gold.transactions(start_date=START, end_date=END),
    "category_allocations": lambda gold: gold.category_allocations(
        start_date=START, end_date=END
    ),
    "monthly_balances": lambda gold: gold.monthly_balances(
        start_month=ReportingMonth.of(START), end_month=ReportingMonth.of(END)
    ),
}


@pytest.mark.parametrize("read", READS.values(), ids=READS.keys())
def test_a_repository_whose_result_is_deleted_refuses_to_read(
    store: GoldStore, read: Callable[[GoldRepository], object]
) -> None:
    # publications.md: a page pinned to a publication whose result is deleted
    # gets PublicationUnavailable, never an empty page that reads as zero.
    publish(store, 1)
    pinned = store.open(1)
    publish(store, 2)
    publish(store, 3)

    with pytest.raises(PublicationUnavailable):
        read(pinned)


def test_a_failed_cleanup_after_a_publish_still_publishes(
    store: GoldStore, profile: Profile
) -> None:
    publish(store, 1)
    publish(store, 2)
    # Fault injection at the storage boundary: the cleanup that follows the
    # next publish's commit cannot delete any result.
    with closing(sqlite3.connect(profile.gold_store)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER refuse_cleanup BEFORE DELETE ON results"
            " BEGIN SELECT RAISE(ABORT, 'disk said no'); END"
        )

    with pytest.warns(StaleResultsWarning):
        third = publish(store, 3)

    assert store.current() == third
    assert store.next_publication_id() == 4
    with closing(sqlite3.connect(profile.gold_store)) as connection, connection:
        connection.execute("DROP TRIGGER refuse_cleanup")
    fourth = publish(store, 4)
    assert list(store.available()) == [third, fourth]
