# Copyright 2026 Therkel
"""What a `budget import` test needs besides the inbox: Git and a ranges file."""

from pathlib import Path
from unittest import mock

SYNTHETIC_COMMIT = "a" * 40


def clean_git() -> mock.Mock:
    """A finished Git call reporting a clean, tracked checkout."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = ""
    completed.stderr = ""
    return completed


def clean_git_run(status: str = "") -> mock.Mock:
    """A `subprocess.run` side effect for tracked, clean production code."""

    def run(arguments: list[str], **_: object) -> mock.Mock:
        stdout = SYNTHETIC_COMMIT if "rev-parse" in arguments else status
        return _completed(stdout)

    return mock.Mock(side_effect=run)


def _completed(stdout: str) -> mock.Mock:
    """Return one successful Git process."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = stdout
    completed.stderr = ""
    return completed


def write_ranges(
    folder: Path,
    default: tuple[str, str] | None = None,
    accounts: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Write a ranges file: a default range and per-account ranges."""
    lines = ["format = 1"]
    if default is not None:
        lines += ["", "[default]", f"from = {default[0]}", f"through = {default[1]}"]
    for account_id, (start, end) in (accounts or {}).items():
        lines += ["", f"[account.{account_id}]", f"from = {start}", f"through = {end}"]
    path = folder / "ranges.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
