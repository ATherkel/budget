# Copyright 2026 Therkel
"""The synthetic lifecycle of `publications.md`, as a household's exports.

February 2026 on `joint-current`: transactions A, B, C and E arrive in run-1,
and F, a late booking, in run-2. Balances chain from a 10,000.00 opening, so
Silver admits both exports. The rules, the taxonomy and every figure are
invented.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from budget.gold import GoldRepository
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from budget.rebuilding import rebuild_from_silver
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS, drop

HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'
TAXONOMY = """\
format = 1

[group.food]
name = "Food"
direction = "expense"

[category.groceries]
name = "Groceries"
group = "food"

[group.home]
name = "Home"
direction = "expense"

[category.household-goods]
name = "Household goods"
group = "home"

[group.family]
name = "Family"
direction = "expense"

[category.gifts]
name = "Gifts"
group = "family"

[group.leisure]
name = "Leisure"
direction = "expense"

[category.streaming]
name = "Streaming"
group = "leisure"
"""
RULES = """\
format = 1

[[rule]]
id = "r-netto"
when.description_contains = "NETTO"
then.category = "groceries"

[[rule]]
id = "r-home"
when.description_contains = "IKEA"
then.category = "household-goods"

[[rule]]
id = "r-streaming"
when.description_contains = "NETFLIX"
then.category = "streaming"
"""
# Each row is the bank's date, text, amount and balance after it.
RUN_1_ROWS = (
    ("02.02.2026", "NETTO 0412", "-640,00", "9.360,00"),
    ("07.02.2026", "IKEA 551", "-2.400,00", "6.960,00"),
    ("12.02.2026", "NETTO 0412", "120,00", "7.080,00"),
    ("18.02.2026", "NETFLIX.COM", "-129,00", "6.951,00"),
)
RUN_2_ROWS = (*RUN_1_ROWS, ("27.02.2026", "NETTO 0412", "-300,00", "6.651,00"))
FEBRUARY = (date(2026, 2, 1), date(2026, 2, 28))


@dataclass(frozen=True)
class Lifecycle:
    """A migrated profile whose inputs are the lifecycle's, with run-1 built."""

    profile_file: Path
    profile: Profile


def export(rows: tuple[tuple[str, str, str, str], ...]) -> bytes:
    """A `danske-csv-v1` export with one booked row per tuple."""
    lines = [
        f'"{dato}"," Mad "," Dagligvarer ","{text}","{amount}","{balance}",'
        '"Udført","Nej"'
        for dato, text, amount, balance in rows
    ]
    return "\r\n".join([HEADER, *lines]).encode("cp1252")


def import_export(
    profile: Profile,
    name: str,
    rows: tuple[tuple[str, str, str, str], ...],
    through: date,
    account_id: str = "joint-current",
) -> None:
    """Import one export covering February through `through`, then build Silver."""
    source = drop(profile, account_id, name, export(rows))
    with writer_lock(profile) as lock:
        import_inbox_file(lock, source, Coverage(date(2026, 2, 1), through))
        rebuild_from_silver(lock)


def lifecycle(folder: Path) -> Lifecycle:
    """Write the inputs and import run-1, so a rebuild publishes P1."""
    folder.mkdir(parents=True, exist_ok=True)
    profile_file = write_profile(folder)
    assert migrate(profile_file)[0] == 0
    profile = load_profile_file(profile_file)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("accounts.toml", ACCOUNTS),
        ("taxonomy.toml", TAXONOMY),
        ("rules.toml", RULES),
    ):
        profile.input_file(name).write_text(content, encoding="utf-8")
    import_export(profile, "danske-20260303.csv", RUN_1_ROWS, date(2026, 3, 2))
    return Lifecycle(profile_file, profile)


def import_run_2(profile: Profile) -> None:
    """Import run-2, whose export carries the late booking F."""
    import_export(profile, "danske-20260310.csv", RUN_2_ROWS, date(2026, 3, 9))


def transaction_id(profile: Profile, description: str) -> str:
    """The Silver identity of the one transaction with this description."""
    with SilverStore(profile) as silver:
        (found,) = {
            each.transaction_id
            for each in silver.read().transactions
            if each.description == description
        }
    return found


def february_by_category(publication: GoldRepository) -> Mapping[str, Decimal]:
    """The February allocations of one publication, summed by category."""
    totals: dict[str, Decimal] = {}
    for allocation in publication.category_allocations(
        start_date=FEBRUARY[0], end_date=FEBRUARY[1]
    ):
        totals[allocation.category_id] = (
            totals.get(allocation.category_id, Decimal(0)) + allocation.amount
        )
    return totals


def at_second_publication(folder: Path) -> Lifecycle:
    """Publish P1 from run-1, then P2 once run-2 brings the late booking."""
    household = lifecycle(folder)
    assert rebuild(household.profile_file)[0] == 0
    import_run_2(household.profile)
    assert rebuild(household.profile_file)[0] == 0
    return household


def correct_ikea_to_gifts(profile: Profile) -> None:
    """Log decision 1: the IKEA purchase was a gift, not household goods."""
    entry = {
        "format": 1,
        "entry": 1,
        "decision_id": "d-0001",
        "recorded_at": "2026-04-10T17:02:11Z",
        "kind": "classify",
        "targets": [transaction_id(profile, "IKEA 551")],
        "category": "gifts",
        "reason": "A present, not furniture",
        "supersedes": [],
    }
    profile.input_file("decisions.jsonl").write_text(
        json.dumps(entry) + "\n", encoding="utf-8"
    )
