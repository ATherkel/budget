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
from budget.profiles import ProfileFileError, load_profile_file

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
EXIT_REFUSED_INPUT: Final = 3
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


def _selected_profile_file(
    argument: Path | None,
    environ: Mapping[str, str],
) -> Path:
    """Return the profile file named by `--profile`, else by `BUDGET_PROFILE`."""
    if argument is not None:
        return argument
    if PROFILE_VARIABLE in environ:
        return Path(environ[PROFILE_VARIABLE])
    raise NoProfileSelectedError


def main(argv: Sequence[str], *, environ: Mapping[str, str]) -> int:
    """Run one command and return its exit status."""
    arguments = _parser().parse_args(argv)
    try:
        profile_file = _selected_profile_file(arguments.profile, environ)
    except NoProfileSelectedError as error:
        sys.stderr.write(f"budget: {error}\n")
        return EXIT_REFUSED_ENVIRONMENT
    try:
        profile = load_profile_file(profile_file)
    except ProfileFileError as error:
        sys.stderr.write(f"budget: {error}\n")
        return EXIT_REFUSED_INPUT
    migrate_bronze(profile)
    return 0
