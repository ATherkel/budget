# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups."""

from collections.abc import Mapping, Sequence

from budget.analytics.measures import SUMMARY_GROUPS, ZERO
from budget.analytics.reports import (
    MoneyInOut,
    MovementGroup,
    MovementRow,
    SummaryGroup,
)
from budget.gold import GoldTransaction


def _movement_group(
    group: SummaryGroup,
    transactions: Sequence[GoldTransaction],
    names: Mapping[str, str],
) -> MovementGroup:
    # Newest first: by date, then account, then booking sequence, descending.
    newest_first = sorted(
        transactions,
        key=lambda t: (t.transaction_date, t.account_id, t.account_sequence),
        reverse=True,
    )
    rows = tuple(
        MovementRow(
            transaction_date=t.transaction_date,
            description=t.description,
            account_id=t.account_id,
            account_display_name=names[t.account_id],
            amount=t.amount,
            contribution=t.amount * SUMMARY_GROUPS[group],
        )
        for t in newest_first
    )
    amounts = [row.amount for row in rows]
    return MovementGroup(
        group=group,
        rows=rows,
        total=sum((row.contribution for row in rows), ZERO),
        flows=MoneyInOut(
            money_in=sum((a for a in amounts if a > 0), ZERO),
            money_out=sum((a for a in amounts if a < 0), ZERO),
            count=len(amounts),
        ),
    )


def movements(
    grouped: Mapping[SummaryGroup, Sequence[GoldTransaction]] | None,
    names: Mapping[str, str],
) -> tuple[MovementGroup, ...] | None:
    """Return one group per summary group, in card order; null without evidence.

    `names` maps each selected account ID to its display name.
    """
    if grouped is None:
        return None
    return tuple(
        _movement_group(group, grouped[group], names) for group in SUMMARY_GROUPS
    )
