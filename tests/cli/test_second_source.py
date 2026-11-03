# Copyright 2026 Therkel
"""A second synthetic source gives the same Gold as `danske-csv-v1` (#181).

The same three booked transactions are exported once as `danske-csv-v1` and
once as the test-only `synthetic-ledger-v1`, each into its own household and
each run through the pipeline build. Source independence means the published
Gold records agree; nothing here touches analytics or presentation.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

import pytest

from budget.bronze import BronzeStore
from budget.bronze.models import ImportDeclaration
from budget.gold import (
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldTransaction,
)
from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.rebuilding import rebuild_through_gold
from tests.cli.pipelines import prepared
from tests.importing.households import drop
from tests.silver import synthetic_ledger

EXPORTED_ON = date(2026, 3, 5)
COVERS = Coverage(covers_from=date(2026, 3, 1), covers_through=EXPORTED_ON)
BUILT_AT = datetime(2026, 3, 6, tzinfo=UTC)

# Opening balance 1000,00; every account, text and amount is invented.
DANSKE = (
    '"Dato","Tekst","Beløb","Saldo","Status","Afstemt"\r\n'
    '"02.03.2026","GROCER","-125,50","874,50","Udført","Nej"\r\n'
    '"03.03.2026","SALARY","2.000,00","2.874,50","Udført","Nej"\r\n'
    '"04.03.2026","RENT","-800,00","2.074,50","Udført","Nej"'
).encode("cp1252")
SYNTHETIC = synthetic_ledger.payload(
    ("2026-03-02", "-125.50", "GROCER", "874.50"),
    ("2026-03-03", "2000.00", "SALARY", "2874.50"),
    ("2026-03-04", "-800.00", "RENT", "2074.50"),
)


def _danske_household(folder: Path) -> Profile:
    profile = prepared(folder).profile
    source = drop(profile, "joint-current", "danske-20260305.csv", DANSKE)
    with writer_lock(profile) as lock:
        import_inbox_file(lock, source, COVERS)
        rebuild_through_gold(lock, now=BUILT_AT)
    return profile


def _synthetic_household(folder: Path) -> Profile:
    profile = prepared(folder).profile
    source = folder / "ledger.tsv"
    source.write_bytes(SYNTHETIC)
    declaration = ImportDeclaration(
        declared_account_id="joint-current",
        source_format=synthetic_ledger.FORMAT_ID,
        covers_from=COVERS.covers_from,
        covers_through=COVERS.covers_through,
        exported_on=EXPORTED_ON,
    )
    parsers = {synthetic_ledger.FORMAT_ID: synthetic_ledger.PARSER}
    with BronzeStore(profile, parsers=parsers) as bronze:
        bronze.import_file(source, declaration)
    with writer_lock(profile) as lock:
        rebuild_through_gold(
            lock,
            now=BUILT_AT,
            formats={synthetic_ledger.FORMAT_ID: synthetic_ledger.FORMAT},
        )
    return profile


@pytest.fixture
def danske(tmp_path: Path) -> Profile:
    """A household whose export is `danske-csv-v1`, built through Gold."""
    return _danske_household(tmp_path / "danske")


@pytest.fixture
def synthetic(tmp_path: Path) -> Profile:
    """A household whose export is `synthetic-ledger-v1`, built through Gold."""
    return _synthetic_household(tmp_path / "synthetic")


class Published(NamedTuple):
    """Every consumer record of one Gold publication."""

    accounts: Sequence[GoldAccount]
    categories: Sequence[GoldCategory]
    transactions: Sequence[GoldTransaction]
    allocations: Sequence[GoldCategoryAllocation]


def _published(profile: Profile) -> Published:
    """Every consumer record of the profile's current Gold publication."""
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
        assert current is not None
        gold = store.open(current.publication_id)
        first, last = date(2026, 1, 1), date(2026, 12, 31)
        return Published(
            accounts=gold.accounts(),
            categories=gold.categories(),
            transactions=gold.transactions(start_date=first, end_date=last),
            allocations=gold.category_allocations(start_date=first, end_date=last),
        )


def test_both_sources_publish_the_same_gold_records(
    danske: Profile, synthetic: Profile
) -> None:
    from_danske = _published(danske)
    from_synthetic = _published(synthetic)

    assert len(from_danske.transactions) == 3
    assert from_synthetic == from_danske
