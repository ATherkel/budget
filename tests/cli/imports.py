# Copyright 2026 Therkel
"""What a `budget import` test needs besides the inbox: Git and a ranges file."""

from pathlib import Path
from unittest import mock


def clean_git() -> mock.Mock:
    """A finished Git call reporting a clean, tracked checkout."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = ""
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


COMMIT = "0123456789abcdef0123456789abcdef01234567\n"


def clean_checkout(arguments: list[str], **_: object) -> mock.Mock:
    """Answer Git as a clean, tracked checkout at one commit does."""
    completed = clean_git()
    if "rev-parse" in arguments:
        completed.stdout = COMMIT
    return completed
