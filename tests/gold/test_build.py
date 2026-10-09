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
