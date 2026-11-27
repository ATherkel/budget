# Copyright 2026 Therkel
"""`budget sort` sorts the current publication's unknowns, one group at a time.

The household is synthetic: one imported export per account, built through
Silver and published to Gold, with an empty taxonomy and no rules. Every
account, text and amount is invented.
"""

import tempfile
import tomllib
import unittest
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import load_profile_file
from budget.rebuilding import rebuild_from_gold, rebuild_from_silver
from tests.cli.commands import check, sort
from tests.cli.imports import clean_checkout, clean_git
from tests.cli.pipelines import TAXONOMY, prepared
from tests.importing.households import drop

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
_NOW = datetime(2026, 4, 1, tzinfo=UTC)
# The question after each group, which stdout holds without the answer typed.
_ASKED = (
    "[t] transfer  [n] new category  [s] skip  [m] months  [?] category list  "
    "[q] quit  or type a word to search: "
)
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
# The bank's own labels: most groceries say supermarket, one says baker.
LABELS: dict[str, tuple[str, str]] = {
    "NETTO 1234 KBH": ("Dagligvarer", "Supermarked"),
    "NETTO 5678 KBH": ("Dagligvarer", "Supermarked"),
    "Netto 91 KBH": ("Dagligvarer", "Bager"),
    "NETTO 2 KBH": ("Dagligvarer", "Supermarked"),
    # The bank's own label for "no category".
    "Fra lønkonto": ("Ukategoriseret", "Ukategoriseret"),
}


def _export(rows: Sequence[Row], opening: int) -> bytes:
    """A `danske-csv-v1` export of `rows`, in date order, with chained balances."""
    lines = [_HEADER]
    balance = opening * 100
    for dato, text, amount in sorted(rows, key=lambda row: row[0][:2]):
        balance += int(amount.replace(",", ""))
        saldo = f"{balance // 100},{balance % 100:02d}"
        category, subcategory = LABELS.get(text, ("", ""))
        lines.append(
            f'"{dato}","{category}","{subcategory}","{text}","{amount}","{saldo}",'
            '"Udført","Nej"'
        )
    return "\r\n".join(lines).encode("cp1252")


