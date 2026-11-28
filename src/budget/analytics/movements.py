# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups."""

from collections.abc import Mapping, Sequence

from budget.analytics.measures import SUMMARY_GROUPS, ZERO, money_in_out
from budget.analytics.reports import (
    MovementGroup,
    MovementRow,
    RowClassification,
    SummaryGroup,
)
from budget.gold import GoldTransaction


def _movement_group(
    group: SummaryGroup,
    transactions: Sequence[GoldTransaction],
    names: Mapping[str, str],
    classifications: Mapping[str, RowClassification],
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
            classification=classifications[t.transaction_id],
        )
        for t in newest_first
    )
    return MovementGroup(
        group=group,
        rows=rows,
        total=sum((row.contribution for row in rows), ZERO),
        flows=money_in_out(transactions),
    )


def movements(
    grouped: Mapping[SummaryGroup, Sequence[GoldTransaction]] | None,
    names: Mapping[str, str],
    classifications: Mapping[str, RowClassification],
) -> tuple[MovementGroup, ...] | None:
    """Return one group per summary group, in card order; null without evidence.

    `names` maps each selected account ID to its display name, and
    `classifications` each grouped transaction to its classification.
    """
    if grouped is None:
        return None
    return tuple(
        _movement_group(group, grouped[group], names, classifications)
        for group in SUMMARY_GROUPS
    )
