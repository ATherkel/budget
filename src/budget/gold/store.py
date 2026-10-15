# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`."""

from collections.abc import Sequence
from types import TracebackType
from typing import Self

from budget.gold.models import GoldPublication
from budget.gold.repository import GoldRepository
from budget.profiles import Profile


class GoldStore:
    """Publish to and read from the Gold store that one profile names."""

    def __init__(self, profile: Profile) -> None:
        """Open the migrated Gold store that one profile names."""
        raise NotImplementedError

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
        """Release the store's connection."""
        raise NotImplementedError

    def current(self) -> GoldPublication | None:
        """Return the current publication, or None before the first publish."""
        raise NotImplementedError

    def available(self) -> Sequence[GoldPublication]:
        """Return the publications whose results are retained."""
        raise NotImplementedError

    def open(self, publication_id: int) -> GoldRepository:
        """Return a repository bound to one retained publication."""
        raise NotImplementedError
