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

ACCOUNTS_FILE_NAME = "accounts.toml"
BRONZE_STORE_NAME = "bronze.db"
EXPORTS_FOLDER = "exports"
IMPORT_LOG_FILE_NAME = "imports.jsonl"
INBOX_FOLDER = "inbox"
INPUTS_FOLDER = "inputs"
STORES_FOLDER = "stores"
WRITER_LOCK_NAME = "budget.lock"
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
_SHARED_FILE_KEYS: Final = frozenset({"format", "profile", "paths", "dashboard"})
_SHARED_PATH_KEYS: Final = frozenset({"stores", "inbox", "exports", "inputs"})
# Only production writes backup sets; development only reads production's.
_FILE_KEYS: Final = {
    DEVELOPMENT_PROFILE_NAME: _SHARED_FILE_KEYS,
    PRODUCTION_PROFILE_NAME: _SHARED_FILE_KEYS | {"backups"},
}
_PATH_KEYS: Final = {
    DEVELOPMENT_PROFILE_NAME: _SHARED_PATH_KEYS | {"upstream_backups"},
    PRODUCTION_PROFILE_NAME: _SHARED_PATH_KEYS | {"backups"},
}


class ProfileFileError(ValueError):
    """A profile file the application cannot use: a configuration error."""

    def __init__(self, path: Path, problem: str) -> None:
        """Name the file and what is wrong with it."""
        super().__init__(f"{path}: {problem}")


