# Copyright 2026 Therkel
"""`budget sort` sorts the current publication's unknowns, one group at a time.

The household is synthetic: one imported export per account, built through
Silver and published to Gold, with an empty taxonomy and no rules. Every
account, text and amount is invented.
"""

import unittest
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import load_profile_file
from budget.rebuilding import rebuild_from_gold, rebuild_from_silver
from tests.cli.commands import sort
from tests.cli.pipelines import TAXONOMY, prepared
from tests.importing.households import drop

EXIT_OK = 0
_NOW = datetime(2026, 4, 1, tzinfo=UTC)
# The question after each group, which stdout holds without the answer typed.
_ASKED = "Category, t (transfer), n (new category), s (skip) or q (quit): "
_HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'

type Row = tuple[str, str, str]

CURRENT_ROWS: tuple[Row, ...] = (
    ("02.03.2026", "NETTO 1234 KBH", "-45,00"),
    ("05.03.2026", "NETTO 5678 KBH", "-55,00"),
    ("09.03.2026", "Netto 91 KBH", "-60,00"),
    ("12.03.2026", "NETTO 2 KBH", "-40,00"),
    ("06.03.2026", "Til opsparing", "-500,00"),
    ("10.03.2026", "Løn marts 2026", "20000,00"),
)
SAVINGS_ROWS: tuple[Row, ...] = (("06.03.2026", "Fra lønkonto", "500,00"),)


def _export(rows: Sequence[Row], opening: int) -> bytes:
    """A `danske-csv-v1` export of `rows`, in date order, with chained balances."""
    lines = [_HEADER]
    balance = opening * 100
    for dato, text, amount in sorted(rows, key=lambda row: row[0][:2]):
        balance += int(amount.replace(",", ""))
        saldo = f"{balance // 100},{balance % 100:02d}"
        lines.append(f'"{dato}","","","{text}","{amount}","{saldo}","Udført","Nej"')
    return "\r\n".join(lines).encode("cp1252")


def _sortable(folder: Path) -> Path:
    """Publish the household's March with nothing classified; return its profile."""
    base = prepared(folder)
    profile = base.profile
    profile.input_file("taxonomy.toml").write_text("format = 1\n", encoding="utf-8")
    exports = (
        ("joint-current", _export(CURRENT_ROWS, 1000)),
        ("joint-savings", _export(SAVINGS_ROWS, 0)),
    )
    sources = [
        drop(profile, account, "danske-20260331.csv", content)
        for account, content in exports
    ]
    with writer_lock(profile) as lock:
        for source in sources:
            import_inbox_file(
                lock, source, Coverage(date(2026, 3, 1), date(2026, 3, 31))
            )
        rebuild_from_silver(lock)
        rebuild_from_gold(lock, now=_NOW)
    return base.profile_file


def _types(profile_file: Path) -> dict[str, str]:
    """Each published description's transaction type, in the current publication."""
    profile = load_profile_file(profile_file)
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
        assert current is not None
        gold = store.open(current.publication_id)
        transactions = gold.transactions(
            start_date=date.min, end_date=date.max, account_ids=None
        )
    return {each.description: each.transaction_type for each in transactions}


def _write_input(profile_file: Path, name: str, text: str) -> None:
    """Replace one of the household's input files."""
    load_profile_file(profile_file).input_file(name).write_text(text, encoding="utf-8")


class ShowingAGroupTests(unittest.TestCase):
    def test_the_biggest_group_comes_first_with_its_count_sum_and_three_examples(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            status, stdout, stderr = sort(profile_file, "q\n")

            assert (status, stderr) == (EXIT_OK, "")
            first = stdout.split("\n\n")[0].splitlines()
            assert first == [
                "netto kbh",
                "  4 transactions, -200.00 DKK",
                "  2026-03-02  joint-current  -45.00  NETTO 1234 KBH",
                "  2026-03-05  joint-current  -55.00  NETTO 5678 KBH",
                "  2026-03-09  joint-current  -60.00  Netto 91 KBH",
            ]

    def test_skipping_shows_each_next_group_until_none_is_left(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            status, stdout, stderr = sort(profile_file, "s\ns\ns\ns\n")

            assert (status, stderr) == (EXIT_OK, "")
            headings = [block.splitlines()[0] for block in stdout.split("\n\n")]
            assert headings == [
                "netto kbh",
                _ASKED + "fra lønkonto",
                _ASKED + "løn marts",
                _ASKED + "til opsparing",
                _ASKED + "No group is left to sort.",
            ]


class AnsweringATransferTests(unittest.TestCase):
    def test_claiming_both_legs_publishes_them_as_one_transfer(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            # Skip the groceries and the salary; claim the two transfer legs.
            status, _, stderr = sort(profile_file, "s\nt\ns\nt\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            types = _types(profile_file)
            assert (types["Til opsparing"], types["Fra lønkonto"]) == (
                "transfer",
                "transfer",
            )


class AnsweringACategoryTests(unittest.TestCase):
    def test_a_category_id_classifies_the_whole_group_and_publishes_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            status, _, stderr = sort(profile_file, "groceries\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            assert _types(profile_file) == {
                "NETTO 1234 KBH": "expense",
                "NETTO 5678 KBH": "expense",
                "Netto 91 KBH": "expense",
                "NETTO 2 KBH": "expense",
                "Til opsparing": "unknown",
                "Løn marts 2026": "unknown",
                "Fra lønkonto": "unknown",
            }

    def test_each_answer_shows_the_month_totals_with_unknown_shrunk(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            _, stdout, _ = sort(profile_file, "groceries\nq\n")

            totals = stdout.split("\n\n")[1].splitlines()
            assert totals == [
                _ASKED + "Month totals",
                "  2026-03  in 0.00 DKK, out -200.00 DKK, transfer 0.00 DKK, "
                "unknown 20000.00 DKK (3 transactions)",
            ]
