# Copyright 2026 Therkel
"""The `budget` command line.

Nothing selects a profile implicitly: a command runs only when `--profile` or
the `BUDGET_PROFILE` environment variable names a profile file. The caller
passes the environment in, so a test never inherits the operator's shell.
"""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NoReturn

from budget.backups import (
    BackupVerificationError,
    BackupWriteError,
    UnsupportedStoresError,
    back_up,
)
from budget.bronze import require_migration_allowed
from budget.bronze.storage import (
    BRONZE_STAGE,
    MigrationRequiredError,
    NewStoreRefusedError,
    NewStoreRequiredError,
    ProductionMigrationBlockedError,
    StoreBusyError,
    StoreIdentityError,
    StoreNotFoundError,
    UnsupportedSQLiteVersionError,
    UnsupportedStoreVersionError,
    UnversionedStoreError,
)
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.locking import (
    StoresFolderUnavailableError,
    WriterLockHeldError,
    writer_lock,
)
from budget.migration import (
    MigratedWithoutBackupError,
    RestoreInsteadError,
    migrate_profile,
)
from budget.profiles import (
    NoBackupsFolderError,
    Profile,
    ProfileFileError,
    load_profile_file,
)

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
STAGES: Final = (BRONZE_STAGE, "silver", "gold")
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_REFUSED_INPUT: Final = 3
EXIT_REFUSED_ENVIRONMENT: Final = 4
EXIT_VERIFICATION_FAILED: Final = 5
# The Bronze errors operations.md lists as a refused environment. Any other
# Bronze error, such as a broken packaged migration, is a defect: exit 1.
_BRONZE_ENVIRONMENT_REFUSALS: Final = (
    UnsupportedSQLiteVersionError,
    ProductionMigrationBlockedError,
    NewStoreRequiredError,
    NewStoreRefusedError,
    StoreNotFoundError,
    StoreBusyError,
    UnversionedStoreError,
    StoreIdentityError,
    MigrationRequiredError,
    UnsupportedStoreVersionError,
)


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
    # Kept as text: `Path("")` is `.`, which would hide an empty argument.
    parser.add_argument("--profile", help="the profile file to use")
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser(
        "migrate", help="create or upgrade the profile's stores"
    )
    migrate.add_argument("--stage", choices=STAGES, help="migrate one stage only")
    migrate.add_argument(
        "--new-store",
        action="store_true",
        help="start a new production store where none exists",
    )
    commands.add_parser("backup", help="write a backup set of production")
    return parser


def _selected_profile_file(
    argument: str | None,
    environ: Mapping[str, str],
) -> Path:
    """Return the profile file named by `--profile`, else by `BUDGET_PROFILE`.

    An empty name selects nothing, and an empty `--profile` is still the
    operator's choice, so it does not fall through to the variable.
    """
    name = environ.get(PROFILE_VARIABLE) if argument is None else argument
    if not name:
        raise NoProfileSelectedError
    return Path(name)


def _migrate(profile: Profile, stage: str | None, *, new_store: bool) -> None:
    """Create or upgrade the stores this code has: Bronze, for now."""
    if stage not in {None, BRONZE_STAGE}:
        raise StageNotBuiltError(stage)
    # Refusals that touch nothing come first; the lock guards the mutation.
    require_migration_allowed(profile, new_store=new_store)
    with writer_lock(profile) as lock:
        migrate_profile(lock, new_store=new_store)


def _backup(profile: Profile) -> None:
    """Write one backup set, and name it on stdout."""
    # Refusals that touch nothing come first; the lock guards the set.
    if profile.backups is None:
        raise NoBackupsFolderError(profile.name)
    if not profile.bronze_store.exists():
        raise StoreNotFoundError(profile.bronze_store)
    with writer_lock(profile) as lock:
        written = back_up(lock, now=datetime.now(UTC))
    sys.stdout.write(f"backup set {written.name} written\n")


def _run(arguments: argparse.Namespace, environ: Mapping[str, str]) -> None:
    """Select and load the profile, then run the command against it."""
    profile_file = _selected_profile_file(arguments.profile, environ)
    profile = load_profile_file(profile_file)
    if arguments.command == "backup":
        _backup(profile)
        return
    _migrate(profile, arguments.stage, new_store=arguments.new_store)


def _refuse(error: Exception, status: int) -> int:
    """Report a refusal on stderr and return its exit status."""
    sys.stderr.write(f"budget: {error}\n")
    return status


def main(argv: Sequence[str], *, environ: Mapping[str, str]) -> int:
    """Run one command and return its exit status.

    A refusal is reported on stderr with its exit status. Anything else
    propagates: an unexpected error is a defect, and Python exits 1.
    """
    try:
        arguments = _parser().parse_args(argv)
    except SystemExit as usage:
        # argparse has already printed the usage or help; return its status
        # (2 for a usage error, 0 for --help) instead of leaving the process.
        return usage.code if isinstance(usage.code, int) else EXIT_USAGE
    try:
        _run(arguments, environ)
    except ProfileFileError as error:
        return _refuse(error, EXIT_REFUSED_INPUT)
    except (
        NoProfileSelectedError,
        StageNotBuiltError,
        WriterLockHeldError,
        StoresFolderUnavailableError,
        RestoreInsteadError,
        MigratedWithoutBackupError,
        BackupWriteError,
        UnsupportedStoresError,
        NoBackupsFolderError,
        *_BRONZE_ENVIRONMENT_REFUSALS,
    ) as error:
        return _refuse(error, EXIT_REFUSED_ENVIRONMENT)
    except (
        BackupVerificationError,
        ImportLogDamagedError,
        ImportLogAheadOfBronzeError,
    ) as error:
        return _refuse(error, EXIT_VERIFICATION_FAILED)
    return EXIT_OK


def run() -> NoReturn:
    """Run the installed `budget` command with this process's own environment.

    This is the only place that reads `os.environ` or `sys.argv`; `main` is
    given both, so a test never inherits the operator's shell.
    """
    sys.exit(main(sys.argv[1:], environ=os.environ))
