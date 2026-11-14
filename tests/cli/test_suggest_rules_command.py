# Copyright 2026 Therkel
"""`budget suggest-rules`: a summary of the bank's own category labels.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. The profile holds a migrated Silver
store and a synthetic `SilverResult` written through the store's own public
`replace`; the command only reads that stored result.
"""

import tomllib
import unittest
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from budget.silver import SilverResult, SilverStore, Transaction, migrate_silver
from tests.cli.commands import check, suggest_rules
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_CONFIGURATION = 3
EXIT_REFUSED_ENVIRONMENT = 4
CURRENT = "joint-current"
SAVINGS = "joint-savings"

type Labels = tuple[str | None, str | None]


def _transaction(
    number: int,
    labels: Labels,
    amount: str = "-100.00",
    *,
    account_id: str = CURRENT,
) -> Transaction:
    """One booked synthetic transaction carrying the given bank labels."""
    category, subcategory = labels
    return Transaction(
        transaction_id=f"{number:064x}",
        account_id=account_id,
        transaction_date=date(2026, 3, number),
        amount=Decimal(amount),
        currency="DKK",
        description=f"SYNTHETIC {number}",
        source_system="danske-csv-v1",
        balance=None,
        source_status="Udført",
        booking_status="booked",
        occurrence=1,
        day_sequence=1,
        identity_version="1",
        bank_category=category,
        bank_subcategory=subcategory,
    )


def _seeded_profile_file(folder: Path, transactions: Sequence[Transaction]) -> Path:
    """Write a profile whose Silver store holds exactly `transactions`."""
    profile_file = write_profile(folder)
    profile = development_profile(folder)
    migrate_silver(profile)
    with SilverStore(profile) as store:
        store.replace(
            SilverResult(
                transactions=tuple(transactions),
                transaction_evidence=(),
                unbooked_records=(),
                balance_observations=(),
                account_evidence=(),
                evidence_exports=(),
                import_run_results=(),
                review_items=(),
            ),
            currencies={CURRENT: "DKK", SAVINGS: "DKK"},
        )
    return profile_file


def _write_rules(folder: Path, text: str) -> None:
    """Write the profile's `rules.toml`, the only input file the command reads."""
    inputs = folder / "inputs"
    inputs.mkdir(exist_ok=True)
    (inputs / "rules.toml").write_text(text, encoding="utf-8")


def _check_with_drafts(folder: Path, drafts: Path) -> tuple[int, str, str]:
    """Run `budget check` on a fresh profile whose taxonomy and rules are the drafts.

    The household copies the drafts in as they are; only `accounts.toml`
    comes from elsewhere, since the drafts never declare accounts.
    """
    folder.mkdir()
    profile_file = write_profile(folder)
    profile = development_profile(folder)
    write_inputs(profile)
    for name in ("taxonomy", "rules"):
        draft = (drafts / f"{name}-draft.toml").read_bytes()
        profile.input_file(f"{name}.toml").write_bytes(draft)
    return check(profile_file)


def _draft_rules(drafts: Path) -> list[dict[str, object]]:
    """The rules in `rules-draft.toml`, as TOML reads them."""
    text = (drafts / "rules-draft.toml").read_text(encoding="utf-8")
    return cast("list[dict[str, object]]", tomllib.loads(text)["rule"])


def _line_above(drafts: Path, line: str) -> str:
    """The line right above `line` in `taxonomy-draft.toml`."""
    lines = (drafts / "taxonomy-draft.toml").read_text(encoding="utf-8").splitlines()
    return lines[lines.index(line) - 1]


def _columns(stdout: str, count: int) -> list[list[str]]:
    """The first `count` two-space-separated columns of each output line."""
    return [line.split("  ")[:count] for line in stdout.splitlines()]


