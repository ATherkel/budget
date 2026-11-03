# Copyright 2026 Therkel
"""The Silver build reads the formats its caller supplies, not only the built-in ones.

#181 proves source independence with a test-only second format, so a Silver
build's inputs may carry a format map beside the built-in one (default: the
built-ins).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from budget.bronze.models import ImportRun, SourceRecord
from budget.silver import SilverBuildInputs, derive_silver
from tests.silver.exports import ACCOUNT
from tests.silver.synthetic_ledger import FORMAT, FORMAT_ID

PAYLOAD = "payload-synthetic-0001"


def test_a_run_in_a_supplied_format_is_read_into_transactions() -> None:
    run = ImportRun(
        import_run_id="run-synthetic-0001",
        payload_id=PAYLOAD,
        declared_account_id=ACCOUNT,
        source_format=FORMAT_ID,
        original_filename="ledger-20260305.txt",
        exported_on=date(2026, 3, 5),
        exported_on_source="filename",
        covers_from=date(2026, 3, 2),
        covers_through=date(2026, 3, 5),
        started_at=datetime(2026, 3, 5, tzinfo=UTC),
        outcome="stored",
        repeat_of=None,
    )
    record = SourceRecord(
        payload_id=PAYLOAD,
        record_ordinal=1,
        fields={
            "when": "2026-03-02",
            "sum": "-125.50",
            "memo": "GROCER",
            "bal": "874.50",
            "state": "booked",
        },
    )

    result = derive_silver(
        SilverBuildInputs(
            runs=[run],
            source_records={PAYLOAD: (record,)},
            format_failures={PAYLOAD: ()},
            currencies={ACCOUNT: "DKK"},
            formats={FORMAT_ID: FORMAT},
        )
    )

    assert [
        (t.account_id, t.transaction_date, t.amount, t.description)
        for t in result.transactions
    ] == [(ACCOUNT, date(2026, 3, 2), Decimal("-125.50"), "GROCER")]
