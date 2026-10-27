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

import uvicorn

from budget import routine_logging, sqlstore, summaries
from budget.backups import (
    BACKUP_FAILURES,
    BackupVerificationError,
    BackupWriteError,
    LostStoreError,
    UnsupportedStoresError,
    back_up,
    require_backup_allowed,
)
from budget.bronze.parsers.registry import UnsupportedSourceFormatError
from budget.bronze.storage import BRONZE_STAGE, bronze_stage
from budget.bronze.store import ConflictingDeclaredFormatsError
from budget.codeversion import UncommittedCodeError, require_committed_code
from budget.dashboard import create_app
from budget.dashboard.passphrase import PassphraseNotSetError, set_passphrase
from budget.demo import DEFAULT_DEMO_PORT, DemoDirectoryExistsError, create_demo_profile
from budget.gold.storage import GOLD_STAGE
from budget.importing import (
    Coverage,
    ImportLogAheadOfBronzeError,
    ImportLogDamagedError,
)
from budget.inbox import (
    ExportPreview,
    ImportedInbox,
    cross_account_duplicates,
    import_inbox,
    inbox_exports,
    incident_files,
    preview,
    require_import_allowed,
    require_importable,
)
from budget.inputs import Account, ConfigurationError, load_accounts
from budget.locking import (
    StoresFolderUnavailableError,
    WriterLock,
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
    PRODUCTION_PROFILE_NAME,
    NoBackupsFolderError,
    Profile,
    ProfileFileError,
    load_profile_file,
)
from budget.prompting import ask_continue_after_duplicates, ask_passphrase, ask_ranges
from budget.ranges import load_ranges
from budget.rebuilding import (
    HouseholdInputs,
    SilverNotBuiltError,
    SilverRebuild,
    read_household_inputs,
    rebuild_from_gold,
    rebuild_through_gold,
    require_buildable_accounts,
)
from budget.reviewing import REVIEW_KINDS, open_reviews
from budget.silver.storage import SILVER_STAGE

PROFILE_VARIABLE: Final = "BUDGET_PROFILE"
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_REFUSED_INPUT: Final = 3
EXIT_REFUSED_ENVIRONMENT: Final = 4
EXIT_VERIFICATION_FAILED: Final = 5
# The port in operations.md's example profile, for a profile that names none.
DEFAULT_DASHBOARD_PORT: Final = 8750
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


class NoProfileSelectedError(Exception):
    """Neither `--profile` nor `BUDGET_PROFILE` names a profile file."""

    def __init__(self) -> None:
        """Say how to select a profile, since there is no default."""
        super().__init__(
            f"no profile selected: pass --profile <file> or set {PROFILE_VARIABLE}"
        )


class ImportedWithoutBackupError(Exception):
    """The imports, Silver and Gold are committed, but no backup set followed."""

    def __init__(self, reason: Exception) -> None:
        """Say what was done, what was not, and what to run."""
        super().__init__(
            "the exports were imported, Silver rebuilt and Gold published, but "
            f"no backup set could be written after them: {reason}. Put that "
            "right, then run `budget backup`"
        )


class RebuiltWithoutBackupError(Exception):
    """The rebuild is committed, but no backup set followed it."""

    def __init__(self, reason: Exception) -> None:
        """Say what was done, what was not, and what to run."""
        super().__init__(
            "the stores were rebuilt, but no backup set could be written after "
            f"them: {reason}. Put that right, then run `budget backup`"
        )


class ImportedWithoutPublicationError(Exception):
    """The imports are committed, but Silver and Gold were not rebuilt from them."""

    def __init__(
        self, held_back: ConfigurationError, backup_failure: Exception | None
    ) -> None:
        """Say what was done, what stopped, and which command finishes it."""
        message = (
            "the exports were imported into Bronze, but Silver and Gold were not "
            f"rebuilt: {'; '.join(held_back.problems)}. Put that right, then run "
            "`budget import` again: it finishes the rebuild, the publication and "
            "the backup, whether or not the inbox holds files"
        )
        if backup_failure is not None:
            message += f". No backup set could be written either: {backup_failure}"
        super().__init__(message)


