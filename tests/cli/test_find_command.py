# Copyright 2026 Therkel
"""`budget find`: locate transaction handles in the current publication."""

import hashlib
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import migrate_bronze
from budget.gold import (
    GoldCategoryAllocation,
    GoldRecords,
    GoldResult,
    GoldTransaction,
)
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.silver import (
    SILVER_FINGERPRINT_SCHEME,
    SilverImportRun,
    SilverProvenance,
    SilverResult,
    SilverStore,
    Transaction,
    migrate_silver,
    result_fingerprint,
)
from budget.silver.identity import IDENTITY_VERSION
from tests.cli.commands import decide, find_transaction
from tests.cli.pipelines import TAXONOMY, write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import CONFIGURATION, RECIPE, publication
from tests.gold.worked_example import ACCOUNTS, CATEGORIES, CURRENT, SAVINGS

EXIT_OK = 0
CURRENT_ID = "a1b2c3d4" + "1" * 56
SAVINGS_ID = "b2c3d4e5" + "2" * 56
OTHER_ID = "c3d4e5f6" + "3" * 56
TARGET_PREFIX = "  target "


def _silver_transaction(
    transaction_id: str,
    account_id: str,
    transaction_date: date,
    amount: str,
    description: str,
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        account_id=account_id,
        transaction_date=transaction_date,
        amount=Decimal(amount),
        currency="DKK",
        description=description,
        source_system="synthetic",
        balance=None,
        source_status="booked",
        booking_status="booked",
        occurrence=1,
        day_sequence=1,
        identity_version=IDENTITY_VERSION,
        bank_category=None,
        bank_subcategory=None,
    )


def _gold_transaction(
    transaction: Transaction, *, classified: bool, sequence: int
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=transaction.transaction_id,
        account_id=transaction.account_id,
        transaction_date=transaction.transaction_date,
        account_sequence=sequence,
        amount=transaction.amount,
        description=transaction.description,
        transaction_type="expense" if classified else "unknown",
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )


def _profile_with_transactions(
    folder: Path,
    transactions: tuple[Transaction, ...],
    *,
    category_id: str = "groceries",
) -> Path:
    """Store matching public Silver and Gold results in one synthetic profile."""
    profile_file = write_profile(folder)
    profile = development_profile(folder)
    write_inputs(profile)
    profile.input_file("taxonomy.toml").write_text(TAXONOMY, encoding="utf-8")
    migrate_bronze(profile)
    migrate_silver(profile)
    currencies = {CURRENT: "DKK", SAVINGS: "DKK"}
    silver = SilverResult(
        transactions=transactions,
        transaction_evidence=(),
        unbooked_records=(),
        balance_observations=(),
        account_evidence=(),
        evidence_exports=(),
        import_run_results=(),
        review_items=(),
    )
    provenance = SilverProvenance(
        fingerprint_scheme=SILVER_FINGERPRINT_SCHEME,
        result_fingerprint=result_fingerprint(silver, currencies=currencies),
        import_runs=frozenset(
            {
                SilverImportRun("run-current", "a" * 64, CURRENT),
                SilverImportRun("run-savings", "b" * 64, SAVINGS),
            }
        ),
        currencies=currencies,
        decisions=(),
        decision_log_position=0,
        decision_log_prefix_sha256=hashlib.sha256(b"").hexdigest(),
        code_version=None,
        identity_version=IDENTITY_VERSION,
    )
    with SilverStore(profile) as store:
        store.replace(silver, currencies=currencies, provenance=provenance)

    gold_transactions = (
        _gold_transaction(transactions[0], classified=True, sequence=1),
        _gold_transaction(transactions[1], classified=False, sequence=2),
        _gold_transaction(transactions[2], classified=False, sequence=3),
    )
    allocation = GoldCategoryAllocation(
        allocation_id=f"{transactions[0].transaction_id}/{category_id}",
        transaction_id=transactions[0].transaction_id,
        account_id=CURRENT,
        transaction_date=transactions[0].transaction_date,
        category_id=category_id,
        amount=transactions[0].amount,
    )
    migrate_gold(profile)
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                publication(1),
                GoldRecords(
                    accounts=ACCOUNTS,
                    categories=CATEGORIES,
                    transactions=gold_transactions,
                    category_allocations=(allocation,),
                ),
            ),
            RECIPE,
            CONFIGURATION,
        )
    return profile_file


