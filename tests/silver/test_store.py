# Copyright 2026 Therkel
"""The Silver store: one complete build result, written and read back.

`tests/silver/test_storage.py` covers the file `migrate_silver` creates. This
module covers what the file is for: `SilverStore.replace` writes one whole
`SilverResult` in one transaction and `read` returns the complete result, with
`Decimal` money and deterministic order, before and after a reopen.
"""

import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from tempfile import TemporaryDirectory
from threading import Thread

import pytest

from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.silver import (
    AcceptDiscrepancy,
    MoneyPrecisionError,
    MoneyRangeError,
    NonFiniteMoneyError,
    SilverResult,
    SilverStore,
    Transaction,
    UnbookedRecord,
    UnknownAccountCurrencyError,
    Withdrawn,
)
from budget.silver.currencies import UnknownCurrencyError
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

# Every table a replacement rewrites, as the literal statements that count
# their rows. ADR-013 mandates the on-disk shape, so a test may look at it.
_COUNT_DERIVED_ROWS = (
    "SELECT COUNT(*) FROM account_currencies",
    "SELECT COUNT(*) FROM transactions",
    "SELECT COUNT(*) FROM transaction_evidence",
    "SELECT COUNT(*) FROM unbooked_records",
    "SELECT COUNT(*) FROM balance_observations",
    "SELECT COUNT(*) FROM account_evidence",
    "SELECT COUNT(*) FROM import_run_results",
    "SELECT COUNT(*) FROM validation_errors",
    "SELECT COUNT(*) FROM import_run_result_review_items",
    "SELECT COUNT(*) FROM review_items",
    "SELECT COUNT(*) FROM review_item_payloads",
)


def _complete_result() -> SilverResult:
    """One build that carries every shape the store has to persist."""
    return build_from(EARLIER, LATER, ELSEWHERE, SAVINGS, decisions=DECISIONS)


def _one_transaction(amount: Decimal, currency: str = "DKK") -> SilverResult:
    """A minimal result carrying one booked transaction, for boundary values."""
    return SilverResult(
        transactions=(
            Transaction(
                transaction_id="0" * 64,
                account_id="joint-current",
                transaction_date=date(2026, 3, 1),
                amount=amount,
                currency=currency,
                description="BOUNDARY",
                source_system="danske-csv-v1",
                balance=None,
                source_status="Udført",
                booking_status="booked",
                occurrence=1,
                day_sequence=1,
                identity_version="1",
                bank_category=None,
                bank_subcategory=None,
            ),
        ),
        transaction_evidence=(),
        unbooked_records=(),
        balance_observations=(),
        account_evidence=(),
        import_run_results=(),
        review_items=(),
    )


def _one_unbooked(account_id: str) -> SilverResult:
    """A minimal result whose only amount belongs to one account."""
    return SilverResult(
        transactions=(),
        transaction_evidence=(),
        unbooked_records=(
            UnbookedRecord(
                payload_id="payload-run-a",
                record_ordinal=1,
                import_run_id="run-a",
                account_id=account_id,
                transaction_date=date(2026, 3, 1),
                amount=Decimal("1.00"),
                source_status="Slettet",
                booking_status="cancelled",
            ),
        ),
        balance_observations=(),
        account_evidence=(),
        import_run_results=(),
        review_items=(),
    )


def _stored_minor_units(profile: Profile) -> int:
    """The integer the store wrote, read straight from the file.

    ADR-013 mandates the representation, so this is the one place a test looks
    past `SilverStore.read` and at the column itself.
    """
    with closing(sqlite3.connect(profile.silver_store)) as connection:
        row = connection.execute("SELECT amount FROM transactions").fetchone()
    assert row is not None
    return int(row[0])


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


