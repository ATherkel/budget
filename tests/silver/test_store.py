# Copyright 2026 Therkel
"""The Silver store: one complete build result, written and read back.

`tests/silver/test_storage.py` covers the file `migrate_silver` creates. This
module covers what the file is for: `SilverStore.replace` writes one whole
`SilverResult` in one transaction and `read` returns the complete result, with
`Decimal` money and deterministic order, before and after a reopen.
"""

import unittest
from datetime import date
from tempfile import TemporaryDirectory

from budget.profiles import test_profile as make_test_profile
from budget.silver import AcceptDiscrepancy, SilverResult, SilverStore, Withdrawn
from budget.silver.storage import migrate_silver
from tests.silver.exports import (
    build_from,
    export,
    identity,
    presented,
    row,
)

MARCH_3 = date(2026, 3, 3)
# The second of two identical coffees on 3 March; the bank drops it later.
SECOND_COFFEE = identity(MARCH_3, "-30.00", "KAFFE", 2)

EARLIER = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("03.03.2026", "KAFFE", "-30,00", "895,00"),
        # A cancelled row: retained provenance, never a transaction.
        row("03.03.2026", "KAFFE", "-30,00", "", Status="Slettet"),
        row("05.03.2026", "BOG", "-25,00", "870,00"),
    ],
    run_id="run-a",
    exported_on=date(2026, 3, 6),
)
# One coffee fewer, and the last row carries no bank labels.
LATER = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("05.03.2026", "BOG", "-25,00", "900,00", Kategori="   ", Underkategori=""),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
)
# Another account's export: it drops every transaction and disagrees.
ELSEWHERE = export(
    [
        row("01.03.2026", "HUSLEJE", "-6.000,00", "12.000,00"),
        row("03.03.2026", "EL", "-450,00", "11.550,00"),
    ],
    run_id="run-c",
    exported_on=date(2026, 3, 12),
)
# A second account, whose only booked row states no balance: a *balance-break*
# review item, settled by the *accept discrepancy* decision below.
SAVINGS = presented(
    export(
        [row("01.03.2026", "RENTE", "5,00", "", Kategori="   ", Underkategori="")],
        run_id="run-d",
        exported_on=date(2026, 3, 7),
        covers_through=date(2026, 3, 6),
    ),
    account_id="joint-savings",
    payload_id="payload-run-d",
)

DECISIONS = (
    Withdrawn(decision_id="d-0001", transaction_id=SECOND_COFFEE),
    AcceptDiscrepancy(decision_id="d-0002", import_run_id="run-d"),
)

CURRENCIES = {"joint-current": "DKK", "joint-savings": "DKK"}


def _complete_result() -> SilverResult:
    """One build that carries every shape the store has to persist."""
    return build_from(EARLIER, LATER, ELSEWHERE, SAVINGS, decisions=DECISIONS)


class SilverStoreTests(unittest.TestCase):
    def test_a_complete_result_survives_a_roundtrip_through_the_store(self) -> None:
        result = _complete_result()
        # The fixture has to carry every shape a persisted result can have, or
        # the roundtrip below would not mean what it says. Each assertion here
        # names one of those shapes.
        assert {t.account_id for t in result.transactions} == {
            "joint-current",
            "joint-savings",
        }
        assert {t.balance is None for t in result.transactions} == {False, True}
        assert {t.bank_category is None for t in result.transactions} == {False, True}
        assert {r.status for r in result.import_run_results} == {
            "accepted",
            "quarantined",
        }
        assert [len(r.errors) for r in result.import_run_results].count(0) == 3
        assert any(r.review_item_ids for r in result.import_run_results)
        assert {i.kind for i in result.review_items} == {
            "dropped-transaction",
            "export-disagreement",
            "balance-break",
        }
        assert {i.resolved_by for i in result.review_items} == {
            "d-0001",
            "d-0002",
            None,
        }
        assert {i.transaction_id is None for i in result.review_items} == {
            False,
            True,
        }
        assert len(result.account_evidence) == 2
        assert result.unbooked_records
        assert {o.end_of_day_balance is None for o in result.balance_observations} == {
            False,
            True,
        }

        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with SilverStore(profile) as store:
                store.replace(result, currencies=CURRENCIES)

                assert store.read() == result

            with SilverStore(profile) as reopened:
                assert reopened.read() == result


if __name__ == "__main__":
    unittest.main()