def _sortable(folder: Path, *, name: str = "development") -> Path:
    """Publish the household's March with nothing classified; return its profile."""
    base = prepared(folder, name=name)
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
                '"netto kbh": 4 transactions, -200.00 DKK in total',
                "Your answer applies to all 4, and to future ones with this text.",
                "For example:",
                "  2026-03-02  joint-current  -45.00  NETTO 1234 KBH",
                "  2026-03-05  joint-current  -55.00  NETTO 5678 KBH",
                "  2026-03-09  joint-current  -60.00  Netto 91 KBH",
            ]

    def test_skipping_shows_each_next_group_until_none_is_left(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            status, stdout, stderr = sort(profile_file, "s\ns\ns\ns\n")

            assert (status, stderr) == (EXIT_OK, "")
            blocks = [block.splitlines() for block in stdout.split("\n\n")]
            assert [block[0] for block in blocks] == [
                '"netto kbh": 4 transactions, -200.00 DKK in total',
                _ASKED + '"fra lønkonto": 1 transaction, 500.00 DKK in total',
                _ASKED + '"løn marts": 1 transaction, 20,000.00 DKK in total',
                _ASKED + '"til opsparing": 1 transaction, -500.00 DKK in total',
                _ASKED + "No group is left to sort.",
            ]
            assert blocks[1][1] == (
                "Your answer applies to this one, and to future ones with this text."
            )


class SortingEverythingTests(unittest.TestCase):
    def test_a_session_from_blank_inputs_leaves_nothing_unknown_and_passes_check(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            answers = [
                *("n", "Dagligvarer", "Mad", ""),  # netto kbh, a new group
                "t",  # fra lønkonto
                *("n", "Løn", "Indkomst", ""),  # løn marts, offered income
                "t",  # til opsparing, the other leg
            ]

            status, stdout, stderr = sort(profile_file, "\n".join(answers) + "\n")

            assert (status, stderr) == (EXIT_OK, "")
            assert set(_types(profile_file).values()) == {
                "expense",
                "income",
                "transfer",
            }
            assert stdout.endswith("No group is left to sort.\n")
            assert check(profile_file) == (EXIT_OK, "No problems found.\n", "")


class ProductionTests(unittest.TestCase):
    def test_each_published_answer_writes_a_backup_set(self) -> None:
        with (
            TemporaryDirectory() as directory,
            mock.patch("subprocess.run", side_effect=clean_checkout),
        ):
            profile_file = _sortable(Path(directory), name="production")
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            status, stdout, stderr = sort(profile_file, "groceries\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            totals = stdout.split("\n\n")[1].splitlines()
            assert totals[0].startswith(_ASKED + "Backup   backup set ")
            assert totals[0].endswith(" written")

    def test_uncommitted_code_is_refused_before_anything_is_asked(self) -> None:
        with TemporaryDirectory() as directory:
            with mock.patch("subprocess.run", side_effect=clean_checkout):
                profile_file = _sortable(Path(directory), name="production")
            dirty = clean_git()
            dirty.stdout = " M src/budget/sorting.py\n"

            with mock.patch("subprocess.run", return_value=dirty):
                status, stdout, stderr = sort(profile_file, "groceries\nq\n")

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "uncommitted" in stderr


class QuittingTests(unittest.TestCase):
    def test_input_ending_quits_and_keeps_every_rule_written(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            # No `q`: the input ends at the next question.
            status, _, stderr = sort(profile_file, "groceries\n")

            assert (status, stderr) == (EXIT_OK, "")
            assert _types(profile_file)["NETTO 2 KBH"] == "expense"


TWO_GROUPS = """\
format = 1

[group.food]
name = "Food"
direction = "expense"

[group.home]
name = "Home"
direction = "expense"

[category.groceries]
name = "Groceries"
group = "food"

[category.rent]
name = "Rent"
group = "home"

[category.eating-out]
name = "Eating out"
group = "food"
"""


class CategoryListTests(unittest.TestCase):
    def test_a_group_lists_no_category_unless_asked(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TWO_GROUPS)

            _, stdout, _ = sort(profile_file, "q\n")

            # The group's own lines end with its examples: no category follows.
            assert stdout.split("\n\n")[0].splitlines()[-1] == (
                "  2026-03-09  joint-current  -60.00  Netto 91 KBH"
            )

    def test_a_question_mark_opens_the_category_list_in_the_default_app(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TWO_GROUPS)
            opened: list[str] = []

            # The default app is the system boundary: record what it is given.
            with (
                mock.patch.object(tempfile, "tempdir", directory),
                mock.patch(
                    "budget.sorting.open_in_default_app",
                    side_effect=lambda path: opened.append(
                        path.read_text(encoding="utf-8")
                    ),
                ),
            ):
                _, stdout, _ = sort(profile_file, "?\nq\n")

            listed = (
                "# Categories\n"
                "\n## Food\n\n- Groceries (groceries)\n- Eating out (eating-out)\n"
                "\n## Home\n\n- Rent (rent)\n"
            )
            assert opened == [listed]
            assert stdout.split("\n\n")[1].splitlines() == [
                _ASKED + "Opened the category list in your editor. "
                "Type a word to search, or an id."
            ]

    def test_with_no_category_yet_a_question_mark_says_to_add_one(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            _, stdout, _ = sort(profile_file, "?\nq\n")

            listed = stdout.split("\n\n")[1].splitlines()
            assert listed == [_ASKED + "No categories yet: type n to add one"]

    def test_a_word_lists_the_matching_categories_and_a_number_picks_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TWO_GROUPS)

            # "r" is in groceries and rent, not in eating out.
            status, stdout, stderr = sort(profile_file, "r\n2\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.split("\n\n")[1].splitlines() == [
                _ASKED + 'Matches for "r":',
                "  1 Groceries (groceries)",
                "  2 Rent (rent)",
            ]
            rules = tomllib.loads(
                load_profile_file(profile_file)
                .input_file("rules.toml")
                .read_text(encoding="utf-8")
            )
            assert [rule["then"] for rule in rules["rule"]] == [{"category": "rent"}]

    def test_a_search_shows_at_most_eight_matches(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            tables = "".join(
                f'\n[category.kind-{n}]\nname = "Kind {n}"\ngroup = "home"\n'
                for n in range(1, 11)
            )
            _write_input(
                profile_file,
                "taxonomy.toml",
                'format = 1\n\n[group.home]\nname = "Home"\ndirection = "expense"\n'
                + tables,
            )

            _, stdout, _ = sort(profile_file, "kind\nq\n")

            listed = stdout.split("\n\n")[1].splitlines()
            assert listed[1:] == [
                *(f"  {n} Kind {n} (kind-{n})" for n in range(1, 9)),
                "  and 2 more: type more of the word",
            ]

    def test_a_word_no_category_matches_says_so_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            rules = load_profile_file(profile_file).input_file("rules.toml")
            before = rules.read_bytes()

            _, stdout, _ = sort(profile_file, "groceries\nq\n")

            assert rules.read_bytes() == before
            assert stdout.split("\n\n")[1].splitlines() == [
                _ASKED + 'No category matches "groceries".'
            ]


BANK_NAMED = """\
format = 1

[group.dagligvarer]
name = "Dagligvarer"
direction = "expense"

[category.dagligvarer-bager]
name = "Bager"
group = "dagligvarer"

[category.dagligvarer-supermarked]
name = "Supermarked"
group = "dagligvarer"
"""


class SuggestionTests(unittest.TestCase):
    def test_the_category_named_for_the_commonest_bank_label_is_suggested(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", BANK_NAMED)

            _, stdout, _ = sort(profile_file, "q\n")

            first = stdout.split("\n\n")[0].splitlines()
            assert first[-1] == "Suggested: Supermarked (Dagligvarer / Supermarked)"
            assert stdout.split("\n\n")[1].startswith("[Enter] Supermarked  " + _ASKED)

    def test_the_banks_uncategorised_label_suggests_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(
                profile_file,
                "taxonomy.toml",
                BANK_NAMED + "\n[category.ukategoriseret-ukategoriseret]\n"
                'name = "Ukategoriseret"\ngroup = "dagligvarer"\n',
            )

            # Skip the groceries; the transfer leg carries the bank's label.
            _, stdout, _ = sort(profile_file, "s\nq\n")

            leg = stdout.split("\n\n")[1].splitlines()
            assert leg[0].endswith('"fra lønkonto": 1 transaction, 500.00 DKK in total')
            assert not any(line.startswith("Suggested:") for line in leg)

    def test_enter_accepts_the_suggestion(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", BANK_NAMED)

            sort(profile_file, "\nq\n")

            rules = tomllib.loads(
                load_profile_file(profile_file)
                .input_file("rules.toml")
                .read_text(encoding="utf-8")
            )
            assert [rule["then"] for rule in rules["rule"]] == [
                {"category": "dagligvarer-supermarked"}
            ]


class RefusedAnswerTests(unittest.TestCase):
    def test_an_answer_check_refuses_writes_nothing_and_asks_again(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            rules = load_profile_file(profile_file).input_file("rules.toml")
            before = rules.read_bytes()

            # A category in a group the taxonomy lacks: `check` refuses it all.
            _write_input(
                profile_file,
                "taxonomy.toml",
                'format = 1\n\n[category.groceries]\nname = "Groceries"\n'
                'group = "food"\n',
            )

            status, stdout, stderr = sort(profile_file, "t\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            assert rules.read_bytes() == before
            blocks = stdout.split("\n\n")
            assert "food" in blocks[1]
            assert "Nothing was written." in blocks[1]
            assert blocks[2].splitlines()[0].startswith('"netto kbh": ')


class MonthTableTests(unittest.TestCase):
    def test_m_shows_each_month_in_columns_with_unknown_in_and_out(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            _, stdout, _ = sort(profile_file, "groceries\nm\nq\n")

            lines = stdout.splitlines()
            start = next(i for i, line in enumerate(lines) if "Month  " in line)
            assert lines[start : start + 2] == [
                _ASKED
                + "Month    Currency    In      Out  Transfer  Unknown in  Unknown out",
                "2026-03  DKK       0.00  -200.00      0.00    20500.00      -500.00",
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


class UnpairedTransferTests(unittest.TestCase):
    def test_a_claimed_group_left_unpaired_is_not_asked_again_and_is_counted(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            # No other account holds a leg the groceries could pair with.
            status, stdout, stderr = sort(profile_file, "t\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            blocks = stdout.split("\n\n")
            assert blocks[2].splitlines()[0].startswith('"fra lønkonto": ')
            assert stdout.endswith(
                "4 transactions are marked as transfer but not paired yet: run "
                "budget review --kind unmatched-transfer (or ambiguous-transfer) "
                "to see why.\n"
            )


class RuleIdTests(unittest.TestCase):
    def test_a_rule_id_already_taken_gets_a_suffix(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)
            # A hand-written rule already holds the ID; it matches nothing here.
            _write_input(
                profile_file,
                "rules.toml",
                'format = 1\n\n[[rule]]\nid = "r-sort-netto-kbh"\n'
                'when.description_contains = "no such shop"\n'
                'then.category = "groceries"\n',
            )

            status, _, stderr = sort(profile_file, "groceries\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            rules = tomllib.loads(
                load_profile_file(profile_file)
                .input_file("rules.toml")
                .read_text(encoding="utf-8")
            )
            assert [rule["id"] for rule in rules["rule"]] == [
                "r-sort-netto-kbh",
                "r-sort-netto-kbh-2",
            ]
            assert _types(profile_file)["NETTO 1234 KBH"] == "expense"


class AnsweringANewCategoryTests(unittest.TestCase):
    def test_a_new_category_in_a_new_group_is_added_and_classifies_the_group(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))

            # Name, then a group not yet in the taxonomy, then Enter for the
            # direction the group's negative sum suggests.
            status, _, stderr = sort(profile_file, "n\nDagligvarer\nMad\n\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            taxonomy = tomllib.loads(
                load_profile_file(profile_file)
                .input_file("taxonomy.toml")
                .read_text(encoding="utf-8")
            )
            assert taxonomy == {
                "format": 1,
                "group": {"mad": {"name": "Mad", "direction": "expense"}},
                "category": {"dagligvarer": {"name": "Dagligvarer", "group": "mad"}},
            }
            assert _types(profile_file)["NETTO 1234 KBH"] == "expense"


class AnsweringANewCategoryInAnExistingGroupTests(unittest.TestCase):
    def test_n_into_an_existing_group_typed_by_its_name_adds_no_group(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(
                profile_file,
                "taxonomy.toml",
                TWO_GROUPS.replace('name = "Food"', 'name = "Mad"'),
            )

            # The group's ID is "food"; the person types its name, in any case.
            status, _, stderr = sort(profile_file, "n\nSnacks\nmAD\nq\n")

            assert (status, stderr) == (EXIT_OK, "")
            taxonomy = tomllib.loads(
                load_profile_file(profile_file)
                .input_file("taxonomy.toml")
                .read_text(encoding="utf-8")
            )
            assert list(taxonomy["group"]) == ["food", "home"]
            assert taxonomy["category"]["snacks"] == {"name": "Snacks", "group": "food"}


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

    def test_each_answer_shows_one_progress_line_with_unknown_in_and_out(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _sortable(Path(directory))
            _write_input(profile_file, "taxonomy.toml", TAXONOMY)

            _, stdout, _ = sort(profile_file, "groceries\nq\n")

            # 4 of the 7 are groceries; the salary and both transfer legs are
            # left, 20000.00 + 500.00 in and 500.00 out, never netted.
            progress = stdout.split("\n\n")[1].splitlines()
            assert progress == [
                _ASKED + "Sorted 4 of 7 (57%), 3 unknown left: "
                "in 20500.00 DKK, out -500.00 DKK",
            ]
