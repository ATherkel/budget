# Copyright 2026 Therkel
"""`budget review`: the open Silver review items, and how to settle them.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. The profile holds a migrated Silver
store and a synthetic `SilverResult` written through the store's own public
`replace`; review reads that stored result and nothing else, so it needs no
Bronze store and no `accounts.toml`.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import (
    ImportRunResult,
    ReviewItem,
    SilverResult,
    SilverStore,
    migrate_silver,
)
from tests.cli.commands import review
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
CURRENT = "joint-current"
SAVINGS = "joint-savings"
# Distinct identifiers that share an 8-character prefix, so a line that
# truncated one would no longer read as the identifier it names.
RUN_A = "0400a869" + "1" * 24
RUN_B = "0400a869" + "2" * 24
RUN_C = "75674506" + "3" * 24
PAYLOAD_A = "1a2b3c4d" + "0" * 56
PAYLOAD_B = "1a2b3c4d" + "1" * 56
BREAK_ITEM = "aaaa0000" + "1" * 56
DROP_ITEM = "aaaa0000" + "2" * 56
DISAGREE_ITEM = "bbbb1111" + "3" * 56
RESOLVED_ITEM = "bbbb1111" + "4" * 56
# Only the transaction reaches the terminal as a handle, its first 8.
TRANSACTION = "8f6e62bc" + "0" * 56
TRANSACTION_HANDLE = "8f6e62bc"

EXPECTED_BREAK = (
    f"{BREAK_ITEM}  balance-break  joint-savings  2026-04-01..2026-04-02"
    f"  run {RUN_C}  payload {PAYLOAD_B}"
)
EXPECTED_DROP = (
    f"{DROP_ITEM}  dropped-transaction  joint-current  2026-03-03..2026-03-03"
    f"  run {RUN_B}  payload {PAYLOAD_A}, {PAYLOAD_B}  handle {TRANSACTION_HANDLE}"
)
EXPECTED_DISAGREE = (
    f"{DISAGREE_ITEM}  export-disagreement  joint-current"
    f"  2026-03-10..2026-03-12  run {RUN_A}  payload {PAYLOAD_A}"
)

_RESULT = SilverResult(
    transactions=(),
    transaction_evidence=(),
    unbooked_records=(),
    balance_observations=(),
    account_evidence=(),
    import_run_results=(
        ImportRunResult(
            import_run_id=RUN_A,
            status="quarantined",
            covered_from=date(2026, 3, 1),
            covered_to=date(2026, 3, 12),
            errors=(),
            review_item_ids=(DISAGREE_ITEM, RESOLVED_ITEM),
        ),
        ImportRunResult(
            import_run_id=RUN_B,
            status="quarantined",
            covered_from=date(2026, 3, 1),
            covered_to=date(2026, 3, 9),
            errors=(),
            review_item_ids=(DROP_ITEM,),
        ),
        ImportRunResult(
            import_run_id=RUN_C,
            status="quarantined",
            covered_from=date(2026, 4, 1),
            covered_to=date(2026, 4, 2),
            errors=(),
            review_item_ids=(BREAK_ITEM,),
        ),
    ),
    review_items=(
        ReviewItem(
            review_item_id=BREAK_ITEM,
            kind="balance-break",
            account_id=SAVINGS,
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 2),
            payload_ids=(PAYLOAD_B,),
            resolved_by=None,
        ),
        ReviewItem(
            review_item_id=DROP_ITEM,
            kind="dropped-transaction",
            account_id=CURRENT,
            date_from=date(2026, 3, 3),
            date_to=date(2026, 3, 3),
            payload_ids=(PAYLOAD_A, PAYLOAD_B),
            resolved_by=None,
            transaction_id=TRANSACTION,
        ),
        ReviewItem(
            review_item_id=DISAGREE_ITEM,
            kind="export-disagreement",
            account_id=CURRENT,
            date_from=date(2026, 3, 10),
            date_to=date(2026, 3, 12),
            payload_ids=(PAYLOAD_A,),
            resolved_by=None,
        ),
        ReviewItem(
            review_item_id=RESOLVED_ITEM,
            kind="dropped-transaction",
            account_id=CURRENT,
            date_from=date(2026, 3, 5),
            date_to=date(2026, 3, 5),
            payload_ids=(PAYLOAD_A,),
            resolved_by="d-0007",
            transaction_id=TRANSACTION,
        ),
    ),
)


def _seeded_profile(folder: Path) -> Profile:
    """Migrate Silver and store the synthetic result that holds the items."""
    profile = development_profile(folder)
    migrate_silver(profile)
    with SilverStore(profile) as store:
        store.replace(_RESULT, currencies={CURRENT: "DKK", SAVINGS: "DKK"})
    return profile


class ReviewCommandTests(unittest.TestCase):
    def test_review_lists_open_items_with_filters_and_no_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _seeded_profile(folder)

            # Review takes no writer lock: holding it here proves that.
            with writer_lock(profile):
                status, everything, stderr = review(profile_file)

            assert status == EXIT_OK
            assert stderr == ""
            # Stored order, the resolved item skipped.
            assert everything.splitlines() == [
                EXPECTED_BREAK,
                EXPECTED_DROP,
                EXPECTED_DISAGREE,
            ]
            status, dropped, _ = review(profile_file, "--kind", "dropped-transaction")
            assert status == EXIT_OK
            assert dropped.splitlines() == [EXPECTED_DROP]
            status, savings, _ = review(profile_file, "--account", SAVINGS)
            assert status == EXIT_OK
            assert savings.splitlines() == [EXPECTED_BREAK]
            status, empty, stderr = review(profile_file, "--account", "no-such-account")
            assert status == EXIT_OK
            assert (empty, stderr) == ("", "")
            # Reference identifiers reach the terminal in full, so an operator
            # can name the exact target; only the transaction is a handle.
            assert TRANSACTION_HANDLE in everything
            assert TRANSACTION not in everything


if __name__ == "__main__":
    unittest.main()
