# Copyright 2026 Therkel
"""Released migrations are frozen (#364).

`src/budget/migrations/released.toml` holds, for each release tag, the
SHA-256 of each migration file that release added: a tag's table lists only
the files no earlier table lists, and it may be empty. A store records only the
number of the last migration it ran, so a released file that changes or
disappears never reaches the stores already past it. These tests read only the
manifest and the working tree: CI checks out without tags. The Release workflow
also checks, with `-m release`, that the tag it cuts has a table and that every
migration file is in some table (#492).
"""

import hashlib
import os
import tomllib
from pathlib import Path
from typing import Any

import pytest


def released_migration_drift(manifest: Path, root: Path) -> list[str]:
    """The manifest's paths under `root` that are missing or no longer match."""
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return [
        name
        for files in releases.values()
        for name, digest in files.items()
        if not (root / name).is_file() or _released_hash(root / name) != digest
    ]


def release_manifest_gaps(manifest: Path, root: Path, tag: str) -> list[str]:
    """Why `tag`'s table in the manifest doesn't freeze every migration in `root`."""
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    no_table = [] if tag in releases else [f"{tag} has no table in released.toml"]
    return no_table + [
        f"not in any table: {name}" for name in _unlisted_migrations(releases, root)
    ]


def release_manifest_addition(manifest: Path, root: Path, tag: str) -> str:
    """The released.toml lines that would list every unlisted migration under `tag`."""
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    lines = [] if tag in releases else [f'["{tag}"]']
    lines.extend(
        f'"{name}" = "{_released_hash(root / name)}"'
        for name in _unlisted_migrations(releases, root)
    )
    return "\n".join(lines) + "\n"


def release_manifest_summary(manifest: Path, root: Path, tag: str) -> str:
    """The Markdown a GitHub Actions job summary shows when `tag` can't be cut."""
    problems = "".join(
        f"- {gap}\n" for gap in release_manifest_gaps(manifest, root, tag)
    )
    lines = f"```toml\n{release_manifest_addition(manifest, root, tag)}```\n"
    path = "`src/budget/migrations/released.toml`"
    heading = f"## Release manifest incomplete for {tag}\n\n{problems}\n"
    if tag not in tomllib.loads(manifest.read_text(encoding="utf-8")):
        return f"{heading}Add these lines to the end of {path}:\n\n{lines}"
    return (
        f'{heading}Add these lines under `["{tag}"]` in {path}:\n\n{lines}\n'
        f"If {tag} is already released, its table is frozen: bump the version in "
        "`pyproject.toml` instead.\n"
    )


def release_manifest_annotations(manifest: Path, root: Path, tag: str) -> list[str]:
    """One GitHub Actions error annotation per reason `tag` can't be cut."""
    del manifest, root, tag  # red stub: green replaces this body
    return []


def _unlisted_migrations(releases: dict[str, Any], root: Path) -> list[str]:
    """The migration files under `root` that no release table lists, sorted."""
    listed = {name for files in releases.values() for name in files}
    return sorted(
        name
        for path in root.rglob("*.sql")
        if (name := path.relative_to(root).as_posix()) not in listed
    )


def _released_hash(path: Path) -> str:
    """The SHA-256 the manifest records for `path`: CRLF converted to LF first."""
    return _sha256(path.read_bytes().replace(b"\r\n", b"\n"))


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
    """A migrations folder with a manifest naming its two released files."""
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


def test_a_changed_migration_checked_out_with_crlf_endings_is_still_reported(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    changed = b"CREATE TABLE ledger (id INTEGER PRIMARY KEY, note TEXT) STRICT;\n"
    (tmp_path / BRONZE).write_bytes(changed.replace(b"\n", b"\r\n"))

    assert released_migration_drift(manifest, tmp_path) == [BRONZE]


def test_a_release_tag_with_no_table_in_the_manifest_is_reported(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)

    assert release_manifest_gaps(manifest, tmp_path, "v0.3.0") == [
        "v0.3.0 has no table in released.toml"
    ]


def test_a_migration_in_no_table_is_reported(tmp_path: Path) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )
    _write_manifest(
        manifest,
        {
            "v0.2.0": {
                BRONZE: _sha256(BRONZE_RELEASED),
                SILVER: _sha256(SILVER_RELEASED),
            },
            "v0.3.0": {},
        },
    )

    assert release_manifest_gaps(manifest, tmp_path, "v0.3.0") == [
        "not in any table: silver/0002_add_note.sql"
    ]


