# Copyright 2026 Therkel
"""Released migrations are frozen (#364).

`src/budget/migrations/released.toml` holds, for each release tag, the
SHA-256 of every migration file that release shipped. A store records only the
number of the last migration it ran, so a released file that changes or
disappears never reaches the stores already past it. These tests read only the
manifest and the working tree: CI checks out without tags.
"""

import hashlib
import tomllib
from pathlib import Path


def released_migration_drift(manifest: Path, root: Path) -> list[str]:
    """The manifest's paths under `root` that are missing or no longer match."""
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return [
        name
        for files in releases.values()
        for name, digest in files.items()
        if not (root / name).is_file()
        or _sha256((root / name).read_bytes().replace(b"\r\n", b"\n")) != digest
    ]


def _sha256(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def _write_manifest(path: Path, releases: dict[str, dict[str, str]]) -> None:
    lines: list[str] = []
    for tag, files in releases.items():
        lines.append(f'["{tag}"]')
        lines.extend(f'"{name}" = "{digest}"' for name, digest in files.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


BRONZE = "bronze/0001_create_bronze_store.sql"
SILVER = "silver/0001_create_silver_store.sql"
BRONZE_RELEASED = b"CREATE TABLE ledger (id INTEGER PRIMARY KEY) STRICT;\n"
SILVER_RELEASED = b"CREATE TABLE evidence (id INTEGER PRIMARY KEY) STRICT;\n"


def _released_tree(root: Path) -> Path:
    """A migrations folder exactly as v0.2.0 shipped it, with its manifest."""
    (root / "bronze").mkdir()
    (root / "silver").mkdir()
    (root / BRONZE).write_bytes(BRONZE_RELEASED)
    (root / SILVER).write_bytes(SILVER_RELEASED)
    manifest = root / "released.toml"
    _write_manifest(
        manifest,
        {
            "v0.2.0": {
                BRONZE: _sha256(BRONZE_RELEASED),
                SILVER: _sha256(SILVER_RELEASED),
            }
        },
    )
    return manifest


def test_a_released_migration_whose_text_changed_is_reported(tmp_path: Path) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / SILVER).write_bytes(
        b"CREATE TABLE evidence (id INTEGER PRIMARY KEY, note TEXT) STRICT;\n"
    )

    assert released_migration_drift(manifest, tmp_path) == [SILVER]


def test_a_released_migration_that_was_deleted_is_reported(tmp_path: Path) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / BRONZE).unlink()

    assert released_migration_drift(manifest, tmp_path) == [BRONZE]


def test_a_released_migration_checked_out_with_crlf_endings_is_not_reported(
    tmp_path: Path,
) -> None:
    # A Windows checkout with core.autocrlf writes CRLF; CI checks out LF.
    manifest = _released_tree(tmp_path)
    (tmp_path / BRONZE).write_bytes(BRONZE_RELEASED.replace(b"\n", b"\r\n"))

    assert released_migration_drift(manifest, tmp_path) == []
