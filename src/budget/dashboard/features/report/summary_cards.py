# Copyright 2026 Therkel
"""Overblik's summary cards: one spec per card, every card the same view model.

A new summary group is one `GroupCard` in `CARDS`, and no template changes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from budget.analytics import MonthlyOverview, MovementGroup, MovementRow, SummaryGroup
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.months import danish_date
from budget.dashboard.features.report.card import Card, Cell, Column, Figure, Table

NO_DATA = "Ingen data endnu."


class CardSpec(Protocol):
    """What builds one card from the month's overview."""

    def card(self, overview: MonthlyOverview) -> Card:
        """Return the card for `overview`."""
        ...


@dataclass(frozen=True)
class Field:
    """One column of a group card's table and the text each row shows in it."""

    column: Column
    text: Callable[[MovementRow, str], str]


DATE = Field(Column("Dato"), lambda row, _: danish_date(row.transaction_date))
TEXT = Field(Column("Tekst"), lambda row, _: row.description)
BANK_AMOUNT = Field(
    Column("Bankbeløb", numeric=True),
    lambda row, currency: signed_amount(row.amount, currency),
)
CONTRIBUTION = Field(
    Column("Bidrag", numeric=True),
    lambda row, currency: signed_amount(row.contribution, currency),
)

type Figures = Callable[[str, MovementGroup | None, str], tuple[Figure, ...]]


def total(name: str, group: MovementGroup | None, currency: str) -> tuple[Figure]:
    """Return the group's summed contribution; unknown without data."""
    return (Figure(name, amount(group.total if group else None, currency)),)


@dataclass(frozen=True)
class GroupCard:
    """The card of one summary group: what sets it apart from the others."""

    group: SummaryGroup
    label: str
    empty: str
    figures: Figures = total
    fields: tuple[Field, ...] = (DATE, TEXT, BANK_AMOUNT, CONTRIBUTION)

    def card(self, overview: MonthlyOverview) -> Card:
        """Return the group's card; without data it says so."""
        group = next(
            (g for g in overview.movements or () if g.group == self.group), None
        )
        rows = group.rows if group else ()
        return Card(
            name=self.group,
            label=self.label,
            figures=self.figures(self.group, group, overview.currency),
            tables=(
                Table(
                    label=f"Posteringer bag {self.label}",
                    columns=tuple(field.column for field in self.fields),
                    rows=tuple(self._cells(row, overview.currency) for row in rows),
                    empty=self.empty if group else NO_DATA,
                ),
            ),
        )

    def _cells(self, row: MovementRow, currency: str) -> tuple[Cell, ...]:
        return tuple(Cell(f.column, f.text(row, currency)) for f in self.fields)


@dataclass(frozen=True)
class MoneyLeft:
    """Penge tilbage: a figure without rows of its own, so it never expands."""

    def card(self, overview: MonthlyOverview) -> Card:
        """Return Penge tilbage's card."""
        return Card(
            name="money-left",
            label="Penge tilbage",
            figures=(
                Figure("money-left", amount(overview.net_cash_flow, overview.currency)),
            ),
        )


# Every summary card, in the order Overblik shows them.
CARDS: tuple[CardSpec, ...] = (
    GroupCard("income", "Indtægter", "Ingen indtægter i måneden."),
    MoneyLeft(),
)


def summary_cards(
    overview: MonthlyOverview, specs: tuple[CardSpec, ...] = CARDS
) -> tuple[Card, ...]:
    """Return the overview's summary cards, one per spec, in spec order."""
    return tuple(spec.card(overview) for spec in specs)
