# Copyright 2026 Therkel
"""Run `budget` commands in-process, with an explicit, empty environment."""

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from budget.cli import main


def migrate(profile_file: Path, *options: str) -> tuple[int, str]:
    """Run `budget migrate` with one profile file; return status and stderr."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        status = main(["--profile", str(profile_file), "migrate", *options], environ={})
    return status, stderr.getvalue()


def backup(profile_file: Path) -> tuple[int, str, str]:
    """Run `budget backup` with one profile file; return status and output."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(["--profile", str(profile_file), "backup"], environ={})
    return status, stdout.getvalue(), stderr.getvalue()
