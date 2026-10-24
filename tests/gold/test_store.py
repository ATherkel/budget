# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

Every store is the test profile's, in a temporary folder, created by
`migrate_gold`, or held, empty or migrated, by a second connection to show
that the migration refuses it. All data is the synthetic worked example.
"""

import re
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from queue import Queue
from threading import Thread

import pytest

from budget import sqlstore
from budget.gold import (
    GoldPublication,
    GoldPublications,
    GoldRepository,
    GoldResult,
    GoldStoreClosedError,
    GoldStoreLifecycleError,
    GoldStoreReadOnlyError,
    GoldStoreThreadError,
    PublicationUnavailableError,
)
from budget.gold.models import ReportingMonth
from budget.gold.storage import migrate_gold, open_gold_connection
from budget.gold.store import (
    ConfigurationMismatchError,
    GoldStore,
    PointerMove,
    PublicationIdError,
    PublicationKindError,
    StaleResultsWarning,
)
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.silver import MoneyPrecisionError
from budget.sqlstore import StoreBusyError
from tests.bronze.migration_resources import GOLD_MIGRATIONS, added_migration
from tests.gold.contract import GoldRepositoryContract
from tests.gold.publishing import CONFIGURATION, RECIPE, publication, publish
from tests.gold.worked_example import (
    CATEGORY_ALLOCATIONS,
    MONTHLY_BALANCES,
    PUBLICATION,
    RECORDS,
    SAVINGS,
)
from tests.gold.worked_silver import TAXONOMY


def _assert_raises_in_thread(
    error_type: type[Exception], action: Callable[[], object]
) -> None:
    outcome: Queue[Exception] = Queue()

    def run() -> None:
        try:
            action()
        except (GoldStoreLifecycleError, sqlite3.Error) as error:
            outcome.put(error)
        else:
            outcome.put(AssertionError("the operation did not fail"))

    thread = Thread(target=run)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    outcome_value = outcome.get_nowait()
    assert isinstance(outcome_value, error_type), outcome_value


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


def test_a_read_only_store_refuses_publish_without_writing(profile: Profile) -> None:
    with GoldStore(profile) as writer:
        first = publish(writer, 1)

    with GoldStore(profile, read_only=True) as reader:
        assert reader.current() == first
        assert reader.open(first.publication_id).accounts()
        with pytest.raises(GoldStoreReadOnlyError):
            reader.publish(GoldResult(publication(2), RECORDS), RECIPE, CONFIGURATION)

    with GoldStore(profile) as writer:
        assert writer.current() == first
        assert list(writer.available()) == [first]
        assert writer.next_publication_id() == 2


CLOSED_ACTIONS: dict[str, Callable[[GoldStore, GoldRepository], object]] = {
    "current": lambda store, _repository: store.current(),
    "available": lambda store, _repository: store.available(),
    "open": lambda store, _repository: store.open(1),
    "next publication id": lambda store, _repository: store.next_publication_id(),
    "recipe": lambda store, _repository: store.recipe(1),
    "pointer history": lambda store, _repository: store.pointer_history(),
    "publish": lambda store, _repository: store.publish(
        GoldResult(publication(2), RECORDS), RECIPE, CONFIGURATION
    ),
    "cached publication metadata": lambda _store, repository: repository.publication(),
    "repository accounts": lambda _store, repository: repository.accounts(),
}


@pytest.mark.parametrize("action", CLOSED_ACTIONS.values(), ids=CLOSED_ACTIONS.keys())
def test_every_public_operation_refuses_a_closed_store(
    profile: Profile, action: Callable[[GoldStore, GoldRepository], object]
) -> None:
    store = GoldStore(profile)
    publish(store, 1)
    repository = store.open(1)
    store.close()

    store.close()
    with pytest.raises(GoldStoreClosedError):
        action(store, repository)


def test_a_wrong_thread_read_or_close_does_not_release_the_owner(
    profile: Profile,
) -> None:
    with GoldStore(profile) as store:
        first = publish(store, 1)

        _assert_raises_in_thread(GoldStoreThreadError, store.current)
        assert store.current() == first

        _assert_raises_in_thread(GoldStoreThreadError, store.close)
        assert store.current() == first


@pytest.mark.parametrize(
    "read",
    [
        lambda repository: repository.publication(),
        lambda repository: repository.accounts(),
    ],
    ids=["cached-metadata", "data"],
)
def test_a_borrowed_repository_refuses_its_owner_from_another_thread(
    profile: Profile, read: Callable[[GoldRepository], object]
) -> None:
    with GoldStore(profile) as store:
        publish(store, 1)
        repository = store.open(1)

        _assert_raises_in_thread(GoldStoreThreadError, lambda: read(repository))
        assert repository.publication().publication_id == 1
        assert repository.accounts()


def test_each_thread_can_open_its_own_read_only_reader(profile: Profile) -> None:
    with GoldStore(profile) as writer:
        first = publish(writer, 1)

    def read() -> GoldPublication | None:
        with GoldStore(profile, read_only=True) as reader:
            return reader.current()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(read) for _ in range(2)]

    assert [future.result() for future in futures] == [first, first]


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
    with pytest.raises(PublicationUnavailableError):
        publications.open(first.publication_id)


def test_a_publication_never_published_is_unavailable(store: GoldStore) -> None:
    publish(store, 1)

    with pytest.raises(PublicationUnavailableError):
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
    # gets PublicationUnavailableError, never an empty page that reads as zero.
    publish(store, 1)
    pinned = store.open(1)
    publish(store, 2)
    publish(store, 3)

    with pytest.raises(PublicationUnavailableError):
        read(pinned)


@pytest.fixture
def short_busy_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wait 100 ms for a held store instead of the real five seconds."""
    monkeypatch.setattr(sqlstore, "BUSY_TIMEOUT_MS", 100)


