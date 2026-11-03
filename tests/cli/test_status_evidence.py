# Copyright 2026 Therkel
"""`budget status`: the operational import evidence, apart from published figures.

Every profile and result is synthetic. The seam is the CLI itself; the Silver
result is written through the store's own public `replace`.
"""

import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.silver import (
    AccountEvidence,
    EvidenceExport,
    SilverResult,
    SilverStore,
    migrate_silver,
)
from tests.cli.commands import status
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import publish

EXIT_OK = 0
CURRENT = "joint-current"
PUBLISHED_AT = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
EVIDENCE_HEADING = "Import evidence (operational, apart from published figures)"


def _export(run: str, exported_on: date, first: date, last: date) -> EvidenceExport:
    return EvidenceExport(
        import_run_id=run,
        payload_id=f"payload-{run}",
        account_id=CURRENT,
        exported_on=exported_on,
        covers_from=first,
        covers_through=last,
    )


def _silver(
    *,
    account_evidence: tuple[AccountEvidence, ...] = (),
    evidence_exports: tuple[EvidenceExport, ...] = (),
) -> SilverResult:
    return SilverResult(
        transactions=(),
        transaction_evidence=(),
        unbooked_records=(),
        balance_observations=(),
        account_evidence=account_evidence,
        evidence_exports=evidence_exports,
        import_run_results=(),
        review_items=(),
    )


def _store_silver(profile: Profile, result: SilverResult) -> None:
    migrate_silver(profile)
    with SilverStore(profile) as store:
        store.replace(result, currencies={CURRENT: "DKK"})


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
