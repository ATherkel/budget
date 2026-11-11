# Copyright 2026 Therkel
"""Released migrations are frozen (#364).

`src/budget/migrations/released.toml` holds a table per release that added
migrations, with the SHA-256 of each file it added: a table lists only the files
no earlier table lists, and a release that adds none has no table. A store
records only the number of the last migration it ran, so a released file that
changes or disappears never reaches the stores already past it. These tests read
only the manifest and the working tree: CI checks out without tags. The Release
workflow also checks, with `-m release`, that every migration file is in some
table (#492).
"""

import hashlib
import os
import sys
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


def released_drift_summary(manifest: Path, root: Path) -> str:
    """The Markdown a job summary shows when released migrations changed."""
    del manifest, root  # red stub: green replaces this body
    return ""


def release_manifest_gaps(manifest: Path, root: Path) -> list[str]:
    """Why the manifest doesn't freeze every migration in `root`.

    Only unlisted files count, whatever tag is being cut: a release that adds
    no migration needs no table, because earlier tables list every file.
    """
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return [
        f"not in any table: {name}" for name in _unlisted_migrations(releases, root)
    ]


def release_manifest_addition(
    manifest: Path, root: Path, tag: str, *, header: bool = True
) -> str:
    """The released.toml lines that would list every unlisted migration under `tag`.

    The `["tag"]` header comes first when `tag` has no table yet, unless
    `header` is False.
    """
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    lines: list[str] = [f'["{tag}"]'] if header and tag not in releases else []
    lines.extend(
        f'"{name}" = "{_released_hash(root / name)}"'
        for name in _unlisted_migrations(releases, root)
    )
    return "\n".join(lines) + "\n"


def release_manifest_summary(
    manifest: Path, root: Path, tag: str, *, released: bool = False
) -> str:
    """The Markdown a GitHub Actions job summary shows when `tag` can't be cut.

    `released` says `tag` already exists; only the workflow can know that.
    """
    releases = tomllib.loads(manifest.read_text(encoding="utf-8"))
    problems = "".join(
        f"- not in any table: `{name}`\n"
        for name in _unlisted_migrations(releases, root)
    )
    # A released tag's lines go under the next version's header, never its own.
    addition = release_manifest_addition(manifest, root, tag, header=not released)
    path = "`src/budget/migrations/released.toml`"
    heading = f"## Release manifest incomplete for `{tag}`\n\n{problems}\n"
    if released:
        return (
            f"{heading}`{tag}` is already released, and its table is frozen. Bump "
            "the version in `pyproject.toml`, then add these lines as its new "
            f'table:\n\n```toml\n["v<new version>"]\n{addition}```\n'
        )
    lines = f"```toml\n{addition}```\n"
    if tag not in releases:
        return f"{heading}Add these lines to the end of {path}:\n\n{lines}"
    return f'{heading}Add these lines under `["{tag}"]` in {path}:\n\n{lines}'


def release_manifest_annotations(manifest: Path, root: Path) -> list[str]:
    """One GitHub Actions error annotation per reason `tag` can't be cut."""
    error = "::error file=src/budget/migrations/released.toml,"
    error += "title=Release manifest incomplete::"
    return [f"{error}{gap}" for gap in release_manifest_gaps(manifest, root)]


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


def test_the_job_summary_for_changed_released_migrations_says_to_restore_them(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / BRONZE).unlink()
    (tmp_path / SILVER).write_bytes(
        b"CREATE TABLE evidence (id INTEGER PRIMARY KEY, note TEXT) STRICT;\n"
    )

    assert released_drift_summary(manifest, tmp_path) == (
        "## Released migrations changed\n"
        "\n"
        "- `bronze/0001_create_bronze_store.sql`\n"
        "- `silver/0001_create_silver_store.sql`\n"
        "\n"
        "A released migration is frozen: stores already past it never see a "
        "change. Restore each file as `released.toml` records it, and put the "
        "change in a new migration.\n"
    )