class SilverMoneyTests(unittest.TestCase):
    def test_money_is_stored_as_exact_integer_minor_units(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with SilverStore(profile) as store:
                store.replace(
                    _one_transaction(Decimal("-45.00")),
                    currencies={"joint-current": "DKK"},
                )

            assert _stored_minor_units(profile) == -4500

    def test_the_ambient_decimal_precision_does_not_change_what_is_stored(
        self,
    ) -> None:
        # A two-digit context would round ordinary Decimal arithmetic; the
        # persistence boundary must not depend on it.
        with TemporaryDirectory() as directory, localcontext() as context:
            context.prec = 2
            profile = make_test_profile(directory)
            migrate_silver(profile)
            result = _one_transaction(Decimal("1234567.89"))

            with SilverStore(profile) as store:
                store.replace(result, currencies={"joint-current": "DKK"})

                assert store.read() == result

            assert _stored_minor_units(profile) == 123456789

    def test_the_int64_limits_are_stored_exactly(self) -> None:
        cases = {
            Decimal("92233720368547758.07"): 2**63 - 1,
            Decimal("-92233720368547758.08"): -(2**63),
        }
        for amount, minor_units in cases.items():
            with self.subTest(amount), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)
                result = _one_transaction(amount)

                with SilverStore(profile) as store:
                    store.replace(result, currencies={"joint-current": "DKK"})

                    assert store.read() == result

                assert _stored_minor_units(profile) == minor_units

    def test_one_minor_unit_beyond_the_int64_range_is_refused(self) -> None:
        amounts = (
            Decimal("92233720368547758.08"),
            Decimal("-92233720368547758.09"),
        )
        for amount in amounts:
            with self.subTest(amount), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)

                with (
                    SilverStore(profile) as store,
                    pytest.raises(MoneyRangeError),
                ):
                    store.replace(
                        _one_transaction(amount),
                        currencies={"joint-current": "DKK"},
                    )

    def test_an_amount_the_store_cannot_hold_exactly_is_refused_and_keeps_the_result(
        self,
    ) -> None:
        cases = {
            "more decimal places than DKK allows": (
                Decimal("-45.001"),
                MoneyPrecisionError,
            ),
            "not a number": (Decimal("NaN"), NonFiniteMoneyError),
            "an infinity": (Decimal("Infinity"), NonFiniteMoneyError),
            "beyond the int64 range": (
                Decimal("92233720368547758.08"),
                MoneyRangeError,
            ),
        }
        for label, (amount, defect) in cases.items():
            with self.subTest(label), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)
                result = _complete_result()

                with SilverStore(profile) as store:
                    store.replace(result, currencies=CURRENCIES)

                    with pytest.raises(defect):
                        store.replace(
                            _one_transaction(amount),
                            currencies={"joint-current": "DKK"},
                        )

                    # Nothing was written: the earlier result is still whole.
                    assert store.read() == result

                with SilverStore(profile) as reopened:
                    assert reopened.read() == result

    def test_an_unsupported_currency_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with (
                SilverStore(profile) as store,
                pytest.raises(UnknownCurrencyError),
            ):
                store.replace(
                    _one_transaction(Decimal("-45.00"), currency="XYZ"),
                    currencies={"joint-current": "XYZ"},
                )

    def test_an_account_without_a_currency_in_the_snapshot_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with (
                SilverStore(profile) as store,
                pytest.raises(UnknownAccountCurrencyError),
            ):
                store.replace(
                    _one_unbooked("joint-savings"),
                    currencies={"joint-current": "DKK"},
                )

    def test_an_amount_with_more_places_than_its_currency_has_is_refused(self) -> None:
        # ADR-013: a value carrying more decimal places than its currency allows
        # is rejected, never normalised, even when the extra places are zeros.
        amounts = (
            Decimal("1.230"),
            Decimal("-1.230"),
            Decimal("0.000"),
            Decimal("12345.6789"),
        )
        for amount in amounts:
            with self.subTest(amount), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)
                result = _complete_result()

                with SilverStore(profile) as store:
                    store.replace(result, currencies=CURRENCIES)

                    with pytest.raises(MoneyPrecisionError):
                        store.replace(
                            _one_transaction(amount),
                            currencies={"joint-current": "DKK"},
                        )

                    assert store.read() == result

    def test_an_amount_with_fewer_places_than_its_currency_has_is_padded(self) -> None:
        # `-45,0` and `-45,00` are one amount to the build, so fewer places are
        # padded to the currency's; only *more* places are refused.
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            result = _one_transaction(Decimal("1.2"))

            with SilverStore(profile) as store:
                store.replace(result, currencies={"joint-current": "DKK"})

                [stored] = store.read().transactions
                assert stored.amount == Decimal("1.20")

            assert _stored_minor_units(profile) == 120

    def test_an_amount_with_a_huge_exponent_is_refused(self) -> None:
        # Building 10**5000 would either take unbounded work or fail inside
        # Python's integer-to-string limit; the refusal must come first.
        amounts = (
            Decimal("1e5000"),
            Decimal("-1e5000"),
            Decimal("9.9e999999"),
        )
        for amount in amounts:
            with self.subTest(amount), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)
                result = _complete_result()

                with SilverStore(profile) as store:
                    store.replace(result, currencies=CURRENCIES)

                    with pytest.raises(MoneyRangeError):
                        store.replace(
                            _one_transaction(amount),
                            currencies={"joint-current": "DKK"},
                        )

                    assert store.read() == result

    def test_a_zero_with_a_huge_exponent_is_stored_as_zero(self) -> None:
        # An exponent-heavy zero carries no significant digits: it is exactly
        # zero, so it is stored without building the exponent's power.
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            result = _one_transaction(Decimal("0e5000"))

            with SilverStore(profile) as store:
                store.replace(result, currencies={"joint-current": "DKK"})

                [stored] = store.read().transactions
                assert stored.amount == Decimal("0.00")

            assert _stored_minor_units(profile) == 0


