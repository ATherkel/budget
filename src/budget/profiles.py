# Copyright 2026 Therkel
"""Profiles: one configuration of the same code, naming its own stores.

A profile names every path the application touches. Nothing selects one
implicitly: the caller builds the profile it means, so a test run cannot
inherit the operator's shell.
"""

from dataclasses import dataclass
from pathlib import Path

BRONZE_STORE_NAME = "bronze.db"
STORES_FOLDER = "stores"
TEST_PROFILE_NAME = "test"


class ProfilePathOutsideRootError(ValueError):
    """A test profile names a path outside its temporary root."""

    def __init__(self) -> None:
        """State the rule without repeating the operator's own paths."""
        super().__init__("a test profile path must stay inside its temporary root")


@dataclass(frozen=True)
class Profile:
    """One profile: the name a store records and the folder holding its stores.

    `root` is the temporary directory a test profile must stay inside. It is
    `None` for the development and production profiles, whose paths the
    operator's own profile file names.
    """

    name: str
    stores: Path
    root: Path | None = None

    def __post_init__(self) -> None:
        """Resolve the paths, refusing a test profile that escapes its root."""
        stores = Path(self.stores).resolve()
        root = None if self.root is None else Path(self.root).resolve()
        if root is not None and not stores.is_relative_to(root):
            raise ProfilePathOutsideRootError
        object.__setattr__(self, "stores", stores)
        object.__setattr__(self, "root", root)

    @property
    def bronze_store(self) -> Path:
        """The Bronze stage store inside this profile's stores folder."""
        return Path(self.stores) / BRONZE_STORE_NAME


def test_profile(root: str | Path) -> Profile:
    """Build the test profile whose stores live inside one temporary root."""
    return Profile(
        name=TEST_PROFILE_NAME,
        stores=Path(root) / STORES_FOLDER,
        root=Path(root),
    )
