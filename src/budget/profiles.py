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
WRITER_LOCK_NAME = "budget.lock"
STORES_FOLDER = "stores"
DEVELOPMENT_PROFILE_NAME = "development"
PRODUCTION_PROFILE_NAME = "production"
TEST_PROFILE_NAME = "test"
PROFILE_NAMES: Final = (
    DEVELOPMENT_PROFILE_NAME,
    PRODUCTION_PROFILE_NAME,
    TEST_PROFILE_NAME,
)
PROFILE_FILE_FORMAT: Final = 1
# Test profiles are never files: the test suite builds each one (ADR-015).
_FILE_PROFILE_NAMES: Final = (DEVELOPMENT_PROFILE_NAME, PRODUCTION_PROFILE_NAME)
_FILE_KEYS: Final = frozenset({"format", "profile", "paths", "backups", "dashboard"})
_PATH_KEYS: Final = frozenset(
    {"stores", "inbox", "exports", "inputs", "backups", "upstream_backups"}
)


class ProfileFileError(ValueError):
    """A profile file the application cannot use: a configuration error."""

    def __init__(self, path: Path, problem: str) -> None:
        """Name the file and what is wrong with it."""
        super().__init__(f"{path}: {problem}")


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

    @property
    def writer_lock_file(self) -> Path:
        """The file a writing command locks, re-checked like every store path."""
        return self._guarded_path(Path(self.stores) / WRITER_LOCK_NAME)


def _read_profile_document(path: Path) -> dict[str, object]:
    """Parse the file as TOML, turning every read failure into a refusal."""
    try:
        with path.open("rb") as file:
            # Rebuilt from its items, so the values are typed `object`, not
            # the `Any` that `tomllib` returns; every check below narrows them.
            document: dict[str, object] = dict(tomllib.load(file).items())
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise ProfileFileError(path, f"cannot be read: {reason}") from None
    except tomllib.TOMLDecodeError as error:
        raise ProfileFileError(path, f"is not valid TOML: {error}") from None
    return document


def _require_format(path: Path, document: dict[str, object]) -> None:
    """Refuse a file without the one format version this code reads."""
    if "format" not in document:
        raise ProfileFileError(path, "has no format version")
    version = document["format"]
    # `bool` is an `int` in Python, so `format = true` must not pass as 1.
    if type(version) is not int or version != PROFILE_FILE_FORMAT:
        raise ProfileFileError(
            path,
            f"format {version!r} is not supported: this code reads "
            f"format {PROFILE_FILE_FORMAT}",
        )


def _require_known_keys(
    path: Path, table: dict[str, object], *, known: frozenset[str], prefix: str
) -> None:
    """Refuse a key the documented profile schema does not have."""
    unknown = sorted(set(table) - known)
    if unknown:
        names = ", ".join(f"{prefix}{key}" for key in unknown)
        raise ProfileFileError(path, f"unknown key {names}")


def _profile_name(path: Path, document: dict[str, object]) -> str:
    """Return the file's profile name, refusing `test` and unknown names."""
    name = document.get("profile")
    if name == TEST_PROFILE_NAME:
        raise ProfileFileError(
            path, "a test profile is never a file: the test suite builds it"
        )
    if not isinstance(name, str) or name not in _FILE_PROFILE_NAMES:
        expected = " or ".join(_FILE_PROFILE_NAMES)
        raise ProfileFileError(path, f"profile {name!r} is not {expected}")
    return name


def _stores_path(path: Path, document: dict[str, object]) -> Path:
    """Return `[paths].stores`, which must be an absolute path."""
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ProfileFileError(path, "has no [paths] table")
    _require_known_keys(path, paths, known=_PATH_KEYS, prefix="paths.")
    stores = paths.get("stores")
    if not isinstance(stores, str):
        raise ProfileFileError(path, "paths.stores must be a path in quotes")
    if not Path(stores).is_absolute():
        raise ProfileFileError(path, "paths.stores must be an absolute path")
    return Path(stores)


def load_profile_file(path: Path) -> Profile:
    """Build the profile that one operator's profile file describes.

    The file is versioned TOML with only the keys `operations.md` documents.
    Every problem is a `ProfileFileError` naming the file.
    """
    document = _read_profile_document(path)
    _require_format(path, document)
    _require_known_keys(path, document, known=_FILE_KEYS, prefix="")
    name = _profile_name(path, document)
    return Profile(name=name, stores=_stores_path(path, document))


def test_profile(root: str | Path) -> Profile:
    """Build the test profile whose stores live inside one temporary root."""
    return Profile(
        name=TEST_PROFILE_NAME,
        stores=Path(root) / STORES_FOLDER,
        root=Path(root),
    )
