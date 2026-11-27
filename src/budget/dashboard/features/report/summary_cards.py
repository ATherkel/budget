# Copyright 2026 Therkel
"""Overblik's summary cards: one spec per card, every card the same view model."""

from dataclasses import dataclass

from budget.analytics import MonthlyOverview, SummaryGroup


@dataclass(frozen=True)
class GroupCard:
    """The card of one summary group: what sets it apart from the others."""

    group: SummaryGroup
    label: str
    empty: str


def summary_cards(overview: MonthlyOverview, specs: tuple[GroupCard, ...] = ()) -> tuple:
    """Return the overview's summary cards, one per spec, in spec order."""
    return ()
