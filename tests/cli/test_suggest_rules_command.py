# Copyright 2026 Therkel
"""`budget suggest-rules`: a summary of the bank's own category labels.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. The profile holds a migrated Silver
store and a synthetic `SilverResult` written through the store's own public
`replace`; the command only reads that stored result.
"""

import unittest
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.silver import SilverResult, SilverStore, Transaction, migrate_silver
from tests.cli.commands import suggest_rules
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
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


if __name__ == "__main__":
    unittest.main()