class SilverDurabilityTests(unittest.TestCase):
    def test_a_failed_replacement_leaves_the_previous_result_readable(self) -> None:
        result = _complete_result()
        first, second, *rest = result.transactions
        first_item, *later_items = result.review_items
        # Each of these breaks a unique key after earlier rows of the same
        # replacement are already written: one early (transactions), one late
        # (review items, after every collection before it is in).
        inconsistent = {
            "an early duplicate transaction": replace(
                result, transactions=(first, first, second, *rest)
            ),
            "a late duplicate review item": replace(
                result, review_items=(first_item, first_item, *later_items)
            ),
        }
        for label, broken in inconsistent.items():
            with self.subTest(label), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                migrate_silver(profile)

                with SilverStore(profile) as store:
                    store.replace(result, currencies=CURRENCIES)

                    with pytest.raises(sqlite3.IntegrityError):
                        store.replace(broken, currencies=CURRENCIES)

                    # The transaction rolled back: the previous result is
                    # whole, and this connection is ready for the next attempt.
                    assert store.read() == result

                with SilverStore(profile) as reopened:
                    assert reopened.read() == result

    def test_a_read_is_one_snapshot_while_the_result_is_replaced(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            complete = _complete_result()
            smaller = _one_transaction(Decimal("-45.00"))

            def replace_repeatedly() -> None:
                with SilverStore(profile) as writer:
                    for _ in range(25):
                        writer.replace(smaller, currencies=CURRENCIES)
                        writer.replace(complete, currencies=CURRENCIES)

            with SilverStore(profile) as store:
                store.replace(complete, currencies=CURRENCIES)
                writer = Thread(target=replace_repeatedly)
                writer.start()
                try:
                    for _ in range(100):
                        # Two tables from two different builds would show up
                        # here as a result that equals neither whole result.
                        assert store.read() in (complete, smaller)
                finally:
                    writer.join()

            with SilverStore(profile) as reopened:
                assert reopened.read() in (complete, smaller)

    def test_an_empty_result_clears_every_derived_row_and_keeps_the_identity(
        self,
    ) -> None:
        empty = SilverResult((), (), (), (), (), (), ())
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with SilverStore(profile) as store:
                store.replace(_complete_result(), currencies=CURRENCIES)

                store.replace(empty, currencies={})

                assert store.read() == empty

            with closing(sqlite3.connect(profile.silver_store)) as connection:
                counts = [
                    connection.execute(statement).fetchone()[0]
                    for statement in _COUNT_DERIVED_ROWS
                ]
                assert set(counts) == {0}
                assert connection.execute(
                    "SELECT profile, stage FROM store_identity"
                ).fetchall() == [("test", "silver")]
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


if __name__ == "__main__":
    unittest.main()
