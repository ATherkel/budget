# Copyright 2026 Therkel
"""Danish display of amounts, as the dashboard's reader sees them."""

from decimal import Decimal


def amount(value: Decimal | None, currency: str) -> str:
    """Return an exact amount as a Danish reader reads it, such as `9.020,00 kr.`.

    An unknown amount says so, rather than reading as zero.
    """
    if value is None:
        return "Ingen data endnu"
    digits = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    sign = "\N{MINUS SIGN}" if value < 0 else ""
    return f"{sign}{digits} {'kr.' if currency == 'DKK' else currency}"


def signed_amount(value: Decimal | None, currency: str) -> str:
    """Return `amount`, with an explicit plus sign on a positive amount."""
    shown = amount(value, currency)
    return f"+{shown}" if value is not None and value > 0 else shown
