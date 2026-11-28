# Copyright 2026 Therkel
"""Why each row sits where it does: one `RowClassification` per transaction.

Every report row that lists a transaction takes its classification from here,
so the rule, Category and group a table shows mean the same on every page.
"""

from collections.abc import Collection, Mapping
from datetime import date

from budget.analytics.reports import RowClassification
from budget.gold import GoldCategory, GoldRepository, GoldTransaction


def row_classifications(
    gold: GoldRepository,
    *,
    start_date: date,
    end_date: date,
    account_ids: Collection[str] | None,
) -> Mapping[str, RowClassification]:
    """Return each dated transaction's classification, by `transaction_id`."""
    categories = {c.category_id: c for c in gold.categories()}
    allocated = {
        a.transaction_id: categories[a.category_id]
        for a in gold.category_allocations(
            start_date=start_date, end_date=end_date, account_ids=account_ids
        )
    }
    return {
        t.transaction_id: _row(t, allocated.get(t.transaction_id))
        for t in gold.transactions(
            start_date=start_date, end_date=end_date, account_ids=account_ids
        )
    }


def _row(
    transaction: GoldTransaction, category: GoldCategory | None
) -> RowClassification:
    """Return one transaction's classification and the Category it got, if any."""
    if category is None:
        return RowClassification(transaction.classification)
    return RowClassification(
        transaction.classification, category.name, category.group_name
    )
