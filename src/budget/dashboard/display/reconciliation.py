# Copyright 2026 Therkel
"""An account-month's reconciliation in words, as Overblik and Kontrol print it."""

from decimal import Decimal

from budget.analytics import Reconciliation
from budget.dashboard.display.amounts import amount, signed_amount

UNKNOWN = "Ukendt"


def known_amount(value: Decimal | None, currency: str) -> str:
    """Return a balance, with a missing one unknown rather than 0."""
    return UNKNOWN if value is None else amount(value, currency)


def known_difference(value: Decimal | None, currency: str) -> str:
    """Return a change or residual with its direction signed, or unknown, never 0."""
    return UNKNOWN if value is None else signed_amount(value, currency)


def flows(reconciliation: Reconciliation) -> tuple[tuple[str, Decimal | None], ...]:
    """Return the month's components, from its opening to its expected closing."""
    return (
        ("Indtægter minus udgifter", reconciliation.income_minus_expenses),
        ("Overførsler", reconciliation.transfers),
        ("Ukategoriseret ind", reconciliation.unclassified_in),
        ("Ukategoriseret ud", reconciliation.unclassified_out),
        ("Regulering ind", reconciliation.adjustments_in),
        ("Regulering ud", reconciliation.adjustments_out),
    )
