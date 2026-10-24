# Copyright 2026 Therkel
"""`budget review`: published Gold classification questions beside Silver's.

Every profile and result is synthetic. The command seam is the CLI itself, so
these tests observe what an operator receives rather than private query calls.
"""

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold import (
    ClassificationReviewItem,
    GoldLineageRecords,
    GoldRecords,
    GoldResult,
    GoldTransaction,
)
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.silver import ReviewItem, SilverResult, SilverStore, migrate_silver
from tests.cli.commands import review
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import CONFIGURATION, RECIPE, publication
from tests.gold.worked_example import RECORDS

type SqlParameter = str | bytes | int | float | None
type SqlParameters = tuple[SqlParameter, ...] | dict[str, SqlParameter]

EXIT_OK = 0
CURRENT = "joint-current"
SILVER_ITEM = "a1b2c3d4" + "0" * 56
SILVER_TRANSACTION = "12345678" + "0" * 56
GOLD_ITEM = "f1e2d3c4" + "1" * 56
GOLD_TRANSACTION = "89abcdef" + "2" * 56
AMBIGUOUS_ITEM = "b1c2d3e4" + "3" * 56
AMBIGUOUS_A = "11111111" + "4" * 56
AMBIGUOUS_B = "22222222" + "5" * 56
UNMATCHED_ITEM = "c1d2e3f4" + "6" * 56
UNMATCHED_TRANSACTION = "33333333" + "7" * 56
DECISION_ITEM = "d1e2f3a4" + "8" * 56
DECISION_TRANSACTION = "44444444" + "9" * 56
PINNED_ITEM = "e1f2a3b4" + "b" * 56
NEXT_ITEM = "f1a2b3c4" + "c" * 56
LATER_ITEM = "a2b3c4d5" + "d" * 56
RULE_A = "r-mobilepay"
RULE_B = "r-netto"
SILVER_LINE = (
    f"{SILVER_ITEM}  balance-break  joint-current  2026-02-02..2026-02-02"
    "  handle 12345678"
)
GOLD_LINE = (
    f"{GOLD_ITEM}  rule-conflict  gold  publication 1"
    "  targets 89abcdef  rules r-mobilepay, r-netto"
)
AMBIGUOUS_LINE = (
    f"{AMBIGUOUS_ITEM}  ambiguous-transfer  gold  publication 1"
    "  targets 11111111, 22222222  rules r-savings-transfer"
)
UNMATCHED_LINE = (
    f"{UNMATCHED_ITEM}  unmatched-transfer  gold  publication 1"
    "  targets 33333333  rules r-savings-transfer"
)
DECISION_LINE = (
    f"{DECISION_ITEM}  decision-not-applicable  gold  publication 1  decision d-0004"
)
PINNED_LINE = (
    f"{PINNED_ITEM}  sign-mismatch  gold  publication 1"
    "  targets 89abcdef  rules r-netto"
)
LATER_LINE = (
    f"{LATER_ITEM}  decision-not-applicable  gold  publication 3"
    "  targets 44444444  decision d-0004"
)


def _publish(
    profile: Profile,
    items: tuple[ClassificationReviewItem, ...],
    records: GoldRecords = RECORDS,
) -> None:
    """Publish these synthetic review items with the worked-example result."""
    migrate_gold(profile)
    with GoldStore(profile) as store:
        _publish_numbered(store, 1, items, records)


def _publish_numbered(
    store: GoldStore,
    publication_id: int,
    items: tuple[ClassificationReviewItem, ...],
    records: GoldRecords = RECORDS,
) -> None:
    """Publish one numbered synthetic review result through a Gold store."""
    store.publish(
        GoldResult(
            publication(publication_id),
            records,
            GoldLineageRecords(classification_review_items=items),
        ),
        RECIPE,
        CONFIGURATION,
    )


def _store_silver(profile: Profile, result: SilverResult) -> None:
    """Migrate Silver and replace it with one synthetic result."""
    migrate_silver(profile)
    with SilverStore(profile) as store:
        store.replace(result, currencies={CURRENT: "DKK"})


def _empty_silver() -> SilverResult:
    """A stored Silver result with no open items or quarantined runs."""
    return SilverResult(
        transactions=(),
        transaction_evidence=(),
        unbooked_records=(),
        balance_observations=(),
        account_evidence=(),
        evidence_exports=(),
        import_run_results=(),
        review_items=(),
    )


