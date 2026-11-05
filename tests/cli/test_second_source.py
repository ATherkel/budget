# Copyright 2026 Therkel
"""A second synthetic source gives the same Gold as `danske-csv-v1` (#181).

The same three booked transactions are exported once as `danske-csv-v1` and
once as the test-only `synthetic-ledger-v1`, each into its own household and
each run through the pipeline build. Source independence means the published
Gold records agree; nothing here touches analytics or presentation.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

import pytest

from budget.analytics import (
    HouseholdReports,
    MoneyInOut,
    MonthlyOverview,
    ReportContext,
)
from budget.bronze import BronzeStore
from budget.bronze.models import ImportDeclaration
from budget.gold import (
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldTransaction,
    ReportingMonth,
)
from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.rebuilding import rebuild_through_gold
from tests.cli.lifecycle import RULES, RUN_1_ROWS, TAXONOMY, export
from tests.cli.pipelines import prepared
from tests.importing.households import drop
from tests.silver import synthetic_ledger

EXPORTED_ON = date(2026, 3, 5)
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


def _household(folder: Path, *, categorised: bool) -> Profile:
    """A migrated household; `categorised` gives it the lifecycle's rules."""
    profile = prepared(folder).profile
    if categorised:
        profile.input_file("taxonomy.toml").write_text(TAXONOMY, encoding="utf-8")
        profile.input_file("rules.toml").write_text(RULES, encoding="utf-8")
    return profile


def _danske_household(
    folder: Path,
    *,
    content: bytes = DANSKE,
    covers_from: date = date(2026, 3, 1),
    exported_on: date = EXPORTED_ON,
    categorised: bool = False,
) -> Profile:
    profile = _household(folder, categorised=categorised)
    source = drop(profile, "joint-current", f"danske-{exported_on:%Y%m%d}.csv", content)
    with writer_lock(profile) as lock:
        import_inbox_file(lock, source, Coverage(covers_from, exported_on))
        rebuild_through_gold(lock, now=BUILT_AT)
    return profile


def _synthetic_household(
    folder: Path,
    *,
    content: bytes = SYNTHETIC,
    covers_from: date = date(2026, 3, 1),
    exported_on: date = EXPORTED_ON,
    categorised: bool = False,
) -> Profile:
    profile = _household(folder, categorised=categorised)
    source = folder / "ledger.tsv"
    source.write_bytes(content)
    declaration = ImportDeclaration(
        declared_account_id="joint-current",
        source_format=synthetic_ledger.FORMAT_ID,
        covers_from=covers_from,
        covers_through=exported_on,
        exported_on=exported_on,
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


def _overview(profile: Profile, month: ReportingMonth) -> MonthlyOverview:
    """`month`'s household overview from the profile's current publication."""
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
        assert current is not None
        context = ReportContext(
            publication_id=current.publication_id,
            account_ids=frozenset({"joint-current"}),
            month=month,
            reference_date=date(2026, 4, 15),
        )
        return HouseholdReports(store).monthly_overview(context)


def test_both_sources_give_the_same_monthly_report(
    danske: Profile, synthetic: Profile
) -> None:
    march = ReportingMonth(2026, 3)
    from_danske = _overview(danske, march)
    from_synthetic = _overview(synthetic, march)

    assert from_danske.unclassified == MoneyInOut(
        money_in=Decimal("2000.00"), money_out=Decimal("-925.50"), count=3
    )
    assert from_synthetic == from_danske


# February is the lifecycle's rows; March continues their balance chain.
CATEGORISED_ROWS = (
    *RUN_1_ROWS,
    ("03.03.2026", "NETTO 0412", "-200,00", "6.751,00"),
    ("10.03.2026", "IKEA 551", "-500,00", "6.251,00"),
    ("15.03.2026", "NETFLIX.COM", "-129,00", "6.122,00"),
)
CATEGORISED_EXPORTED_ON = date(2026, 4, 2)


def _iso(dato: str) -> str:
    day, month, year = dato.split(".")
    return f"{year}-{month}-{day}"


def _plain(amount: str) -> str:
    return amount.replace(".", "").replace(",", ".")


def _categorised_pair(
    folder: Path, rows: tuple[tuple[str, str, str, str], ...] = CATEGORISED_ROWS
) -> tuple[Profile, Profile]:
    """The same rows built through Gold from each source, under the lifecycle rules."""
    shared = {
        "covers_from": date(2026, 2, 1),
        "exported_on": CATEGORISED_EXPORTED_ON,
        "categorised": True,
    }
    danske_profile = _danske_household(
        folder / "danske", content=export(rows), **shared
    )
    synthetic_profile = _synthetic_household(
        folder / "synthetic",
        content=synthetic_ledger.payload(
            *(
                (_iso(dato), _plain(amount), text, _plain(saldo))
                for dato, text, amount, saldo in rows
            )
        ),
        **shared,
    )
    return danske_profile, synthetic_profile


@pytest.mark.parametrize("month", [ReportingMonth(2026, 2), ReportingMonth(2026, 3)])
def test_both_sources_categorise_each_month_the_same(
    tmp_path: Path, month: ReportingMonth
) -> None:
    danske_profile, synthetic_profile = _categorised_pair(tmp_path)

    from_danske = _overview(danske_profile, month)
    from_synthetic = _overview(synthetic_profile, month)

    assert from_danske.categories != ()
    assert from_synthetic == from_danske