class ProfileFoldersOverlapError(ValueError):
    """The inbox and the export archive share a folder.

    The archive would then hold the inbox file itself, and an import would
    remove its only archived copy when it removes the file from the inbox.
    """

    def __init__(self) -> None:
        """State the rule without repeating the operator's own paths."""
        super().__init__(
            "the inbox and the export archive must be separate folders, "
            "neither inside the other"
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


@dataclass(frozen=True, kw_only=True)
class Profile:
    """One profile: the name a store records, and every folder it touches.

    Every field is passed by name: they are mostly paths, so a positional call
    could put one folder in another's place without a type error.

    `root` is the temporary directory a test profile must stay inside. It is
    `None` for the development and production profiles, whose paths the
    operator's own profile file names.
    """

    name: str
    stores: Path
    inputs: Path
    inbox: Path
    exports: Path
    backups: Path | None = None
    root: Path | None = None

    def __post_init__(self) -> None:
        """Resolve the paths, refusing a test profile that escapes its root."""
        if self.name not in PROFILE_NAMES:
            raise UnknownProfileNameError(self.name)
        if self.name == TEST_PROFILE_NAME and self.root is None:
            raise TestProfileRootRequiredError
        folders = {
            "stores": Path(self.stores).resolve(),
            "inputs": Path(self.inputs).resolve(),
            "inbox": Path(self.inbox).resolve(),
            "exports": Path(self.exports).resolve(),
        }
        inbox, exports = folders["inbox"], folders["exports"]
        if inbox.is_relative_to(exports) or exports.is_relative_to(inbox):
            raise ProfileFoldersOverlapError
        root = None if self.root is None else Path(self.root).resolve()
        if root is not None and not all(
            folder.is_relative_to(root) for folder in folders.values()
        ):
            raise ProfilePathOutsideRootError
        for field_name, folder in folders.items():
            object.__setattr__(self, field_name, folder)
        object.__setattr__(self, "root", root)

    def _guarded_path(self, path: Path) -> Path:
        """Resolve one derived path and re-check it against a test root.

        The filesystem is not frozen when a profile is built: a folder or a file
        the profile names can be replaced by a symlink afterwards, so every
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
    def accounts_file(self) -> Path:
        """The account registry, re-checked against the test root each time."""
        return self._guarded_path(Path(self.inputs) / ACCOUNTS_FILE_NAME)

    def archive_file(self, archive_path: str) -> Path:
        """One file in the export archive, re-checked against the test root.

        `archive_path` is relative to the archive, as the import log records it.
        """
        return self._guarded_path(Path(self.exports) / archive_path)

    @property
    def import_log_file(self) -> Path:
        """The append-only import log, re-checked against the test root each time."""
        return self._guarded_path(Path(self.inputs) / IMPORT_LOG_FILE_NAME)

    @property
    def backup_staging(self) -> Path:
        """The local folder a backup set is written in until it is complete."""
        raise NotImplementedError

    @property
    def writer_lock_file(self) -> Path:
        """The file a writing command locks, re-checked like every store path."""
        return self._guarded_path(Path(self.stores) / WRITER_LOCK_NAME)


def _read_profile_document(path: Path) -> dict[str, object]:
    """Parse the file as TOML, turning every read failure into a refusal."""
    try:
        # `utf-8-sig` skips the byte-order mark some Windows editors write.
        text = path.read_text(encoding="utf-8-sig")
        # Rebuilt from its items, so the values are typed `object`, not
        # the `Any` that `tomllib` returns; every check below narrows them.
        document: dict[str, object] = dict(tomllib.loads(text).items())
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise ProfileFileError(path, f"cannot be read: {reason}") from None
    except UnicodeDecodeError:
        raise ProfileFileError(path, "is not UTF-8 text") from None
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
    path: Path,
    table: dict[str, object],
    *,
    known: frozenset[str],
    prefix: str,
    profile: str,
) -> None:
    """Refuse a key the documented schema of this profile does not have."""
    unknown = sorted(set(table) - known)
    if unknown:
        names = ", ".join(f"{prefix}{key}" for key in unknown)
        raise ProfileFileError(path, f"unknown key {names} for a {profile} profile")


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


def _paths_table(
    path: Path, document: dict[str, object], profile: str
) -> dict[str, object]:
    """Return the `[paths]` table, refusing a key this profile does not have."""
    table = document.get("paths")
    if not isinstance(table, dict):
        raise ProfileFileError(path, "has no [paths] table")
    # Rebuilt so the values are typed `object`, as in `_read_profile_document`;
    # TOML keys are always strings, so `str` changes nothing.
    paths: dict[str, object] = {str(key): value for key, value in table.items()}
    _require_known_keys(
        path, paths, known=_PATH_KEYS[profile], prefix="paths.", profile=profile
    )
    return paths


def _folder_path(path: Path, paths: dict[str, object], key: str) -> Path:
    """Return `[paths].<key>`, which must be an absolute path."""
    folder = paths.get(key)
    if not isinstance(folder, str):
        raise ProfileFileError(path, f"paths.{key} must be a path in quotes")
    if not Path(folder).is_absolute():
        raise ProfileFileError(path, f"paths.{key} must be an absolute path")
    return Path(folder)


def load_profile_file(path: Path) -> Profile:
    """Build the profile that one operator's profile file describes.

    The file is versioned TOML with only the keys `operations.md` documents
    for its profile. Every problem is a `ProfileFileError` naming the file.
    """
    document = _read_profile_document(path)
    _require_format(path, document)
    name = _profile_name(path, document)
    _require_known_keys(path, document, known=_FILE_KEYS[name], prefix="", profile=name)
    paths = _paths_table(path, document, name)
    try:
        return Profile(
            name=name,
            stores=_folder_path(path, paths, "stores"),
            inputs=_folder_path(path, paths, "inputs"),
            inbox=_folder_path(path, paths, "inbox"),
            exports=_folder_path(path, paths, "exports"),
        )
    except ProfileFoldersOverlapError as error:
        raise ProfileFileError(path, str(error)) from None


def test_profile(root: str | Path) -> Profile:
    """Build the test profile whose stores live inside one temporary root."""
    return Profile(
        name=TEST_PROFILE_NAME,
        stores=Path(root) / STORES_FOLDER,
        inputs=Path(root) / INPUTS_FOLDER,
        inbox=Path(root) / INBOX_FOLDER,
        exports=Path(root) / EXPORTS_FOLDER,
        root=Path(root),
    )
