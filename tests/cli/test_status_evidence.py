# Copyright 2026 Therkel
"""`budget status`: the operational import evidence, apart from published figures.

Every profile and result is synthetic. The seam is the CLI itself; the Silver
result is written through the store's own public `replace`.
"""

import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from budget.gold import ClassificationReviewItem, GoldLineageRecords, GoldResult
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.silver import (
    AccountEvidence,
    EvidenceExport,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    SilverStore,
    ValidationError,
    migrate_silver,
)
from tests.cli.commands import status
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import CONFIGURATION, RECIPE, publication, publish
from tests.gold.worked_example import RECORDS

EXIT_OK = 0
CURRENT = "joint-current"
SAVINGS = "joint-savings"
PUBLISHED_AT = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
EVIDENCE_HEADING = "Import evidence (operational, apart from published figures)"


def _everything_under(folder: Path) -> list[str]:
    """Every path under `folder` but SQLite's own `-wal` and `-shm` sidecars."""
    return sorted(
        str(path.relative_to(folder))
        for path in folder.rglob("*")
        if not path.name.endswith(("-wal", "-shm"))
    )


def _export(
    run: str,
    exported_on: date,
    first: date,
    last: date,
    account_id: str = CURRENT,
) -> EvidenceExport:
    return EvidenceExport(
        import_run_id=run,
        payload_id=f"payload-{run}",
        account_id=account_id,
        exported_on=exported_on,
        covers_from=first,
        covers_through=last,
    )


def _silver(
    *,
    account_evidence: tuple[AccountEvidence, ...] = (),
    evidence_exports: tuple[EvidenceExport, ...] = (),
    import_run_results: tuple[ImportRunResult, ...] = (),
    review_items: tuple[ReviewItem, ...] = (),
) -> SilverResult:
    return SilverResult(
        transactions=(),
        transaction_evidence=(),
        unbooked_records=(),
        balance_observations=(),
        account_evidence=account_evidence,
        evidence_exports=evidence_exports,
        import_run_results=import_run_results,
        review_items=review_items,
    )


def _silver_item(
    item_id: str,
    kind: Literal["balance-break", "dropped-transaction"],
    resolved_by: str | None = None,
) -> ReviewItem:
    return ReviewItem(
        review_item_id=item_id,
        kind=kind,
        account_id=CURRENT,
        date_from=date(2026, 3, 3),
        date_to=date(2026, 3, 3),
        payload_ids=(),
        resolved_by=resolved_by,
    )


def _gold_item(item_id: str, decision_id: str) -> ClassificationReviewItem:
    return ClassificationReviewItem(
        review_item_id=item_id,
        kind="decision-not-applicable",
        transaction_ids=(),
        rule_ids=(),
        decision_id=decision_id,
        reason="target-missing",
    )


def _run(
    run: str, account_id: str, status: Literal["accepted", "quarantined"], *codes: str
) -> ImportRunResult:
    return ImportRunResult(
        import_run_id=run,
        payload_id=f"payload-{run}",
        account_id=account_id,
        status=status,
        covered_from=date(2026, 3, 15),
        covered_to=date(2026, 3, 16),
        errors=tuple(
            ValidationError(f"payload-{run}", 1, code, "synthetic") for code in codes
        ),
        review_item_ids=(),
    )


def _store_silver(profile: Profile, result: SilverResult) -> None:
    migrate_silver(profile)
    with SilverStore(profile) as store:
        store.replace(result, currencies={CURRENT: "DKK", SAVINGS: "DKK"})


