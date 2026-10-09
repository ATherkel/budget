# Copyright 2026 Therkel
"""`gold.build`: Gold records from Silver, the account registry and the taxonomy.

Nothing is classified yet, so every transaction is `unknown`. The expected
records are the worked example's (`gold-layer.md`), and the other cases are
synthetic. Records come in no fixed order, so they are compared as multisets.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import GoldAccount, GoldResult, GoldTransaction
from budget.inputs import Account
from tests.gold.worked_example import (
    ACCOUNTS,
    CATEGORIES,
    CURRENT,
    PUBLICATION,
    SAVINGS,
    TRANSACTIONS,
)
from tests.gold.worked_silver import (
    REGISTRY,
    SILVER,
    build_from,
    silver_transaction,
)


def test_the_registry_and_taxonomy_are_published_as_dimensions() -> None:
    result = build_from()

    assert result.publication() == PUBLICATION
    assert Counter(result.accounts()) == Counter(ACCOUNTS)
    assert Counter(result.categories()) == Counter(CATEGORIES)


def test_an_account_with_no_export_is_published_without_evidence() -> None:
    unimported = Account(
        account_id="own-savings",
        display_name="Own savings",
        account_type="savings",
        ownership_scope="person",
        currency="DKK",
        source_format="danske-csv-v1",
    )

    result = build_from(accounts={**REGISTRY, "own-savings": unimported})

    assert Counter(result.accounts()) == Counter(
        (
            *ACCOUNTS,
            GoldAccount(
                account_id="own-savings",
                display_name="Own savings",
                account_type="savings",
                ownership_scope="person",
                currency="DKK",
                closed_on=None,
                coverage_start=None,
                evidence_through=None,
            ),
        )
    )


def _all_transactions(result: GoldResult) -> Sequence[GoldTransaction]:
    return result.transactions(start_date=date.min, end_date=date.max)


def test_each_booked_silver_transaction_is_one_unknown_gold_transaction() -> None:
    result = build_from()

    # The balance check has tests of its own.
    assert Counter(
        replace(t, balance_check="opening") for t in _all_transactions(result)
    ) == Counter(
        replace(
            t,
            description=f"TEXT {t.transaction_id}",
            transaction_type="unknown",
            transfer_group_id=None,
            balance_check="opening",
        )
        for t in TRANSACTIONS
    )


def test_a_pending_or_cancelled_silver_transaction_is_no_gold_transaction() -> None:
    unbooked = (
        replace(
            silver_transaction("pending", CURRENT, date(2026, 4, 28), "-60.00", None),
            booking_status="pending",
        ),
        replace(
            silver_transaction("cancelled", SAVINGS, date(2026, 3, 3), "5.00", None),
            booking_status="cancelled",
        ),
    )
    silver = replace(SILVER, transactions=(*SILVER.transactions, *unbooked))

    found = _all_transactions(build_from(silver))

    assert Counter(found) == Counter(_all_transactions(build_from()))


def test_the_worked_examples_balance_checks_come_out_exactly() -> None:
    result = build_from()

    assert {t.transaction_id: t.balance_check for t in _all_transactions(result)} == {
        t.transaction_id: t.balance_check for t in TRANSACTIONS
    }


def test_a_missing_balance_is_bridged_but_never_filled_in() -> None:
    stated = (
        silver_transaction("a", CURRENT, date(2026, 1, 5), "-5.00", None),
        silver_transaction("b", CURRENT, date(2026, 1, 6), "-10.00", "100.00"),
        silver_transaction("c", CURRENT, date(2026, 1, 7), "-10.00", None),
        silver_transaction("d", CURRENT, date(2026, 1, 8), "-10.00", "80.00"),
        silver_transaction("e", CURRENT, date(2026, 1, 9), "-10.00", "75.00"),
    )

    found = _all_transactions(build_from(replace(SILVER, transactions=stated)))

    assert [(t.transaction_id, t.balance_after, t.balance_check) for t in found] == [
        ("a", None, "missing_balance"),
        ("b", Decimal("100.00"), "opening"),
        ("c", None, "missing_balance"),
        # 100.00 - 10.00 - 10.00, bridging c's missing balance
        ("d", Decimal("80.00"), "consistent"),
        ("e", Decimal("75.00"), "break"),
    ]
