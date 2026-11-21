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