class PassphraseMismatchError(Exception):
    """The passphrase and its confirmation differ, so neither is stored."""

    def __init__(self) -> None:
        """Say why nothing changed, without repeating what was typed."""
        super().__init__(
            "the two passphrases do not match; the dashboard passphrase is unchanged"
        )


class NoPassphraseFileError(Exception):
    """The profile names nowhere to keep the dashboard passphrase."""

    def __init__(self, profile: str) -> None:
        """Name the setting the profile file needs."""
        super().__init__(
            f"the {profile} profile names no [dashboard] passphrase_file; "
            "add it to the profile file first"
        )


class NoPassphraseTypedError(Exception):
    """The input ended before the passphrase and its confirmation were read."""

    def __init__(self) -> None:
        """Say why nothing changed."""
        super().__init__(
            "no passphrase was typed, or no confirmation; "
            "the dashboard passphrase is unchanged"
        )


class EmptyPassphraseError(Exception):
    """An empty passphrase would guard the dashboard with nothing."""

    def __init__(self) -> None:
        """Say why nothing changed."""
        super().__init__(
            "the passphrase is empty; the dashboard passphrase is unchanged"
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
    migrate.add_argument(
        "--stage", choices=MIGRATED_STAGES, help="migrate one stage only"
    )
    migrate.add_argument(
        "--new-store",
        action="store_true",
        help="start a new production store where none exists",
    )
    commands.add_parser("backup", help="write a backup set of production")
    commands.add_parser("restore", help="restore a whole profile from a backup set")
    rebuild = commands.add_parser("rebuild", help="rebuild a stage and every later one")
    rebuild.add_argument(
        "--from",
        dest="from_stage",
        choices=MIGRATED_STAGES,
        default=GOLD_STAGE,
        help="the stage to rebuild from",
    )
    import_ = commands.add_parser(
        "import", help="import every inbox export, then rebuild Silver and Gold"
    )
    import_.add_argument(
        "--ranges",
        help="a file declaring the range each account's exports were asked "
        "for, instead of asking at the prompt",
    )
    review = commands.add_parser(
        "review", help="list the open review items and quarantined runs"
    )
    review.add_argument(
        "--kind", choices=REVIEW_KINDS, help="list one kind of item only, no runs"
    )
    review.add_argument("--account", help="list one account's items and runs only")
    commands.add_parser("serve", help="start the read-only dashboard")
    commands.add_parser(
        "set-passphrase",
        help="set the dashboard passphrase, which logs out every device",
    )
    demo = commands.add_parser(
        "demo",
        help="create an isolated synthetic development dashboard and start it",
    )
    demo.add_argument(
        "--directory",
        help="a new folder for this demo; defaults to a fresh temporary folder",
    )
    demo.add_argument("--port", type=int, default=DEFAULT_DEMO_PORT)
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
    """Create or upgrade the profile's stores: every stage, or the one named."""
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
    started = perf_counter()
    with writer_lock(profile) as lock:
        require_committed_code(lock.profile)
        if profile.name == PRODUCTION_PROFILE_NAME:
            require_backup_allowed(profile)
        inputs = read_household_inputs(lock.profile)
        now = datetime.now(UTC)
        summary = ""
        counts: dict[str, int] = {}
        if from_stage in {BRONZE_STAGE, SILVER_STAGE}:
            rebuilt = rebuild_through_gold(
                lock, now=now, inputs=inputs, from_bronze=from_stage == BRONZE_STAGE
            )
            summary = summaries.rebuild_summary(rebuilt.silver)
            counts = _rebuild_counts(rebuilt.silver)
            published = rebuilt.gold
        else:
            published = rebuild_from_gold(lock, now=now, inputs=inputs)
        routine_logging.finished(
            profile,
            "rebuild",
            counts={**counts, "published": int(published.published)},
            duration_ms=_milliseconds(started),
        )
        summary += summaries.gold_line(published) + "\n"
        # Every production write is followed by a set covering what it wrote;
        # a Gold rebuild that publishes nothing wrote nothing.
        wrote = from_stage != GOLD_STAGE or published.published
        if profile.name != PRODUCTION_PROFILE_NAME or not wrote:
            sys.stdout.write(summary)
            return
        try:
            written = back_up(lock, now=datetime.now(UTC))
        except BACKUP_FAILURES as error:
            sys.stdout.write(summary)
            raise RebuiltWithoutBackupError(error) from None
        sys.stdout.write(f"{summary}Backup   backup set {written.name} written\n")


def _declared_ranges(
    previews: Sequence[ExportPreview],
    accounts: Mapping[str, Account],
    ranges_file: str | None,
    excluded: frozenset[Path],
) -> dict[Path, Coverage] | None:
    """Settle every file's range: from the ranges file, or at the prompt.

    Returns `None` when the person did not confirm at the prompt. A ranges
    file is the person's written declaration, so it asks nothing. A file an
    incident holds is left out: it is not going to be imported, so it needs no
    declaration.
    """
    if ranges_file is None:
        return ask_ranges(previews, excluded)
    ranges = load_ranges(Path(ranges_file), accounts)
    return {
        each.source: ranges.declared(each)
        for each in previews
        if not each.skipped and each.source not in excluded
    }


def _import_files(
    lock: WriterLock,
    inputs: HouseholdInputs,
    previews: Sequence[ExportPreview],
    ranges_file: str | None,
) -> ImportedInbox | int:
    """Settle every range, then import the files; or return the exit status.

    A payload the inbox holds under more than one account is shown before the
    ranges are asked: nothing is imported unless the person goes on.
    """
    profile = lock.profile
    accounts = load_accounts(profile)
    require_buildable_accounts(
        profile, {each.account_id for each in previews if not each.skipped}
    )
    require_importable(inputs, previews)
    duplicates = cross_account_duplicates(previews)
    if duplicates and not ask_continue_after_duplicates(duplicates):
        sys.stdout.write("Nothing was imported.\n")
        return EXIT_REFUSED_INPUT
    excluded = incident_files(duplicates)
    declared = _declared_ranges(previews, accounts, ranges_file, excluded)
    if declared is None:
        sys.stdout.write("Nothing was imported.\n")
        return EXIT_OK
    return import_inbox(lock, previews, declared, duplicates, inputs)


def _import(profile: Profile, ranges_file: str | None) -> int:
    """Import every inbox export with its declared range, then rebuild.

    Every range is settled before the first file is stored. With an empty
    inbox, Bronze may still be ahead of Silver and Gold because an earlier
    import stopped after it stored; then this finishes the rebuild, the
    publication and production's backup. Returns 3 when any file stays in the
    inbox unimported, else 0.
    """
    started = perf_counter()
    with writer_lock(profile) as lock:
        inputs = require_import_allowed(profile)
        accounts = load_accounts(profile)
        previews = [
            preview(profile, accounts, source) for source in inbox_exports(profile)
        ]
        done = (
            _import_files(lock, inputs, previews, ranges_file)
            if previews
            else import_inbox(lock, (), {}, (), inputs)
        )
        if isinstance(done, int):
            return done
        if not previews and done.rebuilt is None and done.held_back is None:
            sys.stdout.write("The inbox holds no exports; nothing was imported.\n")
            return EXIT_OK
        sys.stdout.write(summaries.import_summary(done))
        routine_logging.finished(
            profile,
            "import",
            counts=done.counts(),
            duration_ms=_milliseconds(started),
        )
    if done.held_back is not None:
        raise ImportedWithoutPublicationError(done.held_back, done.backup_failure)
    if done.backup_failure is not None:
        raise ImportedWithoutBackupError(done.backup_failure)
    return EXIT_REFUSED_INPUT if done.any_left_in_inbox else EXIT_OK


def _review(profile: Profile, kind: str | None, account: str | None) -> None:
    """List the open review items and unshown quarantined runs, with no lock.

    Review only reads the persisted Silver result, so it neither locks nor
    needs a Bronze store or `accounts.toml`.
    """
    started = perf_counter()
    reviews = open_reviews(profile, kind=kind, account=account)
    summary = summaries.review_summary(reviews)
    routine_logging.finished(
        profile,
        "review",
        counts={
            "items": len(reviews.items),
            "gold_items": len(reviews.gold_items),
            "runs": len(reviews.runs),
        },
        duration_ms=_milliseconds(started),
        kinds=tuple(
            sorted(
                {
                    *(entry.item.kind for entry in reviews.items),
                    *(entry.item.kind for entry in reviews.gold_items),
                }
            )
        ),
    )
    sys.stdout.write(summary)


def _set_passphrase(profile: Profile) -> None:
    """Ask for the new dashboard passphrase twice, then store its hash."""
    # Refused before asking, so no one types a passphrase that cannot be kept.
    if profile.passphrase_file is None:
        raise NoPassphraseFileError(profile.name)
    try:
        passphrase = ask_passphrase("New dashboard passphrase: ")
        confirmation = ask_passphrase("Type it again: ")
    except EOFError:
        raise NoPassphraseTypedError from None
    if not passphrase.strip():
        raise EmptyPassphraseError
    if confirmation != passphrase:
        raise PassphraseMismatchError
    set_passphrase(profile, passphrase)


def _serve(profile: Profile) -> None:
    """Serve the read-only dashboard until stopped, after its refusals."""
    app = create_app(profile, clock=lambda: datetime.now(UTC))
    uvicorn.run(
        app,
        host=profile.dashboard_bind or "127.0.0.1",
        port=profile.dashboard_port or DEFAULT_DASHBOARD_PORT,
    )


def _demo(directory: str | None, port: int) -> None:
    """Create a synthetic development profile, then use the real serve path."""
    profile = create_demo_profile(
        None if directory is None else Path(directory), port=port
    )
    url = f"http://127.0.0.1:{port}"
    sys.stdout.write(
        f"Synthetic dashboard: {url}\n"
        f"Login passphrase: budget-demo\n"
        f"Demo folder: {profile.stores.parent}\n"
        "Press Ctrl+C to stop. Delete the demo folder when finished.\n"
    )
    sys.stdout.flush()
    _serve(profile)


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
    if arguments.command == "demo":
        _demo(arguments.directory, arguments.port)
        return EXIT_OK
    profile_file = _selected_profile_file(arguments.profile, environ)
    profile = load_profile_file(profile_file)
    if arguments.command == "import":
        return _import(profile, arguments.ranges)
    if arguments.command == "backup":
        _backup(profile)
    elif arguments.command == "restore":
        pass
    elif arguments.command == "rebuild":
        _rebuild(profile, arguments.from_stage)
    elif arguments.command == "review":
        _review(profile, arguments.kind, arguments.account)
    elif arguments.command == "set-passphrase":
        _set_passphrase(profile)
    elif arguments.command == "serve":
        _serve(profile)
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
    except (
        ProfileFileError,
        ConfigurationError,
        ConflictingDeclaredFormatsError,
        UnsupportedSourceFormatError,
        NoPassphraseFileError,
        NoPassphraseTypedError,
        EmptyPassphraseError,
        PassphraseMismatchError,
        DemoDirectoryExistsError,
    ) as error:
        return _refuse(error, EXIT_REFUSED_INPUT)
    except (
        NoProfileSelectedError,
        UncommittedCodeError,
        SilverNotBuiltError,
        WriterLockHeldError,
        StoresFolderUnavailableError,
        RestoreInsteadError,
        MigratedWithoutBackupError,
        ImportedWithoutBackupError,
        ImportedWithoutPublicationError,
        RebuiltWithoutBackupError,
        BackupWriteError,
        UnsupportedStoresError,
        LostStoreError,
        NoBackupsFolderError,
        PassphraseNotSetError,
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
