# Copyright 2026 Therkel
"""Detaljer's Ind and Ud: one spec per card, each account's cards the same view model.

A new card per account is one `FlowCard` in `CARDS`, and no template changes.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from budget.analytics import AccountActivitySnapshot, ActivityRow, MoneyInOut
from budget.dashboard.display.amounts import signed_amount
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import transaction_kind
from budget.dashboard.features.report.card import (
    NO_DATA,
    Card,
    Cell,
    Column,
    Figure,
    Table,
)

DATE = Column("Dato")
TEXT = Column("Tekst")
KIND = Column("Type")
AMOUNT = Column("Beløb", numeric=True)


def _cells(row: ActivityRow, currency: str) -> tuple[Cell, ...]:
    return (
        Cell(DATE, danish_date(row.transaction_date)),
        Cell(TEXT, row.description),
        Cell(KIND, transaction_kind(row)),
        Cell(AMOUNT, signed_amount(row.amount, currency)),
    )


def activity_table(
    label: str, rows: tuple[ActivityRow, ...], currency: str, empty: str
) -> Table:
    """Return an account's transactions as a table: date, text, type and amount."""
    return Table(
        label=label,
        columns=(DATE, TEXT, KIND, AMOUNT),
        rows=tuple(_cells(row, currency) for row in rows),
        empty=empty,
    )


@dataclass(frozen=True)
class FlowCard:
    """One direction of an account's money: its total and the rows behind it."""

    name: str
    label: str
    empty: str
    total: Callable[[MoneyInOut], Decimal]
    keeps: Callable[[Decimal], bool]

    def card(
        self,
        account: AccountActivitySnapshot,
        rows: tuple[ActivityRow, ...],
        currency: str,
    ) -> Card:
        """Return the card of `account` in this direction."""
        flows = account.money_in_out
        return Card(
            name=f"activity-{self.name}-{account.account_id}",
            label=self.label,
            figures=(
                Figure(
                    f"activity-{self.name}-{account.account_id}",
                    signed_amount(self.total(flows) if flows else None, currency),
                ),
            ),
            tables=(
                activity_table(
                    f"{self.label} for {account.display_name}",
                    tuple(row for row in rows if self.keeps(row.amount)),
                    currency,
                    self.empty if flows else NO_DATA,
                ),
            ),
        )


# Each account's cards, in the order Detaljer shows them.
CARDS = (
    FlowCard(
        "in",
        "Ind",
        "Ingen penge ind i måneden.",
        lambda flows: flows.money_in,
        lambda amount: amount > 0,
    ),
    FlowCard(
        "out",
        "Ud",
        "Ingen penge ud i måneden.",
        lambda flows: flows.money_out,
        lambda amount: amount < 0,
    ),
)


def account_cards(
    account: AccountActivitySnapshot, rows: tuple[ActivityRow, ...], currency: str
) -> tuple[Card, ...]:
    """Return the cards of `account` and its own rows, one per spec, in order."""
    return tuple(spec.card(account, rows, currency) for spec in CARDS)