def test_a_release_that_adds_no_migration_needs_no_table(tmp_path: Path) -> None:
    # Every file is already frozen by the table of the release that first
    # shipped it, so cutting v0.3.0 with no ["v0.3.0"] table finds no gaps.
    manifest = _released_tree(tmp_path)

    assert release_manifest_gaps(manifest, tmp_path) == []


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

    assert release_manifest_gaps(manifest, tmp_path) == [
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


def test_a_tag_with_no_table_names_only_each_migration_in_no_table(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_gaps(manifest, tmp_path) == [
        "not in any table: silver/0002_add_note.sql",
    ]


def test_the_job_summary_marks_tags_and_paths_as_code(
    tmp_path: Path,
) -> None:
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_summary(manifest, tmp_path, "v0.3.0") == (
        "## Release manifest incomplete for `v0.3.0`\n"
        "\n"
        "- not in any table: `silver/0002_add_note.sql`\n"
        "\n"
        "Add these lines to the end of `src/budget/migrations/released.toml`:\n"
        "\n"
        "```toml\n"
        '["v0.3.0"]\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
    )


def test_the_job_summary_for_a_tag_with_a_table_says_to_add_the_lines_under_it(
    tmp_path: Path,
) -> None:
    # Whether the tag is already released is for the Release workflow to say:
    # these tests read no tags, so the summary makes no guess about it.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    assert release_manifest_summary(manifest, tmp_path, "v0.2.0") == (
        "## Release manifest incomplete for `v0.2.0`\n"
        "\n"
        "- not in any table: `silver/0002_add_note.sql`\n"
        "\n"
        'Add these lines under `["v0.2.0"]` in '
        "`src/budget/migrations/released.toml`:\n"
        "\n"
        "```toml\n"
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
    )


def test_the_job_summary_for_a_released_tag_says_to_bump_and_start_a_new_table(
    tmp_path: Path,
) -> None:
    # A rehearsal before the version bump checks the last release's tag. Its
    # table is frozen, so the lines belong in the next version's new table.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    summary = release_manifest_summary(manifest, tmp_path, "v0.2.0", released=True)

    assert summary == (
        "## Release manifest incomplete for `v0.2.0`\n"
        "\n"
        "- not in any table: `silver/0002_add_note.sql`\n"
        "\n"
        "`v0.2.0` is already released, and its table is frozen. Bump the version "
        "in `pyproject.toml`, then add these lines as its new table:\n"
        "\n"
        "```toml\n"
        '["v<new version>"]\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
    )


def test_the_job_summary_for_a_released_tag_with_no_table_has_only_the_new_header(
    tmp_path: Path,
) -> None:
    # v0.3.0 was released without adding a migration, so it has no table. Its
    # own header in the paste block would put the new files under a released tag.
    manifest = _released_tree(tmp_path)
    (tmp_path / "silver" / "0002_add_note.sql").write_bytes(
        b"ALTER TABLE evidence ADD COLUMN note TEXT;\n"
    )

    summary = release_manifest_summary(manifest, tmp_path, "v0.3.0", released=True)

    assert summary.endswith(
        "```toml\n"
        '["v<new version>"]\n'
        '"silver/0002_add_note.sql" = '
        '"5de046400308f01755df18cb8c5d6e5aa3aecf176d6cfd14b9d822bfb6ce5fe2"\n'
        "```\n"
    )


def test_each_problem_becomes_an_error_annotation_on_released_toml(
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

    error = "::error file=src/budget/migrations/released.toml,"
    error += "title=Release manifest incomplete::"
    assert release_manifest_annotations(manifest, tmp_path) == [
        f"{error}not in any table: gold/0001_create_gold_store.sql",
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


def _report_to_github_actions(manifest: Path, tag: str) -> None:
    """On GitHub Actions, annotate the run and write the paste lines to its summary."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    # pytest replays a failing test's stdout line by line, so GitHub still
    # reads each annotation as a workflow command.
    for annotation in release_manifest_annotations(manifest, MIGRATIONS):
        sys.stdout.write(f"{annotation}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as job_summary:
            # The Release workflow's version step sets this when the tag exists.
            released = os.environ.get("RELEASE_TAG_RELEASED") == "true"
            job_summary.write(
                release_manifest_summary(manifest, MIGRATIONS, tag, released=released)
            )


@pytest.mark.release
def test_every_migration_is_in_a_table_before_a_release() -> None:
    # Main keeps the last release's version while unreleased migrations pile
    # up, so only the Release workflow, which sets RELEASE_TAG, can check this.
    tag = os.environ.get("RELEASE_TAG")
    if not tag:
        pytest.skip("RELEASE_TAG is not set; the Release workflow sets it")
    manifest = MIGRATIONS / "released.toml"

    gaps = release_manifest_gaps(manifest, MIGRATIONS)

    if gaps:
        _report_to_github_actions(manifest, tag)
    assert not gaps, "\n".join(
        [
            *gaps,
            "Add these lines to src/budget/migrations/released.toml:",
            release_manifest_addition(manifest, MIGRATIONS, tag),
        ]
    )