@pytest.mark.usefixtures("short_busy_timeout")
def test_migrate_refuses_a_gold_store_another_program_holds(tmp_path: Path) -> None:
    # Such as DB Browser for SQLite, left open in a write transaction.
    profile = make_test_profile(tmp_path)
    profile.gold_store.parent.mkdir(parents=True)
    with closing(sqlite3.connect(profile.gold_store, isolation_level=None)) as holder:
        holder.execute("BEGIN EXCLUSIVE")

        with pytest.raises(
            StoreBusyError, match=f"{re.escape(str(profile.gold_store))} is in use"
        ):
            migrate_gold(profile)

        holder.execute("ROLLBACK")
    assert profile.gold_store.read_bytes() == b""


@pytest.mark.usefixtures("short_busy_timeout")
def test_migrate_refuses_to_upgrade_a_gold_store_another_program_writes_to(
    profile: Profile,
) -> None:
    # A migrated store is in WAL mode, where a writer leaves reads open: the
    # refusal comes only when the pending migration starts to write.
    store = profile.gold_store
    with closing(sqlite3.connect(store)) as reader:
        version = reader.execute("PRAGMA user_version").fetchone()[0]
    with (
        closing(sqlite3.connect(store, isolation_level=None)) as holder,
        added_migration(
            "CREATE TABLE marker (x TEXT) STRICT;\n", folder=GOLD_MIGRATIONS
        ),
    ):
        holder.execute("BEGIN IMMEDIATE")

        with pytest.raises(StoreBusyError, match=f"{re.escape(str(store))} is in use"):
            migrate_gold(profile)

        holder.execute("ROLLBACK")
    with closing(sqlite3.connect(store)) as reader:
        assert reader.execute("PRAGMA user_version").fetchone()[0] == version
        tables = reader.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        assert "marker" not in {name for (name,) in tables}