class SuggestRulesSummaryTests(unittest.TestCase):
    def test_each_bank_category_pair_is_one_line_with_its_transaction_count(
        self,
    ) -> None:
        # Interleaved across accounts, so a pair is counted over all of Silver;
        # a missing subcategory is a pair of its own, listed after the named ones.
        transactions = (
            _transaction(1, ("Indkomst", "Løn"), "25000.00"),
            _transaction(2, ("Bolig", "Husleje")),
            _transaction(3, ("Bolig", None), account_id=SAVINGS),
            _transaction(4, ("Bolig", "Husleje"), account_id=SAVINGS),
        )
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), transactions)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert _columns(stdout, 2) == [
            ["Bolig / Husleje", "2 transactions"],
            ["Bolig / (none)", "1 transaction"],
            ["Indkomst / Løn", "1 transaction"],
        ]

    def test_each_pair_shows_the_signed_sum_of_its_amounts(self) -> None:
        # A refund inside the hotel pair nets against its purchases, so a sum
        # of absolute amounts or of the expenses alone would read differently.
        # DKK is the only currency Silver accepts today (ADR-013).
        transactions = (
            _transaction(1, ("Bolig", "Husleje"), "-1200.00"),
            _transaction(2, ("Bolig", "Husleje"), "-100.00"),
            _transaction(3, ("Rejser", "Hotel"), "-500.50", account_id=SAVINGS),
            _transaction(4, ("Rejser", "Hotel"), "50.00"),
        )
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), transactions)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert _columns(stdout, 3) == [
            ["Bolig / Husleje", "2 transactions", "-1300.00 DKK"],
            ["Rejser / Hotel", "2 transactions", "-450.50 DKK"],
        ]

    def test_transactions_without_a_bank_category_are_one_line_after_the_pairs(
        self,
    ) -> None:
        # An export with no category column, and a stray subcategory with no
        # category, both leave nothing a bank-category rule could match.
        transactions = (
            _transaction(1, (None, None)),
            _transaction(2, ("Bolig", "Husleje")),
            _transaction(3, (None, "Husleje"), account_id=SAVINGS),
            _transaction(4, (None, None), account_id=SAVINGS),
        )
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), transactions)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert stdout.splitlines() == [
            "Bolig / Husleje  1 transaction  -100.00 DKK",
            "No bank category  3 transactions",
        ]

    def test_spellings_that_differ_only_in_case_are_one_pair(self) -> None:
        # Gold matches a label without its case, so these are one pair. It
        # shows the most-used spelling, a tie going to the one that sorts
        # first ("MAD" before "Mad"), and names the others after it.
        transactions = (
            _transaction(1, ("Bolig", "Husleje")),
            _transaction(2, ("BOLIG", "husleje")),
            _transaction(3, ("Bolig", "Husleje"), account_id=SAVINGS),
            _transaction(4, ("Mad", None)),
            _transaction(5, ("MAD", None)),
        )
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), transactions)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert stdout.splitlines() == [
            "Bolig / Husleje (also BOLIG / husleje)  3 transactions  -300.00 DKK",
            "MAD / (none) (also Mad / (none))  2 transactions  -200.00 DKK",
        ]

    def test_control_characters_in_a_bank_label_are_escaped(self) -> None:
        # The bank wrote the label, so it is shown as `review` shows it:
        # an escape or bell character never reaches the terminal as itself.
        transactions = (_transaction(1, ("Bolig\x1b[2J", "Leje\x07")),)
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), transactions)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert stdout.splitlines() == [
            r"Bolig\x1b[2J / Leje\x07  1 transaction  -100.00 DKK"
        ]

    def test_silver_with_no_transactions_says_so(self) -> None:
        # Built but empty, as after importing nothing: an empty summary would
        # read as "the bank labels nothing".
        with TemporaryDirectory() as directory:
            profile_file = _seeded_profile_file(Path(directory), ())

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert stdout == "No transactions in Silver\n"

    def test_silver_that_was_never_built_is_refused_with_how_to_build_it(
        self,
    ) -> None:
        # An empty summary would read as "the bank labels nothing".
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            migrate_silver(development_profile(folder))

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
        assert stderr.startswith("budget: Silver has not been built")
        assert "run `budget rebuild --from silver`" in stderr

    def test_a_pair_a_bank_category_rule_already_matches_names_that_rule(
        self,
    ) -> None:
        # Only a rule that tests nothing but the bank's labels covers a pair.
        # A category-only rule covers each of its subcategories, in any case,
        # as Gold matches it; a rule with any further condition covers none.
        transactions = (
            _transaction(1, ("Bolig", "Husleje")),
            _transaction(2, ("Bolig", None)),
            _transaction(3, ("Mad", "Dagligvarer")),
            _transaction(4, ("Rejser", "Hotel")),
            _transaction(5, ("Rejser", None)),
        )
        rules = """format = 1

[[rule]]
id = "r-rent"
priority = -10
when.bank_category = "Bolig"
when.bank_subcategory = "Husleje"
then.category = "rent"

[[rule]]
id = "r-groceries-current"
priority = -10
when.bank_category = "Mad"
when.account = "joint-current"
then.category = "groceries"

[[rule]]
id = "r-travel"
priority = -20
when.bank_category = "rejser"
then.category = "travel"
"""
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)
            _write_rules(folder, rules)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stderr) == (EXIT_OK, "")
        assert stdout.splitlines() == [
            "Bolig / Husleje  1 transaction  -100.00 DKK  covered by r-rent",
            "Bolig / (none)  1 transaction  -100.00 DKK",
            "Mad / Dagligvarer  1 transaction  -100.00 DKK",
            "Rejser / Hotel  1 transaction  -100.00 DKK  covered by r-travel",
            "Rejser / (none)  1 transaction  -100.00 DKK  covered by r-travel",
        ]

    def test_an_invalid_rules_file_is_refused_before_anything_is_printed(
        self,
    ) -> None:
        # A half-printed summary would flag pairs against rules Gold refuses.
        rules = """format = 1

[[rule]]
id = ""
when.bank_category = "Bolig"
then.category = "rent"
"""
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(
                folder, (_transaction(1, ("Bolig", "Husleje")),)
            )
            _write_rules(folder, rules)

            status, stdout, stderr = suggest_rules(profile_file)

        assert (status, stdout) == (EXIT_REFUSED_CONFIGURATION, "")
        assert stderr.startswith("budget: rules.toml: rule 1: id must be")


