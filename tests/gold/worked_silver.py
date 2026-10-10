# Copyright 2026 Therkel
"""The worked example of `gold-layer.md` as the inputs `gold.build` reads.

The Silver transactions carry only what Silver knows: each row's date, amount,
description and bank-stated balance, with its order within a date. They are
listed in reverse, so a build that kept Silver's order would show it. One
admitted export per account, dated 2026-05-08, declares 2026-01-01 through
2026-05-08. Every account, text and amount is invented.
"""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import GoldResult, build
from budget.inputs import (
    Account,
    Category,
    CategoryGroup,
    ConfigurationSnapshot,
    Taxonomy,
)
from budget.silver import (
    AccountEvidence,
    EvidenceExport,
    SilverResult,
    Transaction,
)
from tests.gold.worked_example import (
    CURRENT,
    PUBLICATION,
    SAVINGS,
    TRANSACTIONS,
)

EXPORTED_ON = date(2026, 5, 8)
COVERS_FROM = date(2026, 1, 1)

REGISTRY: Mapping[str, Account] = {
    CURRENT: Account(
        account_id=CURRENT,
        display_name="Joint current",
        account_type="current",
        ownership_scope="household",
        currency="DKK",
        source_format="danske-csv-v1",
    ),
    SAVINGS: Account(
        account_id=SAVINGS,
        display_name="Joint savings",
        account_type="savings",
        ownership_scope="household",
        currency="DKK",
        source_format="danske-csv-v1",
    ),
}

# `taxonomy.toml` as loaded: the groups and categories the example's
# `CATEGORIES` flatten.
TAXONOMY = Taxonomy(
    groups={
        "income": CategoryGroup("income", "Income", "income"),
        "housing": CategoryGroup("housing", "Housing", "expense"),
        "food": CategoryGroup("food", "Food", "expense"),
    },
    categories={
        "salary": Category("salary", "Salary", "income"),
        "interest": Category("interest", "Interest", "income"),
        "rent": Category("rent", "Rent", "housing"),
        "utilities": Category("utilities", "Utilities", "housing"),
        "groceries": Category("groceries", "Groceries", "food"),
    },
)


def silver_transaction(
    transaction_id: str,
    account_id: str,
    transaction_date: date,
    amount: str,
    balance: str | None,
) -> Transaction:
    """One booked Silver transaction in DKK, the first on its date."""
    return Transaction(
        transaction_id=transaction_id,
        account_id=account_id,
        transaction_date=transaction_date,
        amount=Decimal(amount),
        currency="DKK",
        description=f"TEXT {transaction_id}",
        source_system="danske-csv-v1",
        balance=None if balance is None else Decimal(balance),
        source_status="Udført",
        booking_status="booked",
        occurrence=1,
        day_sequence=1,
        identity_version="1",
        bank_category=None,
        bank_subcategory=None,
    )


def _silver_transactions() -> tuple[Transaction, ...]:
    """The example's rows as Silver states them, numbered within each date."""
    seen: dict[tuple[str, date], int] = {}
    rows = []
    for t in TRANSACTIONS:
        key = (t.account_id, t.transaction_date)
        seen[key] = seen.get(key, 0) + 1
        stated = silver_transaction(
            t.transaction_id,
            t.account_id,
            t.transaction_date,
            str(t.amount),
            str(t.balance_after),
        )
        rows.append(replace(stated, day_sequence=seen[key]))
    return tuple(reversed(rows))


SILVER = SilverResult(
    transactions=_silver_transactions(),
    transaction_evidence=(),
    unbooked_records=(),
    balance_observations=(),
    account_evidence=tuple(
        AccountEvidence(account_id, COVERS_FROM, EXPORTED_ON)
        for account_id in (CURRENT, SAVINGS)
    ),
    evidence_exports=tuple(
        EvidenceExport(
            f"run-{account_id}", account_id, EXPORTED_ON, COVERS_FROM, EXPORTED_ON
        )
        for account_id in (CURRENT, SAVINGS)
    ),
    import_run_results=(),
    review_items=(),
)


def build_from(
    silver: SilverResult = SILVER,
    *,
    accounts: Mapping[str, Account] = REGISTRY,
) -> GoldResult:
    """Run the Gold build over these inputs, bound to the example's publication.

    The configuration has no rules: nothing is classified yet.
    """
    return build(
        silver=silver,
        configuration=ConfigurationSnapshot(
            accounts=accounts, taxonomy=TAXONOMY, rules={}
        ),
        publication=PUBLICATION,
    )
