# Copyright 2026 Therkel
"""The `budget` command line.

Nothing selects a profile implicitly: a command runs only when `--profile` or
the `BUDGET_PROFILE` environment variable names a profile file. The caller
passes the environment in, so a test never inherits the operator's shell.
"""

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from budget.bronze import migrate_bronze
from budget.profiles import load_profile_file

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
EXIT_REFUSED_ENVIRONMENT: Final = 4


class NoProfileSelectedError(Exception):
    """Neither `--profile` nor `BUDGET_PROFILE` names a profile file."""

    def __init__(self) -> None:
        """Say how to select a profile, since there is no default."""
        super().__init__(
            f"no profile selected: pass --profile <file> or set {PROFILE_VARIABLE}"
        )


def _parser() -> argparse.ArgumentParser:
    """Build the command-line grammar."""
    parser = argparse.ArgumentParser(prog="budget")
    parser.add_argument("--profile", type=Path, help="the profile file to use")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="create or upgrade the profile's stores")
    return parser


def main(argv: Sequence[str], *, environ: Mapping[str, str]) -> int:
    """Run one command and return its exit status."""
    arguments = _parser().parse_args(argv)
    if arguments.profile is None and PROFILE_VARIABLE not in environ:
        sys.stderr.write(f"budget: {NoProfileSelectedError()}\n")
        return EXIT_REFUSED_ENVIRONMENT
    if arguments.profile is not None:
        migrate_bronze(load_profile_file(arguments.profile))
    return 0