class SuggestRulesDraftTests(unittest.TestCase):
    def test_out_writes_drafts_that_check_accepts_as_written(self) -> None:
        # The subcategory rules outrank the category-only rule, so the specific
        # label wins wherever both match; a missing folder is created.
        transactions = (
            _transaction(1, ("Housing", "Rent")),
            _transaction(2, ("Housing", None)),
            _transaction(3, ("Income", "Salary"), "25000.00"),
        )
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)
            out = folder / "drafts" / "first"

            status, stdout, stderr = suggest_rules(profile_file, "--out", str(out))

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines()[-1] == (
                f"Wrote taxonomy-draft.toml and rules-draft.toml to {out}"
            )
            assert _check_with_drafts(folder / "check", out) == (
                EXIT_OK,
                "No problems found.\n",
                "",
            )
            assert _draft_rules(out) == [
                {
                    "id": "r-bank-housing-rent",
                    "priority": -10,
                    "when": {"bank_category": "Housing", "bank_subcategory": "Rent"},
                    "then": {"category": "housing-rent"},
                },
                {
                    "id": "r-bank-housing-other",
                    "priority": -20,
                    "when": {"bank_category": "Housing"},
                    "then": {"category": "housing-other"},
                },
                {
                    "id": "r-bank-income-salary",
                    "priority": -10,
                    "when": {"bank_category": "Income", "bank_subcategory": "Salary"},
                    "then": {"category": "income-salary"},
                },
            ]

    def test_each_draft_category_says_how_many_transactions_and_how_much(
        self,
    ) -> None:
        # The comment sits right above the category it describes, so the
        # household can tell a large pair from a stray one while editing.
        transactions = (
            _transaction(1, ("Housing", "Rent"), "-1200.00"),
            _transaction(2, ("Housing", "Rent"), "-100.00"),
            _transaction(3, ("Income", "Salary"), "25000.00"),
        )
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)

            status, _, stderr = suggest_rules(profile_file, "--out", str(folder))

            assert (status, stderr) == (EXIT_OK, "")
            assert _line_above(folder, "[category.housing-rent]") == (
                "# 2 transactions, -1300.00 DKK"
            )
            assert _line_above(folder, "[category.income-salary]") == (
                "# 1 transaction, 25000.00 DKK"
            )

    def test_a_draft_group_is_income_only_when_its_sum_is_positive(self) -> None:
        # The guess is the group's, over all its pairs: Income's negative
        # pair does not make it an expense. A group that nets to zero is an
        # expense, the more common kind; the household confirms each.
        transactions = (
            _transaction(1, ("Housing", "Rent"), "-100.00"),
            _transaction(2, ("Housing", "Rent"), "30.00"),
            _transaction(3, ("Income", "Salary"), "25000.00"),
            _transaction(4, ("Income", None), "-500.00"),
            _transaction(5, ("Even", "Odd"), "100.00"),
            _transaction(6, ("Even", None), "-100.00"),
        )
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)

            status, _, stderr = suggest_rules(profile_file, "--out", str(folder))

            assert (status, stderr) == (EXIT_OK, "")
            text = (folder / "taxonomy-draft.toml").read_text(encoding="utf-8")
            groups = tomllib.loads(text)["group"]
            assert {group: groups[group]["direction"] for group in groups} == {
                "even": "expense",
                "housing": "expense",
                "income": "income",
            }

    def test_draft_ids_are_ascii_slugs_unique_and_never_a_transaction_type(
        self,
    ) -> None:
        # æ/ø/å spell out as Danish does, other accents drop, and anything
        # else becomes one hyphen. Two labels with one slug get a suffix, and
        # a slug naming a type that carries no category is never used.
        transactions = (
            _transaction(1, ("Bolig og Ældre", "Fødsel & Børn")),
            _transaction(2, ("Café", "Mad & Drikke")),
            _transaction(3, ("Café", "Mad/Drikke")),
            _transaction(4, ("Transfer", None)),
        )
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)

            status, _, stderr = suggest_rules(profile_file, "--out", str(folder))

            assert (status, stderr) == (EXIT_OK, "")
            text = (folder / "taxonomy-draft.toml").read_text(encoding="utf-8")
            taxonomy = tomllib.loads(text)
            assert list(taxonomy["group"]) == ["bolig-og-aeldre", "cafe", "transfer-2"]
            assert list(taxonomy["category"]) == [
                "bolig-og-aeldre-foedsel-boern",
                "cafe-mad-drikke",
                "cafe-mad-drikke-2",
                "transfer-2-other",
            ]
            assert [rule["id"] for rule in _draft_rules(folder)] == [
                "r-bank-bolig-og-aeldre-foedsel-boern",
                "r-bank-cafe-mad-drikke",
                "r-bank-cafe-mad-drikke-2",
                "r-bank-transfer-2-other",
            ]

    def test_pairs_whose_categories_differ_only_in_case_share_one_draft_group(
        self,
    ) -> None:
        # Each pair keeps its own most-used spelling, so the bank category is
        # "Bolig" in one and "BOLIG" in the other. Gold matches both as one
        # label, so they are one group, named by its most-used spelling.
        transactions = (
            _transaction(1, ("Bolig", "Husleje")),
            _transaction(2, ("Bolig", "Husleje")),
            _transaction(3, ("BOLIG", None), "50.00"),
        )
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)

            status, _, stderr = suggest_rules(profile_file, "--out", str(folder))

            assert (status, stderr) == (EXIT_OK, "")
            text = (folder / "taxonomy-draft.toml").read_text(encoding="utf-8")
            taxonomy = tomllib.loads(text)
            assert taxonomy["group"] == {
                "bolig": {"name": "Bolig", "direction": "expense"}
            }
            assert {
                category_id: category["group"]
                for category_id, category in taxonomy["category"].items()
            } == {"bolig-husleje": "bolig", "bolig-other": "bolig"}

    def test_labels_with_quotes_backslashes_and_control_characters_read_back_exact(
        self,
    ) -> None:
        # The bank writes the labels, so the drafts must quote any character
        # TOML gives a meaning to or refuses raw, DEL included.
        category, subcategory = 'Mad "&" Drikke\\', "Leje\x1b[2J\x07\x7f"
        transactions = (_transaction(1, (category, subcategory)),)
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)

            status, _, stderr = suggest_rules(profile_file, "--out", str(folder))

            assert (status, stderr) == (EXIT_OK, "")
            assert [rule["when"] for rule in _draft_rules(folder)] == [
                {"bank_category": category, "bank_subcategory": subcategory}
            ]

    def test_a_covered_pair_is_drafted_commented_out_under_the_rule_covering_it(
        self,
    ) -> None:
        # Flagged, not skipped: the household sees the pair, but pasting the
        # drafts adds nothing live for it. A group whose every pair is
        # covered is commented out too, so no group is left empty.
        transactions = (
            _transaction(1, ("Bolig", "Husleje")),
            _transaction(2, ("Bolig", None)),
            _transaction(3, ("Rejser", "Hotel")),
            _transaction(4, ("Rejser", None)),
        )
        rules = """format = 1

[[rule]]
id = "r-rent"
when.bank_category = "Bolig"
when.bank_subcategory = "Husleje"
then.category = "rent"

[[rule]]
id = "r-travel"
when.bank_category = "Rejser"
then.category = "travel"
"""
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)
            _write_rules(folder, rules)
            out = folder / "drafts"

            status, _, stderr = suggest_rules(profile_file, "--out", str(out))

            assert (status, stderr) == (EXIT_OK, "")
            taxonomy_text = (out / "taxonomy-draft.toml").read_text(encoding="utf-8")
            rules_text = (out / "rules-draft.toml").read_text(encoding="utf-8")
            taxonomy = tomllib.loads(taxonomy_text)
            assert (list(taxonomy["group"]), list(taxonomy["category"])) == (
                ["bolig"],
                ["bolig-other"],
            )
            assert [rule["id"] for rule in _draft_rules(out)] == ["r-bank-bolig-other"]
            assert '# covered by r-rent\n# [[rule]]\n# id = "r-bank-bolig-husleje"' in (
                rules_text
            )
            assert "# covered by r-rent\n# [category.bolig-husleje]" in taxonomy_text
            assert "# covered by r-travel\n# [group.rejser]" in taxonomy_text
            assert _check_with_drafts(folder / "check", out) == (
                EXIT_OK,
                "No problems found.\n",
                "",
            )

    def test_an_existing_draft_file_is_refused_and_nothing_is_written(
        self,
    ) -> None:
        # A rerun must never lose the household's edits to an earlier draft.
        # Both files are checked first, so the missing one is not written
        # either. The refusal names only the file that exists.
        transactions = (_transaction(1, ("Bolig", "Husleje")),)
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)
            out = folder / "drafts"
            out.mkdir()
            edited = out / "rules-draft.toml"
            edited.write_text("# the household's edits\n", encoding="utf-8")

            status, stdout, stderr = suggest_rules(profile_file, "--out", str(out))

            assert (status, stdout) == (EXIT_REFUSED_CONFIGURATION, "")
            assert stderr.startswith(f"budget: {edited} already exists")
            assert "taxonomy-draft.toml" not in stderr
            assert sorted(path.name for path in out.iterdir()) == ["rules-draft.toml"]
            assert edited.read_text(encoding="utf-8") == "# the household's edits\n"

    def test_an_out_folder_inside_the_inputs_folder_is_refused(self) -> None:
        # Drafts never go into inputs, where they would sit beside the real
        # files. The folder is judged once resolved, so `..` cannot reach it.
        transactions = (_transaction(1, ("Bolig", "Husleje")),)
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = _seeded_profile_file(folder, transactions)
            (folder / "inputs").mkdir()
            out = folder / "elsewhere" / ".." / "inputs" / "drafts"

            status, stdout, stderr = suggest_rules(profile_file, "--out", str(out))

            assert (status, stdout) == (EXIT_REFUSED_CONFIGURATION, "")
            assert stderr.startswith("budget: drafts are never written into ")
            assert list((folder / "inputs").iterdir()) == []


if __name__ == "__main__":
    unittest.main()