def test_a_busy_cleanup_after_a_publish_still_publishes(
    profile: Profile, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fault injection at the storage boundary: another program takes the
    # store's write lock between the publish's commit and its cleanup, so the
    # cleanup waits out the real busy timeout, about five seconds.
    holder = sqlite3.connect(profile.gold_store, isolation_level=None)
    writes_begun = 0

    def lock_before_the_cleanup(statement: str) -> None:
        nonlocal writes_begun
        if statement == "BEGIN IMMEDIATE":
            writes_begun += 1
            if writes_begun == 2:
                holder.execute("BEGIN EXCLUSIVE")

    def traced(opened: Profile, *, read_only: bool = False) -> sqlite3.Connection:
        connection = open_gold_connection(opened, read_only=read_only)
        connection.set_trace_callback(lock_before_the_cleanup)
        return connection

    monkeypatch.setattr("budget.gold.store.open_gold_connection", traced)
    with closing(holder), GoldStore(profile) as store:
        with pytest.warns(StaleResultsWarning, match="database is locked"):
            first = publish(store, 1)
        holder.execute("ROLLBACK")

        assert store.current() == first


def test_a_cleanup_defect_after_a_publish_propagates(
    store: GoldStore, profile: Profile
) -> None:
    publish(store, 1)
    publish(store, 2)
    # A defect, not a passing condition: the cleanup can never delete a result.
    with closing(sqlite3.connect(profile.gold_store)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER refuse_cleanup BEFORE DELETE ON results"
            " BEGIN SELECT RAISE(ABORT, 'cleanup is broken'); END"
        )

    with pytest.raises(sqlite3.IntegrityError) as raised:
        publish(store, 3)

    assert "publication 3 is current" in " ".join(raised.value.__notes__)
    assert store.current() == publication(3)
    assert store.next_publication_id() == 4


def test_a_view_is_never_published_as_current(store: GoldStore) -> None:
    # publications.md, invariant 6: an as_known_at publication is never current.
    view = replace(publication(1), kind="as_known_at")

    with pytest.raises(PublicationKindError):
        store.publish(GoldResult(view, RECORDS), RECIPE, CONFIGURATION)

    assert store.current() is None
    assert store.next_publication_id() == 1


@pytest.mark.parametrize(
    "changes",
    [{"account_id": SAVINGS}, {"transaction_date": date(1999, 1, 1)}],
    ids=["other-account", "other-date"],
)
def test_an_allocation_unlike_its_transaction_is_refused(
    store: GoldStore, changes: dict[str, object]
) -> None:
    # gold-contract.md, invariant 6: an allocation's account_id and
    # transaction_date equal its transaction's, so reads by account or date
    # never move category money onto another account or month.
    first, *rest = CATEGORY_ALLOCATIONS
    moved = replace(first, **changes)
    records = replace(RECORDS, category_allocations=(moved, *rest))

    with pytest.raises(sqlite3.IntegrityError):
        store.publish(GoldResult(publication(1), records), RECIPE, CONFIGURATION)

    assert store.current() is None


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_a_blank_label_is_refused(store: GoldStore, blank: str) -> None:
    # A label keeps its result for good, so a blank one would pin it unnamed.
    labeled = replace(publication(1), label=blank)

    with pytest.raises(sqlite3.IntegrityError):
        store.publish(GoldResult(labeled, RECORDS), RECIPE, CONFIGURATION)

    assert store.current() is None


def test_a_labeled_result_is_retained_after_later_publishes(store: GoldStore) -> None:
    labeled = replace(publication(1), label="March review")
    store.publish(GoldResult(labeled, RECORDS), RECIPE, CONFIGURATION)

    later = [publish(store, n) for n in (2, 3, 4)]

    assert list(store.available()) == [labeled, *later[1:]]
    assert store.open(1).publication() == labeled


def test_an_amount_its_currency_cannot_hold_writes_nothing(store: GoldStore) -> None:
    first = publish(store, 1)
    # Encoding refuses it before the write transaction begins.
    last = replace(MONTHLY_BALANCES[-1], closing_balance=Decimal("1.005"))
    records = replace(RECORDS, monthly_balances=(*MONTHLY_BALANCES[:-1], last))

    with pytest.raises(MoneyPrecisionError):
        store.publish(GoldResult(publication(2), records), RECIPE, CONFIGURATION)

    assert store.current() == first
    assert store.next_publication_id() == 2
