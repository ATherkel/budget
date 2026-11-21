# Copyright 2026 Therkel
"""The repository's djlint settings keep template lines to 120 characters."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.cli.processes import explicit_environment

REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_FILES = ("pyproject.toml", ".djlint_rules.yaml")


def lint(tmp_path: Path, line: str) -> subprocess.CompletedProcess[str]:
    """Lint a one-line template under the repository's djlint settings."""
    for name in CONFIG_FILES:
        shutil.copy(REPOSITORY / name, tmp_path / name)
    (tmp_path / "page.html").write_text(line + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "djlint", str(tmp_path / "page.html"), "--lint"],
        capture_output=True,
        text=True,
        check=False,
        env=explicit_environment(),
    )


def long_template_lines(root: Path) -> list[str]:
    """Return `path:line` for each template line under `root` over 120 characters.

    djlint drops a match that overlaps a comment, so its rule alone lets a long
    line through when it holds one; this reads the lines themselves.
    """
    return [
        f"{path.relative_to(root)}:{number}"
        for path in sorted(root.rglob("*.html"))
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if len(line) > 120
    ]


def paragraph(length: int) -> str:
    """Return a `<p>` element exactly `length` characters long."""
    return "<p>" + "x" * (length - len("<p></p>")) + "</p>"


def test_a_template_line_over_120_characters_fails_the_lint(tmp_path: Path) -> None:
    result = lint(tmp_path, paragraph(121))

    assert result.returncode == 1, result.stdout
    assert "longer than 120 characters" in result.stdout


@pytest.mark.parametrize("length", [80, 120])
def test_a_template_line_of_at_most_120_characters_passes(
    tmp_path: Path, length: int
) -> None:
    result = lint(tmp_path, paragraph(length))

    assert result.returncode == 0, result.stdout


def test_a_long_template_line_with_a_comment_is_still_too_long(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "templates"
    folder.mkdir()
    comment = "{# n #}"
    lines = [
        paragraph(120 - len(comment)) + comment,
        paragraph(121 - len(comment)) + comment,
    ]
    (folder / "page.html").write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert long_template_lines(tmp_path) == [str(Path("templates/page.html")) + ":2"]
