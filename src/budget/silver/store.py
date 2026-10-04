# Copyright 2026 Therkel
"""Reading and replacing the one persisted SilverResult of a profile.

The store is a view of `silver.db` (ADR-015): `replace` writes one whole
`SilverResult` in one transaction, and `read` returns the complete result.
Opening never creates or changes the schema; `migrate_silver` owns that.
"""

from collections.abc import Mapping
from types import TracebackType
from typing import Self

from budget.profiles import Profile
from budget.silver.models import SilverResult
from budget.silver.storage import open_silver_connection


class SilverStore:
    """Read and replace the Silver store that one profile names."""

    def __init__(self, profile: Profile) -> None:
        """Open the migrated Silver store that one profile names."""
        self._connection = open_silver_connection(profile)

    def __enter__(self) -> Self:
        """Return the open store for a `with` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the store when the `with` block ends."""
        self.close()

    def close(self) -> None:
        """Release resources when the store is closed."""
        self._connection.close()

    def replace(self, result: SilverResult, *, currencies: Mapping[str, str]) -> None:
        """Replace the stored result with one complete `SilverResult`."""
        raise NotImplementedError

    def read(self) -> SilverResult:
        """Return the complete stored result, with Decimal money."""
        raise NotImplementedError