class StatusEvidenceTests(unittest.TestCase):
    def test_status_shows_each_accounts_latest_export_and_evidence_through(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)
            _store_silver(
                profile,
                _silver(
                    account_evidence=(
                        AccountEvidence(CURRENT, date(2026, 1, 1), date(2026, 2, 28)),
                        AccountEvidence(CURRENT, date(2026, 3, 10), date(2026, 4, 30)),
                    ),
                    evidence_exports=(
                        _export(
                            "run-1",
                            date(2026, 3, 1),
                            date(2026, 1, 1),
                            date(2026, 2, 28),
                        ),
                        _export(
                            "run-2",
                            date(2026, 5, 2),
                            date(2026, 3, 10),
                            date(2026, 4, 30),
                        ),
                    ),
                ),
            )

            code, stdout, stderr = status(profile_file, now=PUBLISHED_AT)

            lines = stdout.splitlines()
            assert (code, stderr) == (EXIT_OK, "")
            assert "Published figures: publication 1 (current)" in lines
            assert EVIDENCE_HEADING in lines, stdout
            assert lines[lines.index(EVIDENCE_HEADING) + 1] == (
                f"{CURRENT}  latest export 2026-05-02  evidence through 2026-04-30"
            )

    def test_status_lists_each_accounts_quarantined_runs_and_only_those(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            _store_silver(
                profile,
                _silver(
                    account_evidence=(
                        AccountEvidence(CURRENT, date(2026, 3, 10), date(2026, 4, 30)),
                        AccountEvidence(SAVINGS, date(2026, 3, 10), date(2026, 4, 30)),
                    ),
                    evidence_exports=(
                        _export(
                            "run-1",
                            date(2026, 5, 2),
                            date(2026, 3, 10),
                            date(2026, 4, 30),
                        ),
                        _export(
                            "run-2",
                            date(2026, 5, 2),
                            date(2026, 3, 10),
                            date(2026, 4, 30),
                            SAVINGS,
                        ),
                    ),
                    import_run_results=(
                        _run("run-1", CURRENT, "accepted"),
                        _run(
                            "run-3",
                            CURRENT,
                            "quarantined",
                            "unknown-status",
                            "duplicate-record",
                        ),
                    ),
                ),
            )

            code, stdout, stderr = status(profile_file, now=PUBLISHED_AT)

            lines = stdout.splitlines()
            assert (code, stderr) == (EXIT_OK, "")
            assert EVIDENCE_HEADING in lines, stdout
            block = lines[lines.index(EVIDENCE_HEADING) + 1 :]
            assert block == [
                f"{CURRENT}  latest export 2026-05-02  evidence through 2026-04-30",
                (
                    "  quarantined  run-3  2026-03-15..2026-03-16"
                    "  duplicate-record, unknown-status"
                ),
                f"{SAVINGS}  latest export 2026-05-02  evidence through 2026-04-30",
                "  quarantined  none",
            ]


class StatusReviewItemTests(unittest.TestCase):
    def test_status_counts_open_review_items_by_kind_silver_apart_from_gold(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                store.publish(
                    GoldResult(
                        publication(1),
                        RECORDS,
                        GoldLineageRecords(
                            classification_review_items=(
                                _gold_item("a" * 64, "d-0001"),
                                _gold_item("b" * 64, "d-0002"),
                            )
                        ),
                    ),
                    RECIPE,
                    CONFIGURATION,
                )
            _store_silver(
                profile,
                _silver(
                    review_items=(
                        _silver_item("1" * 64, "dropped-transaction"),
                        _silver_item("2" * 64, "dropped-transaction"),
                        _silver_item("3" * 64, "balance-break"),
                        _silver_item("4" * 64, "balance-break", resolved_by="d-0009"),
                    )
                ),
            )

            code, stdout, stderr = status(profile_file, now=PUBLISHED_AT)

            lines = stdout.splitlines()
            assert (code, stderr) == (EXIT_OK, "")
            assert "Open review items" in lines, stdout
            assert lines[lines.index("Open review items") + 1 :][:2] == [
                "  Silver (operational): balance-break 1, dropped-transaction 2",
                "  Gold (publication 1): decision-not-applicable 2",
            ]


class StatusNoEvidenceTests(unittest.TestCase):
    def test_status_says_no_evidence_is_recorded_rather_than_complete(self) -> None:
        for migrated in (False, True):
            with (
                self.subTest(silver_store_migrated=migrated),
                TemporaryDirectory() as d,
            ):
                folder = Path(d)
                profile_file = write_profile(folder)
                if migrated:
                    migrate_silver(development_profile(folder))
                before = _everything_under(folder)

                code, stdout, stderr = status(profile_file)

                lines = stdout.splitlines()
                assert (code, stderr) == (EXIT_OK, "")
                assert lines[-2:] == [EVIDENCE_HEADING, "  none recorded"], stdout
                assert _everything_under(folder) == before