def _silver_with_item() -> SilverResult:
    """A stored Silver result holding the CLI test's balance-break item."""
    return replace(
        _empty_silver(),
        review_items=(
            ReviewItem(
                review_item_id=SILVER_ITEM,
                kind="balance-break",
                account_id=CURRENT,
                date_from=date(2026, 2, 2),
                date_to=date(2026, 2, 2),
                payload_ids=(),
                resolved_by=None,
                transaction_id=SILVER_TRANSACTION,
            ),
        ),
    )


def _seed(profile: Profile) -> None:
    """Store one open Silver item and publish one Gold review item."""
    _store_silver(profile, _silver_with_item())
    _publish(
        profile,
        (
            ClassificationReviewItem(
                review_item_id=GOLD_ITEM,
                kind="rule-conflict",
                transaction_ids=(GOLD_TRANSACTION,),
                rule_ids=(RULE_A, RULE_B),
                decision_id=None,
                reason=None,
            ),
        ),
    )


def _target(transaction_id: str, source_id: str) -> GoldTransaction:
    """A worked-example transaction under a longer synthetic identifier."""
    source = next(t for t in RECORDS.transactions if t.transaction_id == source_id)
    return replace(source, transaction_id=transaction_id)


def _seed_gold_kinds(profile: Profile) -> None:
    """Publish transfer questions and an all-missing decision."""
    _store_silver(profile, _empty_silver())
    _publish(
        profile,
        (
            ClassificationReviewItem(
                review_item_id=AMBIGUOUS_ITEM,
                kind="ambiguous-transfer",
                transaction_ids=(AMBIGUOUS_A, AMBIGUOUS_B),
                rule_ids=("r-savings-transfer",),
                decision_id=None,
                reason=None,
            ),
            ClassificationReviewItem(
                review_item_id=UNMATCHED_ITEM,
                kind="unmatched-transfer",
                transaction_ids=(UNMATCHED_TRANSACTION,),
                rule_ids=("r-savings-transfer",),
                decision_id=None,
                reason="no-candidate",
            ),
            ClassificationReviewItem(
                review_item_id=DECISION_ITEM,
                kind="decision-not-applicable",
                transaction_ids=(),
                rule_ids=(),
                decision_id="d-0004",
                reason="target-missing",
            ),
        ),
        GoldRecords(
            accounts=RECORDS.accounts,
            transactions=(
                _target(AMBIGUOUS_A, "current-03"),
                _target(AMBIGUOUS_B, "savings-01"),
                _target(UNMATCHED_TRANSACTION, "current-04"),
            ),
        ),
    )


class GoldReviewCommandTests(unittest.TestCase):
    def test_review_lists_a_published_gold_rule_conflict_beside_silver(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            _seed(development_profile(folder))

            status, stdout, stderr = review(profile_file)

            assert status == EXIT_OK
            assert stderr == ""
            assert stdout.splitlines() == [SILVER_LINE, GOLD_LINE]
            assert GOLD_TRANSACTION not in stdout
            assert RULE_A in stdout
            assert RULE_B in stdout

    def test_review_lists_transfer_items_and_filters_kind(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            _seed_gold_kinds(profile)

            ambiguous_status, ambiguous, ambiguous_stderr = review(
                profile_file, "--kind", "ambiguous-transfer"
            )
            unmatched_status, unmatched, unmatched_stderr = review(
                profile_file, "--kind", "unmatched-transfer"
            )

            assert (ambiguous_status, ambiguous_stderr) == (EXIT_OK, "")
            assert ambiguous.splitlines() == [AMBIGUOUS_LINE]
            assert (unmatched_status, unmatched_stderr) == (EXIT_OK, "")
            assert unmatched.splitlines() == [UNMATCHED_LINE]

    def test_account_filter_keeps_every_target_of_a_matching_gold_item(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            _seed_gold_kinds(development_profile(folder))

            status, savings, stderr = review(profile_file, "--account", "joint-savings")

            assert (status, stderr) == (EXIT_OK, "")
            assert savings.splitlines() == [AMBIGUOUS_LINE]
            assert AMBIGUOUS_A[:8] in savings
            assert AMBIGUOUS_B[:8] in savings

    def test_an_all_missing_decision_renders_its_decision_without_targets(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            _seed_gold_kinds(development_profile(folder))

            status, stdout, stderr = review(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.splitlines() == [
                AMBIGUOUS_LINE,
                UNMATCHED_LINE,
                DECISION_LINE,
            ]
            assert "targets " not in DECISION_LINE


if __name__ == "__main__":
    unittest.main()
