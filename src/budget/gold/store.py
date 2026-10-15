# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

The store is a view of `gold.db` (ADR-014, `publications.md`). Opening it
never creates or changes the schema; `migrate_gold` owns that.
"""

import sqlite3
from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Final, Self

from budget.gold.models import GoldPublication
from budget.gold.recipe import Recipe
from budget.gold.repository import GoldRepository
from budget.gold.result import GoldResult
from budget.gold.storage import open_gold_connection
from budget.inputs.snapshot import ConfigurationSnapshot
from budget.profiles import Profile

_SELECT_CURRENT_ID: Final = (
    "SELECT to_publication_id FROM pointer_moves ORDER BY move DESC LIMIT 1"
)
_SELECT_RETAINED: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) ORDER BY publication_id"
)
_SELECT_RETAINED_ONE: Final = (
    "SELECT publications.* FROM publications"
    " JOIN results USING (publication_id) WHERE publication_id = ?"
)


class GoldStore:
    """Publish to and read from the Gold store that one profile names."""

    def __init__(self, profile: Profile) -> None:
        """Open the migrated Gold store that one profile names."""
        self._connection = open_gold_connection(profile)

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
        self._connection.close()

    def current(self) -> GoldPublication | None:
        """Return the current publication, or None when it has no result.

        That is before the first publish, and after a Gold migration that
        could not convert the current result until the next build.
        """
        connection = self._connection
        pointer = connection.execute(_SELECT_CURRENT_ID).fetchone()
        if pointer is None:
            return None
        row = connection.execute(_SELECT_RETAINED_ONE, (pointer[0],)).fetchone()
        return None if row is None else _publication(row)

    def available(self) -> Sequence[GoldPublication]:
        """Return the publications whose results are retained, oldest first."""
        rows = self._connection.execute(_SELECT_RETAINED).fetchall()
        return tuple(_publication(row) for row in rows)

    def open(self, publication_id: int) -> GoldRepository:
        """Return a repository bound to one retained publication."""
        raise NotImplementedError

    def next_publication_id(self) -> int:
        """Return the id the next publication must carry."""
        raise NotImplementedError

    def publish(
        self,
        result: GoldResult,
        recipe: Recipe,
        configuration: ConfigurationSnapshot,
    ) -> None:
        """Store `result` as a new publication and make it current."""
        raise NotImplementedError


def _optional_time(text: str | None) -> datetime | None:
    """Read a stored moment that may be absent."""
    return None if text is None else datetime.fromisoformat(text)


def _publication(row: sqlite3.Row) -> GoldPublication:
    """Read one `publications` row back as the metadata it stores."""
    return GoldPublication(
        publication_id=row["publication_id"],
        kind=row["kind"],
        label=row["label"],
        known_at=datetime.fromisoformat(row["known_at"]),
        built_at=datetime.fromisoformat(row["built_at"]),
        replayed_at=_optional_time(row["replayed_at"]),
        contract_version=row["contract_version"],
        fingerprint_scheme=row["fingerprint_scheme"],
        result_fingerprint=row["result_fingerprint"],
    )
