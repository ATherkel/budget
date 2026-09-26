# Copyright 2026 Therkel
"""Decimal places of each supported currency's minor unit (ADR-013)."""

from decimal import Decimal

# ISO 4217 minor units. A currency missing here is rejected, never guessed.
_MINOR_UNIT_PLACES = {"DKK": 2}


class UnknownCurrencyError(ValueError):
    """An account's configured currency is not in the minor-unit table."""

    def __init__(self, currency: str) -> None:
        """Name the currency the table lacks."""
        super().__init__(f"currency {currency!r} has no known minor unit")


def minor_unit_places(currency: str) -> int:
    """How many decimal places `currency`'s amounts carry."""
    try:
        return _MINOR_UNIT_PLACES[currency]
    except KeyError:
        raise UnknownCurrencyError(currency) from None


def written(amount: Decimal) -> str:
    """Write an amount that already carries its places in its one written form."""
    return format(amount, "f")
