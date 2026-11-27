# Copyright 2026 Therkel
"""Overblik's Afstemning: one card per selected account, the same view model."""

from budget.analytics import Diagnostics, Reconciliation
from budget.dashboard.display.amounts import signed_amount
from budget.dashboard.display.reconciliation import (
    flows,
    known_amount,
    known_difference,
)
from budget.dashboard.features.report.card import (
    NO_DATA,
    Card,
    Cell,
    Column,
    Figure,
    Table,
)

ITEM = Column("Post")
AMOUNT = Column("Beløb", numeric=True)


def _unexplained(reconciliation: Reconciliation, currency: str) -> str:
    """Return the unexplained difference, or say a missing input rules it out."""
    residual = reconciliation.internal_residual
    if residual is None:
        return "Ikke mulig at afstemme"
    return signed_amount(residual, currency)


def _lines(
    reconciliation: Reconciliation, currency: str
) -> tuple[tuple[str, str], ...]:
    """Return the account-month's lines, from its opening to its opening gap."""
    return (
        ("Startsaldo", known_amount(reconciliation.opening_balance, currency)),
        *(
            (label, known_difference(value, currency))
            for label, value in flows(reconciliation)
        ),
        ("Beregnet slutsaldo", known_amount(reconciliation.expected_closing, currency)),
        ("Bankens slutsaldo", known_amount(reconciliation.closing_balance, currency)),
        ("Uforklaret forskel", _unexplained(reconciliation, currency)),
        ("Åbningsforskel", known_difference(reconciliation.opening_gap, currency)),
    )


def reconciliation_card(reconciliation: Reconciliation, currency: str) -> Card:
    """Return one account's card: its unexplained difference and the lines behind it."""
    name = f"reconciliation-{reconciliation.account_id}"
    return Card(
        name=name,
        label=f"Afstemning, {reconciliation.display_name}",
        figures=(Figure(name, _unexplained(reconciliation, currency)),),
        tables=(
            Table(
                label=f"Afstemning for {reconciliation.display_name}",
                columns=(ITEM, AMOUNT),
                rows=tuple(
                    (Cell(ITEM, label), Cell(AMOUNT, text))
                    for label, text in _lines(reconciliation, currency)
                ),
                empty=NO_DATA,
            ),
        ),
    )


def reconciliation_cards(diagnostics: Diagnostics) -> tuple[Card, ...]:
    """Return one card per selected account, in the order diagnostics gives them."""
    return tuple(
        reconciliation_card(reconciliation, diagnostics.currency)
        for reconciliation in diagnostics.reconciliations
    )
