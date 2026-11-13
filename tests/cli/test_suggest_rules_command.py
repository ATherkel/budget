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
CURRENT = "joint-current"
SAVINGS = "joint-savings"

type Labels = tuple[str | None, str | None]


def _transaction(
    number: int,
    labels: Labels,
    amount: str = "-100.00",
    *,
    account_id: str = CURRENT,
    currency: str = "DKK",
) -> Transaction:
    """One booked synthetic transaction carrying the given bank labels."""
    category, subcategory = labels
    return Transaction(
        transaction_id=f"{number:064x}",
        account_id=account_id,
        transaction_date=date(2026, 3, number),
        amount=Decimal(amount),
        currency=currency,
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


def _seeded_profile_file(
    folder: Path,
    transactions: Sequence[Transaction],
    currencies: dict[str, str] | None = None,
) -> Path:
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
            currencies=currencies or {CURRENT: "DKK", SAVINGS: "DKK"},
        )
    return profile_file


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


if __name__ == "__main__":
    unittest.main()
