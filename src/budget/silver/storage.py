# Copyright 2026 Therkel
"""The Silver stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/silver/` inside the
installed package, and every refusal around them are shared with Bronze
(`budget.sqlstore`). This module names the Silver stage, re-exports the shared
refusals under the stage's own module, and will hold the persistence-level
money conversion.
"""

import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Final

from budget.profiles import Profile
from budget.silver.currencies import minor_unit_places
from budget.sqlstore import (
    BUSY_TIMEOUT_MS,
    ForeignKeyViolationError,
    MigrationRequiredError,
    MigrationResourceError,
    ProductionMigrationBlockedError,
    StageStore,
    StoreBusyError,
    StoreError,
    StoreIdentityError,
    StoreNotFoundError,
    UnsupportedSQLiteVersionError,
    UnsupportedStoreVersionError,
    UnversionedStoreError,
    migrate_store,
    open_store_connection,
    require_migration_allowed,
)

SILVER_STAGE: Final = "silver"
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "silver"
)
# SQLite's INTEGER is a 64-bit signed integer, so a money value outside these
# bounds has no exact representation and is refused, never clamped.
MIN_MINOR_UNIT: Final = -(2**63)
MAX_MINOR_UNIT: Final = 2**63 - 1

__all__ = [
    "BUSY_TIMEOUT_MS",
    "MAX_MINOR_UNIT",
    "MIN_MINOR_UNIT",
    "SILVER_STAGE",
    "ForeignKeyViolationError",
    "MigrationRequiredError",
    "MigrationResourceError",
    "MoneyError",
    "MoneyPrecisionError",
    "MoneyRangeError",
    "NonFiniteMoneyError",
    "ProductionMigrationBlockedError",
    "StoreBusyError",
    "StoreError",
    "StoreIdentityError",
    "StoreNotFoundError",
    "UnknownAccountCurrencyError",
    "UnsupportedSQLiteVersionError",
    "UnsupportedStoreVersionError",
    "UnversionedStoreError",
    "from_minor_units",
    "migrate_silver",
    "open_silver_connection",
    "require_migration_allowed",
    "to_minor_units",
]


def migrate_silver(profile: Profile) -> None:
    """Create or upgrade the Silver store that one profile names.

    The production profile is refused before any folder or file is touched.
    """
    migrate_store(silver_stage(profile))


def silver_stage(profile: Profile) -> StageStore:
    """Name the Silver store one profile describes."""
    return StageStore(
        profile=profile,
        stage=SILVER_STAGE,
        label="Silver",
        path=profile.silver_store,
        migrations=_MIGRATIONS_FOLDER,
    )


def open_silver_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Silver store, refusing anything it cannot vouch for."""
    return open_store_connection(silver_stage(profile))


class MoneyError(ValueError):
    """An amount cannot be stored exactly as integer minor units."""


class NonFiniteMoneyError(MoneyError):
    """The amount is NaN or an infinity, which no currency can hold."""

    def __init__(self, amount: Decimal, currency: str) -> None:
        """Name the amount and the currency that cannot hold it."""
        super().__init__(f"{currency} cannot hold the amount {amount}")


class MoneyPrecisionError(MoneyError):
    """The amount carries more decimal places than its currency has."""

    def __init__(self, amount: Decimal, currency: str) -> None:
        """Name the amount and the currency's exact number of places."""
        super().__init__(
            f"{currency} amounts carry {minor_unit_places(currency)} decimal "
            f"places, so {amount} cannot be stored exactly"
        )


class MoneyRangeError(MoneyError):
    """The amount's minor units do not fit SQLite's 64-bit integer."""

    def __init__(self, minor_units: int) -> None:
        """Name the count and the range it left."""
        super().__init__(
            f"{minor_units} minor units do not fit a 64-bit signed integer"
        )


class UnknownAccountCurrencyError(ValueError):
    """An account with money has no currency in the result's snapshot."""

    def __init__(self, account_id: str) -> None:
        """Name the account whose currency the caller left out."""
        super().__init__(f"account {account_id!r} has no currency in this result")


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Write an amount as an exact count of `currency`'s minor unit (ADR-013).

    The conversion is integer arithmetic on the Decimal's own digits: it never
    rounds, never passes through `float`, and does not depend on the ambient
    decimal context's precision. An unsupported currency, a non-finite value,
    more decimal places than the currency allows, and a value outside SQLite's
    64-bit integer are each refused rather than guessed at.
    """
    places = minor_unit_places(currency)
    sign, digits, exponent = amount.as_tuple()
    if not isinstance(exponent, int):
        raise NonFiniteMoneyError(amount, currency)
    coefficient = int("".join(str(digit) for digit in digits)) if digits else 0
    shift = exponent + places
    if shift >= 0:
        minor = coefficient * _power_of_ten(shift)
    else:
        divisor = _power_of_ten(-shift)
        if coefficient % divisor:
            raise MoneyPrecisionError(amount, currency)
        minor = coefficient // divisor
    minor = -minor if sign else minor
    if not MIN_MINOR_UNIT <= minor <= MAX_MINOR_UNIT:
        raise MoneyRangeError(minor)
    return minor


def _power_of_ten(exponent: int) -> int:
    """Return 10**exponent exactly, for the small, non-negative powers used here.

    `int.__pow__` types its result as `Any`, which a strict type checker refuses
    to treat as an `int`; multiplying out the power keeps the arithmetic and the
    type exact, and no amount's exponent is large enough for that to matter.
    """
    value = 1
    for _ in range(exponent):
        value *= 10
    return value


def from_minor_units(minor: int, currency: str) -> Decimal:
    """Read an exact count of `currency`'s minor unit back as a Decimal.

    The result carries exactly the currency's decimal places, so a roundtrip
    through the store returns the value the build wrote, and the construction
    depends on no ambient decimal context.
    """
    places = minor_unit_places(currency)
    sign = 1 if minor < 0 else 0
    digits = tuple(int(character) for character in str(abs(minor)))
    return Decimal((sign, digits, -places))