def test_the_lines_to_paste_list_each_unlisted_migration_with_its_hash(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / "0001_create_gold_store.sql").write_bytes(
        b"CREATE TABLE actuals (id INTEGER PRIMARY KEY) STRICT;\n"
    )

    assert release_manifest_addition(manifest, tmp_path, "v0.3.0") == (
        '["v0.3.0"]\n'
        '"gold/0001_create_gold_store.sql" = '
        '"50d4df93f40b47538839919d46816eb0eb276898283f565d826ab18a6c7b7f7e"\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
    )


def test_the_hash_to_paste_for_a_crlf_checkout_is_the_hash_of_its_lf_text(
    tmp_path: Path,
) -> None:
    # A Windows checkout with core.autocrlf writes CRLF; CI and the drift test
    # hash the LF text, so a pasted CRLF hash would fail on the next CI run.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\r\n"
    )

    assert release_manifest_addition(manifest, tmp_path, "v0.3.0") == (
        '["v0.3.0"]\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
    )


def test_the_lines_to_paste_into_an_existing_table_repeat_no_header(
    tmp_path: Path,
) -> None:
    # TOML rejects a second ["v0.3.0"] header, so the lines go under the first.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )
    _write_manifest(
        manifest,
        {
            "v0.2.0": {
                BRONZE: _sha256(BRONZE_RELEASED),
                SILVER: _sha256(SILVER_RELEASED),
            },
            "v0.3.0": {},
        },
    )

    assert release_manifest_addition(manifest, tmp_path, "v0.3.0") == (
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
    )


def test_a_tag_with_no_table_also_names_each_migration_in_no_table(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_gaps(manifest, tmp_path, "v0.3.0") == [
        "v0.3.0 has no table in released.toml",
        "not in any table: silver/0002_add_note.sql",
    ]


def test_the_job_summary_lists_the_problems_and_the_lines_to_paste(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_summary(manifest, tmp_path, "v0.3.0") == (
        "## Release manifest incomplete for v0.3.0\n"
        "\n"
        "- v0.3.0 has no table in released.toml\n"
        "- not in any table: silver/0002_add_note.sql\n"
        "\n"
        "Add these lines to the end of `src/budget/migrations/released.toml`:\n"
        "\n"
        "```toml\n"
        '["v0.3.0"]\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
    )


def test_the_job_summary_for_a_tag_with_a_table_warns_a_released_one_is_frozen(
    tmp_path: Path,
) -> None:
    # Dispatching Release without bumping pyproject's version checks the last
    # release's tag, whose table must not grow.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_summary(manifest, tmp_path, "v0.2.0") == (
        "## Release manifest incomplete for v0.2.0\n"
        "\n"
        "- not in any table: silver/0002_add_note.sql\n"
        "\n"
        'Add these lines under `["v0.2.0"]` in '
        "`src/budget/migrations/released.toml`:\n"
        "\n"
        "```toml\n"
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
        "\n"
        "If v0.2.0 is already released, its table is frozen: bump the version in "
        "`pyproject.toml` instead.\n"
    )


def test_each_problem_becomes_an_error_annotation_on_released_toml(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    error = "::error file=src/budget/migrations/released.toml,"
    error += "title=Release manifest incomplete::"
    assert release_manifest_annotations(manifest, tmp_path, "v0.3.0") == [
        f"{error}v0.3.0 has no table in released.toml",
        f"{error}not in any table: silver/0002_add_note.sql",
    ]


MIGRATIONS = Path(__file__).resolve().parent.parent / "src" / "budget" / "migrations"


# Marked release as well: the Release workflow runs only `-m release`, and it
# can tag a branch that the full test suite never ran on.
@pytest.mark.release
def test_no_migration_a_release_shipped_has_changed() -> None:
    manifest = MIGRATIONS / "released.toml"
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))

    # v0.2.0 shipped Bronze 0001 and Silver 0001; an empty manifest guards nothing.
    assert set(releases["v0.2.0"]) == {BRONZE, SILVER}
    assert released_migration_drift(manifest, MIGRATIONS) == []


@pytest.mark.release
def test_the_release_tag_has_a_table_and_every_migration_is_in_one() -> None:
    # Main keeps the last release's version while unreleased migrations pile
    # up, so only the Release workflow, which sets RELEASE_TAG, can check this.
    tag = os.environ.get("RELEASE_TAG")
    if not tag:
        pytest.skip("RELEASE_TAG is not set; the Release workflow sets it")
    manifest = MIGRATIONS / "released.toml"

    gaps = release_manifest_gaps(manifest, MIGRATIONS, tag)

    assert not gaps, "\n".join(
        [
            *gaps,
            "Add these lines to src/budget/migrations/released.toml:",
            release_manifest_addition(manifest, MIGRATIONS, tag),
        ]
    )
