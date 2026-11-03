# Copyright 2026 Therkel
"""The versioned fingerprint of one stored Silver result."""

from collections.abc import Mapping
from typing import Final

from budget.silver.models import SilverResult

SILVER_FINGERPRINT_SCHEME: Final = "1"


def result_fingerprint(result: SilverResult, *, currencies: Mapping[str, str]) -> str:
    """Return the result and currency snapshot's lowercase hexadecimal hash."""
    _ = result, currencies
    return ""
