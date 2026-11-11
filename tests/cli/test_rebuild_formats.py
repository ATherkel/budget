# Copyright 2026 Therkel
"""A pipeline rebuild reads the formats its caller supplies (#181).

The household declares its accounts in `danske-csv-v1`; a test-only second
format is imported through Bronze under its own declaration and rebuilt into
Silver, with no change to the built-in formats.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from budget.bronze import BronzeStore
from budget.bronze.models import ImportDeclaration
from budget.locking import writer_lock
from budget.rebuilding import rebuild_through_gold
from budget.silver import SilverStore
from tests.cli.pipelines import prepared
from tests.silver import synthetic_ledger


def test_a_pipeline_rebuild_reads_a_supplied_format_into_silver(
    tmp_path: Path,
) -> None:
    profile = prepared(tmp_path / "household").profile
    export = tmp_path / "ledger.tsv"
    export.write_bytes(
        synthetic_ledger.payload(("2026-03-02", "-125.50", "GROCER", "874.50"))
    )
    declaration = ImportDeclaration(
        declared_account_id="joint-current",
        source_format=synthetic_ledger.FORMAT_ID,
        covers_from=date(2026, 3, 1),
        covers_through=date(2026, 3, 5),
        exported_on=date(2026, 3, 5),
    )
    with BronzeStore(
        profile, parsers={synthetic_ledger.FORMAT_ID: synthetic_ledger.PARSER}
    ) as bronze:
        bronze.import_file(export, declaration)

    with writer_lock(profile) as lock:
        rebuild_through_gold(
            lock,
            now=datetime(2026, 3, 6, tzinfo=UTC),
            formats={synthetic_ledger.FORMAT_ID: synthetic_ledger.FORMAT},
        )

    with SilverStore(profile) as silver:
        transactions = silver.read().transactions
    assert [(t.transaction_date, t.amount, t.description) for t in transactions] == [
        (date(2026, 3, 2), Decimal("-125.50"), "GROCER")
    ]
