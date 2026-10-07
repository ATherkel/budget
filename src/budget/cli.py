# Copyright 2026 Therkel
"""The `budget` command line.

Nothing selects a profile implicitly: a command runs only when `--profile` or
the `BUDGET_PROFILE` environment variable names a profile file. The caller
passes the environment in, so a test never inherits the operator's shell.
"""

import argparse
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Final, NoReturn

from budget import routine_logging, sqlstore, summaries
from budget.backups import (
    BackupVerificationError,
    BackupWriteError,
    LostStoreError,
    UnsupportedStoresError,
    back_up,
)
from budget.bronze.storage import BRONZE_STAGE, bronze_stage
from budget.codeversion import UncommittedCodeError, require_committed_code
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.inbox import import_inbox, inbox_exports, preview
from budget.inputs import ConfigurationError
from budget.locking import (
    StoresFolderUnavailableError,
    WriterLockHeldError,
    writer_lock,
)
from budget.migration import (
    MIGRATED_STAGES,
    MigratedWithoutBackupError,
    RestoreInsteadError,
    migrate_profile,
    require_migration_allowed,
)
from budget.profiles import (
    NoBackupsFolderError,
    Profile,
    ProfileFileError,
    load_profile_file,
)
from budget.ranges import load_ranges
from budget.rebuilding import SilverRebuild, rebuild_from_silver
from budget.reviewing import REVIEW_KINDS, open_reviews
from budget.silver.storage import SILVER_STAGE

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
GOLD_STAGE: Final = "gold"
STAGES: Final = (BRONZE_STAGE, SILVER_STAGE, GOLD_STAGE)
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_REFUSED_INPUT: Final = 3
EXIT_REFUSED_ENVIRONMENT: Final = 4
EXIT_VERIFICATION_FAILED: Final = 5
# The store errors operations.md lists as a refused environment, for every
# stage. Any other store error, such as a broken packaged migration, is a
# defect: exit 1.
_STORE_ENVIRONMENT_REFUSALS: Final = (
    sqlstore.UnsupportedSQLiteVersionError,
    sqlstore.ProductionMigrationBlockedError,
    sqlstore.NewStoreRequiredError,
    sqlstore.NewStoreRefusedError,
    sqlstore.StoreNotFoundError,
    sqlstore.StoreBusyError,
    sqlstore.UnversionedStoreError,
    sqlstore.StoreIdentityError,
    sqlstore.MigrationRequiredError,
    sqlstore.UnsupportedStoreVersionError,
)


class StageNotBuiltError(Exception):
    """The named stage has no store in this code yet."""

    def __init__(self, stage: str) -> None:
        """Name the stage, rather than pretend to migrate it."""
        super().__init__(
            f"the {stage} stage is not built yet: only {BRONZE_STAGE} and "
            f"{SILVER_STAGE} can be migrated"
        )


class NoProfileSelectedError(Exception):
    """Neither `--profile` nor `BUDGET_PROFILE` names a profile file."""

    def __init__(self) -> None:
        """Say how to select a profile, since there is no default."""
        super().__init__(
            f"no profile selected: pass --profile <file> or set {PROFILE_VARIABLE}"
        )


