# Copyright 2026 Therkel
"""Profiles: one configuration of the same code, naming its own stores.

A profile names every path the application touches. Nothing selects one
implicitly: the caller builds the profile it means, so a test run cannot
inherit the operator's shell.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

BRONZE_STORE_NAME = "bronze.db"
STORES_FOLDER = "stores"
DEVELOPMENT_PROFILE_NAME = "development"
PRODUCTION_PROFILE_NAME = "production"
TEST_PROFILE_NAME = "test"
PROFILE_NAMES: Final = (
    DEVELOPMENT_PROFILE_NAME,
    PRODUCTION_PROFILE_NAME,
    TEST_PROFILE_NAME,
)


class ProfilePathOutsideRootError(ValueError):
    """A test profile names a path outside its temporary root."""

    def __init__(self) -> None:
        """State the rule without repeating the operator's own paths."""
        super().__init__("a test profile path must stay inside its temporary root")


class UnknownProfileNameError(ValueError):
    """A profile name is not one of the declared profiles."""

    def __init__(self, name: str) -> None:
        """Name the unknown value and the profiles that exist."""
        super().__init__(
            f"unknown profile {name!r}: expected one of {', '.join(PROFILE_NAMES)}"
        )


class TestProfileRootRequiredError(ValueError):
    """A test profile must carry the temporary root it stays inside."""

    def __init__(self) -> None:
        """State the rule a test profile cannot opt out of."""
        super().__init__("a test profile must name the temporary root it stays inside")


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
        if self.name not in PROFILE_NAMES:
            raise UnknownProfileNameError(self.name)
        if self.name == TEST_PROFILE_NAME and self.root is None:
            raise TestProfileRootRequiredError
        stores = Path(self.stores).resolve()
        root = None if self.root is None else Path(self.root).resolve()
        if root is not None and not stores.is_relative_to(root):
            raise ProfilePathOutsideRootError
        object.__setattr__(self, "stores", stores)
        object.__setattr__(self, "root", root)

    def _guarded_path(self, path: Path) -> Path:
        """Resolve one derived path and re-check it against a test root.

        The filesystem is not frozen when a profile is built: the stores folder
        or the store file can be replaced by a symlink afterwards, so every
        access resolves the path again instead of trusting the construction.
        """
        resolved = Path(path).resolve()
        if self.root is not None and not resolved.is_relative_to(self.root):
            raise ProfilePathOutsideRootError
        return resolved

    @property
    def bronze_store(self) -> Path:
        """The Bronze stage store, re-checked against the test root each time."""
        return self._guarded_path(Path(self.stores) / BRONZE_STORE_NAME)


def load_profile_file(path: Path) -> Profile:
    """Build the profile that one operator's profile file describes."""
    with path.open("rb") as file:
        document = tomllib.load(file)
    return Profile(name=document["profile"], stores=Path(document["paths"]["stores"]))


def test_profile(root: str | Path) -> Profile:
    """Build the test profile whose stores live inside one temporary root."""
    return Profile(
        name=TEST_PROFILE_NAME,
        stores=Path(root) / STORES_FOLDER,
        root=Path(root),
    )
