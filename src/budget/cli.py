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

from budget.bronze import BronzeStorageError, migrate_bronze
from budget.bronze.storage import BRONZE_STAGE
from budget.profiles import Profile, ProfileFileError, load_profile_file

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
STAGES: Final = (BRONZE_STAGE, "silver", "gold")
EXIT_OK: Final = 0
EXIT_REFUSED_INPUT: Final = 3
EXIT_REFUSED_ENVIRONMENT: Final = 4


class StageNotBuiltError(Exception):
    """The named stage has no store in this code yet."""

    def __init__(self, stage: str) -> None:
        """Name the stage, rather than pretend to migrate it."""
        super().__init__(
            f"the {stage} stage is not built yet: only {BRONZE_STAGE} can be migrated"
        )


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
    migrate = commands.add_parser(
        "migrate", help="create or upgrade the profile's stores"
    )
    migrate.add_argument("--stage", choices=STAGES, help="migrate one stage only")
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


def _migrate(profile: Profile, stage: str | None) -> None:
    """Create or upgrade the stores this code has: Bronze, for now."""
    if stage not in {None, BRONZE_STAGE}:
        raise StageNotBuiltError(stage)
    migrate_bronze(profile)


def _run(arguments: argparse.Namespace, environ: Mapping[str, str]) -> None:
    """Select and load the profile, then run the command against it."""
    profile_file = _selected_profile_file(arguments.profile, environ)
    profile = load_profile_file(profile_file)
    _migrate(profile, arguments.stage)


def _refuse(error: Exception, status: int) -> int:
    """Report a refusal on stderr and return its exit status."""
    sys.stderr.write(f"budget: {error}\n")
    return status


def main(argv: Sequence[str], *, environ: Mapping[str, str]) -> int:
    """Run one command and return its exit status.

    A refusal is reported on stderr with its exit status. Anything else
    propagates: an unexpected error is a defect, and Python exits 1.
    """
    arguments = _parser().parse_args(argv)
    try:
        _run(arguments, environ)
    except ProfileFileError as error:
        return _refuse(error, EXIT_REFUSED_INPUT)
    except (NoProfileSelectedError, StageNotBuiltError, BronzeStorageError) as error:
        return _refuse(error, EXIT_REFUSED_ENVIRONMENT)
    return EXIT_OK