class RebuildFromStageNotBuiltError(Exception):
    """The stage a rebuild would read from has no reader in this code yet."""

    def __init__(self, stage: str) -> None:
        """Name the one stage reading that exists, rather than pretend."""
        super().__init__(
            f"rebuilding from {stage} is not built yet: only --from {SILVER_STAGE} is"
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
    rebuild = commands.add_parser("rebuild", help="rebuild a stage and every later one")
    rebuild.add_argument(
        "--from",
        dest="from_stage",
        choices=STAGES,
        default=GOLD_STAGE,
        help="the stage to rebuild from",
    )
    import_ = commands.add_parser(
        "import", help="import every inbox export, then rebuild Silver"
    )
    import_.add_argument(
        "--ranges",
        required=True,
        help="a file declaring the range each account's exports were asked for",
    )
    review = commands.add_parser("review", help="list the open review items")
    review.add_argument("--kind", choices=REVIEW_KINDS, help="list one kind only")
    review.add_argument("--account", help="list one account's items only")
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
    """Create or upgrade the stores this code has: Bronze and Silver, for now."""
    if stage is not None and stage not in MIGRATED_STAGES:
        raise StageNotBuiltError(stage)
    stages = MIGRATED_STAGES if stage is None else (stage,)
    # Refusals that touch nothing come first; the lock guards the mutation.
    require_migration_allowed(profile, stages=stages, new_store=new_store)
    with writer_lock(profile) as lock:
        migrate_profile(lock, stages=stages, new_store=new_store)


def _backup(profile: Profile) -> None:
    """Write one backup set, and name it on stdout."""
    # Refusals that touch nothing come first; the lock guards the set.
    if profile.backups is None:
        raise NoBackupsFolderError(profile.name)
    bronze = bronze_stage(profile)
    if not bronze.path.exists():
        raise sqlstore.StoreNotFoundError(bronze.label, bronze.path)
    with writer_lock(profile) as lock:
        written = back_up(lock, now=datetime.now(UTC))
    sys.stdout.write(f"backup set {written.name} written\n")


def _rebuild(profile: Profile, from_stage: str) -> None:
    """Rebuild `from_stage` and every later stage, under one writer lock.

    The whole command holds the profile's writer lock, so the inputs it reads
    from the stages before `from_stage` cannot change between the read and the
    replacement it writes, and the summary and completion log belong to that
    same lock.
    """
    if from_stage != SILVER_STAGE:
        raise RebuildFromStageNotBuiltError(from_stage)
    started = perf_counter()
    with writer_lock(profile) as lock:
        require_committed_code(lock.profile)
        rebuilt = rebuild_from_silver(lock)
        summary = summaries.rebuild_summary(rebuilt)
        routine_logging.finished(
            profile,
            "rebuild",
            counts=_rebuild_counts(rebuilt),
            duration_ms=_milliseconds(started),
        )
        sys.stdout.write(summary)


def _import(profile: Profile, ranges_file: str) -> int:
    """Import every inbox export with its declared range, then rebuild Silver.

    Returns 3 when any file was refused and stays in the inbox, else 0.
    """
    ranges = load_ranges(Path(ranges_file))
    with writer_lock(profile) as lock:
        coverages = []
        for source in inbox_exports(profile):
            coverage = ranges.coverage(source.parent.name)
            if coverage is not None:
                coverages.append((preview(profile, source), coverage))
        imported = import_inbox(lock, coverages)
        sys.stdout.write(summaries.import_summary(imported))
    return EXIT_REFUSED_INPUT if imported.any_left_in_inbox else EXIT_OK


def _review(profile: Profile, kind: str | None, account: str | None) -> None:
    """List the profile's open review items, taking no writer lock.

    Review only reads the persisted Silver result, so it neither locks nor
    needs a Bronze store or `accounts.toml`.
    """
    started = perf_counter()
    items = open_reviews(profile, kind=kind, account=account)
    summary = summaries.review_summary(items)
    routine_logging.finished(
        profile,
        "review",
        counts={"items": len(items)},
        duration_ms=_milliseconds(started),
        kinds=tuple(sorted({entry.item.kind for entry in items})),
    )
    sys.stdout.write(summary)


def _rebuild_counts(rebuilt: SilverRebuild) -> dict[str, int]:
    """Return the rebuild counts a routine log records, and nothing else."""
    outcomes = Counter(run.outcome for run in rebuilt.runs)
    return {
        "stored": outcomes["stored"],
        "repeat": outcomes["repeat"],
        "refused": outcomes["refused"],
        "review_open": sum(
            1 for item in rebuilt.result.review_items if item.resolved_by is None
        ),
    }


def _milliseconds(started: float) -> int:
    """Whole milliseconds since `started`, as a log records a duration."""
    return int((perf_counter() - started) * 1000)


def _run(arguments: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Select and load the profile, run the command, and return its status."""
    profile_file = _selected_profile_file(arguments.profile, environ)
    profile = load_profile_file(profile_file)
    if arguments.command == "import":
        return _import(profile, arguments.ranges)
    if arguments.command == "backup":
        _backup(profile)
    elif arguments.command == "rebuild":
        _rebuild(profile, arguments.from_stage)
    elif arguments.command == "review":
        _review(profile, arguments.kind, arguments.account)
    else:
        _migrate(profile, arguments.stage, new_store=arguments.new_store)
    return EXIT_OK


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
        return _run(arguments, environ)
    except (ProfileFileError, ConfigurationError) as error:
        return _refuse(error, EXIT_REFUSED_INPUT)
    except (
        NoProfileSelectedError,
        StageNotBuiltError,
        RebuildFromStageNotBuiltError,
        UncommittedCodeError,
        WriterLockHeldError,
        StoresFolderUnavailableError,
        RestoreInsteadError,
        MigratedWithoutBackupError,
        BackupWriteError,
        UnsupportedStoresError,
        LostStoreError,
        NoBackupsFolderError,
        *_STORE_ENVIRONMENT_REFUSALS,
    ) as error:
        return _refuse(error, EXIT_REFUSED_ENVIRONMENT)
    except (
        BackupVerificationError,
        ImportLogDamagedError,
        ImportLogAheadOfBronzeError,
    ) as error:
        return _refuse(error, EXIT_VERIFICATION_FAILED)


def run() -> NoReturn:
    """Run the installed `budget` command with this process's own environment.

    This is the only place that reads `os.environ` or `sys.argv`; `main` is
    given both, so a test never inherits the operator's shell.
    """
    sys.exit(main(sys.argv[1:], environ=os.environ))