class FindCommandTests(unittest.TestCase):
    def test_finding_text_lists_current_matches_with_categories(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        CURRENT_ID,
                        CURRENT,
                        date(2026, 3, 1),
                        "-45.00",
                        "MENY GROCERY",
                    ),
                    _silver_transaction(
                        SAVINGS_ID,
                        SAVINGS,
                        date(2026, 3, 2),
                        "-20.00",
                        "weekly meny",
                    ),
                    _silver_transaction(
                        OTHER_ID,
                        CURRENT,
                        date(2026, 4, 1),
                        "-5.00",
                        "CAFE",
                    ),
                ),
            )

            status, stdout, stderr = find_transaction(profile_file, "mEnY")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines() == [
                (
                    f"{TARGET_PREFIX}{CURRENT_ID[:8]}  {CURRENT}"
                    '  2026-03-01  -45.00 DKK  "MENY GROCERY"  category groceries'
                ),
                (
                    f"{TARGET_PREFIX}{SAVINGS_ID[:8]}  {SAVINGS}"
                    '  2026-03-02  -20.00 DKK  "weekly meny"  category unclassified'
                ),
            ]

    def test_month_narrows_matching_transactions_to_that_calendar_month(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        CURRENT_ID,
                        CURRENT,
                        date(2026, 3, 31),
                        "-45.00",
                        "MENY MARCH",
                    ),
                    _silver_transaction(
                        SAVINGS_ID,
                        SAVINGS,
                        date(2026, 4, 1),
                        "-20.00",
                        "MENY APRIL",
                    ),
                    _silver_transaction(
                        OTHER_ID,
                        CURRENT,
                        date(2026, 4, 2),
                        "-5.00",
                        "CAFE",
                    ),
                ),
            )

            status, stdout, stderr = find_transaction(
                profile_file, "meny", "--month", "2026-03"
            )

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines() == [
                (
                    f"{TARGET_PREFIX}{CURRENT_ID[:8]}  {CURRENT}"
                    '  2026-03-31  -45.00 DKK  "MENY MARCH"  category groceries'
                )
            ]

    def test_account_narrows_matching_transactions_to_that_account(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        CURRENT_ID,
                        CURRENT,
                        date(2026, 3, 1),
                        "-45.00",
                        "MENY CURRENT",
                    ),
                    _silver_transaction(
                        SAVINGS_ID,
                        SAVINGS,
                        date(2026, 3, 2),
                        "-20.00",
                        "MENY SAVINGS",
                    ),
                    _silver_transaction(
                        OTHER_ID,
                        CURRENT,
                        date(2026, 3, 3),
                        "-5.00",
                        "CAFE",
                    ),
                ),
            )

            status, stdout, stderr = find_transaction(
                profile_file, "meny", "--account", SAVINGS
            )

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines() == [
                (
                    f"{TARGET_PREFIX}{SAVINGS_ID[:8]}  {SAVINGS}"
                    '  2026-03-02  -20.00 DKK  "MENY SAVINGS"  category unclassified'
                )
            ]

    def test_month_and_account_filters_apply_together(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        CURRENT_ID,
                        CURRENT,
                        date(2026, 3, 1),
                        "-45.00",
                        "MENY CURRENT MARCH",
                    ),
                    _silver_transaction(
                        SAVINGS_ID,
                        SAVINGS,
                        date(2026, 4, 1),
                        "-20.00",
                        "MENY SAVINGS APRIL",
                    ),
                    _silver_transaction(
                        OTHER_ID,
                        SAVINGS,
                        date(2026, 3, 2),
                        "-5.00",
                        "MENY SAVINGS MARCH",
                    ),
                ),
            )

            status, stdout, stderr = find_transaction(
                profile_file,
                "meny",
                "--month",
                "2026-03",
                "--account",
                SAVINGS,
            )

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines() == [
                (
                    f"{TARGET_PREFIX}{OTHER_ID[:8]}  {SAVINGS}"
                    '  2026-03-02  -5.00 DKK  "MENY SAVINGS MARCH"'
                    "  category unclassified"
                )
            ]

    def test_find_lengthens_colliding_handles_and_decide_resolves_them(self) -> None:
        first_id = "deadbeef1" + "1" * 55
        collision_id = "deadbeef2" + "2" * 55
        other_id = "f0e1d2c3" + "3" * 56
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        first_id,
                        CURRENT,
                        date(2026, 3, 1),
                        "-45.00",
                        "MENY PRIMARY",
                    ),
                    _silver_transaction(
                        collision_id,
                        SAVINGS,
                        date(2026, 3, 2),
                        "-20.00",
                        "OTHER MATCH",
                    ),
                    _silver_transaction(
                        other_id,
                        CURRENT,
                        date(2026, 3, 3),
                        "-5.00",
                        "CAFE",
                    ),
                ),
                category_id="rent",
            )

            status, stdout, stderr = find_transaction(profile_file, "meny")

            assert (status, stderr) == (EXIT_OK, "")
            (line,) = stdout.splitlines()
            fields = line.split()
            assert fields[:3] == ["target", first_id[:9], CURRENT]
            assert first_id[:8] not in fields

            status, _, stderr = decide(
                profile_file,
                "classify",
                fields[1],
                "groceries",
                "--reason",
                "Roundtrip",
            )

            assert (status, stderr) == (EXIT_OK, "")
            profile = development_profile(Path(directory))
            with GoldStore(profile, read_only=True) as store:
                current = store.current()
                assert current is not None
                gold = store.open(current.publication_id)
                (allocation,) = (
                    each
                    for each in gold.category_allocations(
                        start_date=date(2026, 3, 1),
                        end_date=date(2026, 3, 1),
                    )
                    if each.transaction_id == first_id
                )
            assert allocation.category_id == "groceries"

    def test_no_match_prints_one_line_and_succeeds(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = _profile_with_transactions(
                Path(directory),
                (
                    _silver_transaction(
                        CURRENT_ID,
                        CURRENT,
                        date(2026, 3, 1),
                        "-45.00",
                        "MENY GROCERY",
                    ),
                    _silver_transaction(
                        SAVINGS_ID,
                        SAVINGS,
                        date(2026, 3, 2),
                        "-20.00",
                        "MENY SAVINGS",
                    ),
                    _silver_transaction(
                        OTHER_ID,
                        CURRENT,
                        date(2026, 3, 3),
                        "-5.00",
                        "CAFE",
                    ),
                ),
            )

            result = find_transaction(profile_file, "no such merchant")

            assert result == (EXIT_OK, "No transactions matched.\n", "")

    def test_invalid_month_is_refused_before_store_reads(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory))

            result = find_transaction(profile_file, "meny", "--month", "2026-13")

            assert result == (
                3,
                "",
                (
                    'budget: --month "2026-13" is not YYYY-MM; expected a '
                    "calendar month such as 2026-03\n"
                ),
            )


if __name__ == "__main__":
    unittest.main()
