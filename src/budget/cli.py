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
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Final, NoReturn

import uvicorn

from budget import checking, routine_logging, sqlstore, summaries
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
from budget.completeness import Completeness, completeness
from budget.dashboard import create_app
from budget.dashboard.passphrase import PassphraseNotSetError, set_passphrase
from budget.deciding import DecisionLog, DecisionProposal, Recorded
from budget.decision_log import DECISION_KINDS
from budget.demo import DEFAULT_DEMO_PORT, DemoDirectoryExistsError, create_demo_profile
from budget.gold.storage import GOLD_STAGE
from budget.gold.store import GoldStore, UndoUnavailableError
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
    SilverReviews,
    read_household_inputs,
    rebuild_from_gold,
    rebuild_through_gold,
    require_buildable_accounts,
)
from budget.refreshing import (
    InputsNotReplacedError,
    NotProductionsSetError,
    NotRefreshableError,
    RefreshUndoError,
    RefreshWriteError,
    refresh,
    require_refreshable,
)
from budget.restoring import (
    CatchUpCodeRefusedError,
    CatchUpInputsRefusedError,
    CatchUpRefusedError,
    DamagedStoreError,
    DecisionLogDamagedError,
    DecisionLogDivergedError,
    ImportLogDisagreesError,
    IncompleteSetError,
    NoUsableSetError,
    OccupiedProfileError,
    RestoreWriteError,
    UndoAfterCatchUp,
    UnfinishedRestoreError,
    UnknownStageError,
    require_no_unfinished_restore,
    restore,
)
from budget.reviewing import REVIEW_KINDS, open_reviews
from budget.silver.storage import SILVER_STAGE
from budget.silver.store import SilverStore

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


class UndoneWithoutBackupError(Exception):
    """The undo is committed, but no backup set followed it."""

    def __init__(self, reason: Exception) -> None:
        """Say what was done and what to run."""
        super().__init__(
            "the current publication was restored, but no backup set could be "
            f"written after it: {reason}. Put that right, then run `budget backup`"
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


class DecisionRejectedError(Exception):
    """The boundary rejected the proposed decision; nothing was recorded."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        """Name every reason the boundary gave, one per line."""
        self.reasons = reasons
        listed = "".join(f"\n  {reason}" for reason in reasons)
        super().__init__(f"the decision was rejected; nothing was recorded:{listed}")


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
    restore_ = commands.add_parser(
        "restore", help="restore a whole profile from a backup set"
    )
    dev = commands.add_parser("dev", help="development-only commands")
    dev_commands = dev.add_subparsers(dest="dev_command", required=True)
    refresh = dev_commands.add_parser(
        "refresh", help="restore production's newest backup set for development"
    )
    refresh.add_argument(
        "--inputs", action="store_true", help="also replace development's inputs"
    )
    refresh.add_argument(
        "--writable",
        action="store_true",
        help="restore into development's own stores, to rehearse a migration",
    )
    restore_.add_argument(
        "backup_set", nargs="?", help="the set to restore (default: the newest)"
    )
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
    decide = commands.add_parser(
        "decide", help="record a manual decision, then rebuild from what it affects"
    )
    decide.add_argument("kind", choices=DECISION_KINDS)
    decide.add_argument(
        "targets",
        nargs="*",
        help="handles or IDs; for classify, the category comes last",
    )
    decide.add_argument("--reason", required=True)
    decide.add_argument(
        "--supersedes",
        action="append",
        default=[],
        metavar="DECISION_ID",
        help="a decision this one replaces; repeat for several",
    )
    decide.add_argument(
        "--adjustment",
        action="store_true",
        help="classify as an adjustment instead of a category",
    )
    decide.add_argument(
        "--counterpart", help="a one-sided transfer's counterpart account"
    )
    commands.add_parser("undo", help="restore the previous current publication")
    commands.add_parser("status", help="show balance and classification completeness")
    commands.add_parser(
        "check", help="validate every input file and the decision-log prefix"
    )
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


def _undo_line(undo: UndoAfterCatchUp, backup_set: str) -> str:
    """Say where undo returns after catch-up."""
    return (
        f"undo returns to publication {undo.publication_id}, the current one in "
        f"backup set {backup_set}; publications made after that set are lost\n"
    )


def _restore(profile: Profile, backup_set: str | None) -> int:
    """Restore the whole profile from a backup set, and name the set on stdout."""
    with writer_lock(profile) as lock:
        restored = restore(lock, backup_set, now=datetime.now(UTC))
    for skipped in restored.skipped:
        sys.stdout.write(f"skipped backup set {skipped}: this code cannot read it\n")
    for put_back in restored.put_back:
        sys.stdout.write(f"put back {put_back} from the backup set\n")
    if restored.imports_lost:
        sys.stdout.write(
            "the import log was missing: runs imported after backup set "
            f"{restored.backup.name} are not restored\n"
        )
    if restored.decision_line_cut_off:
        sys.stdout.write(
            "the decision log's final line was cut off: it counts as never "
            "written and is left in place; delete it before recording a decision\n"
        )
    if restored.decisions_lost:
        sys.stdout.write(
            "the decision log was missing: decisions recorded after backup set "
            f"{restored.backup.name} cannot be recovered\n"
        )
    if restored.replayed:
        runs = "run" if restored.replayed == 1 else "runs"
        sys.stdout.write(
            f"replayed {restored.replayed} import {runs} from the export archive\n"
        )
    if restored.gold_started:
        sys.stdout.write(
            f"backup set {restored.backup.name} holds no Gold store: Gold was "
            "started anew, and no earlier publication is recovered\n"
        )
    if restored.gold is not None:
        sys.stdout.write(summaries.gold_line(restored.gold) + "\n")
    if restored.undo is not None:
        sys.stdout.write(_undo_line(restored.undo, restored.backup.name))
    sys.stdout.write(f"restored backup set {restored.backup.name}\n")
    if restored.backed_up is not None:
        sys.stdout.write(f"backup set {restored.backed_up.name} written\n")
    if restored.backup_failure is not None:
        sys.stderr.write(
            "budget: the restore is finished, but no backup set of it could be "
            f"written: {restored.backup_failure}; run `budget backup` once that "
            "is put right\n"
        )
        return EXIT_REFUSED_ENVIRONMENT
    return EXIT_OK


def _dev_refresh(profile: Profile, *, inputs: bool, writable: bool) -> None:
    """Restore production's newest backup set for development; name it."""
    # Refused before the lock, which would create the stores folder.
    require_refreshable(profile)
    with writer_lock(profile) as lock:
        refreshed = refresh(lock, inputs=inputs, writable=writable)
    for skipped in refreshed.skipped:
        sys.stdout.write(f"skipped backup set {skipped}: this code cannot read it\n")
    name = refreshed.backup.name
    into = "development's own stores (writable)" if writable else "upstream (read-only)"
    sys.stdout.write(f"restored backup set {name} into {into}\n")
    if inputs:
        sys.stdout.write(f"replaced development's inputs with backup set {name}'s\n")


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
        silver_reviews = SilverReviews()
        if from_stage in {BRONZE_STAGE, SILVER_STAGE}:
            rebuilt = rebuild_through_gold(
                lock, now=now, inputs=inputs, from_bronze=from_stage == BRONZE_STAGE
            )
            summary = summaries.rebuild_summary(rebuilt.silver)
            counts = _rebuild_counts(rebuilt.silver)
            published = rebuilt.gold
            silver_reviews = rebuilt.silver_reviews
        else:
            published = rebuild_from_gold(lock, now=now, inputs=inputs)
        routine_logging.finished(
            profile,
            "rebuild",
            counts={**counts, "published": int(published.published)},
            duration_ms=_milliseconds(started),
        )
        # Every production write is followed by a set covering what it wrote;
        # a Gold rebuild that publishes nothing wrote nothing. The set comes
        # before the diff, so a diff that fails cannot cost it.
        wrote = from_stage != GOLD_STAGE or published.published
        written = None
        failure = None
        if profile.name == PRODUCTION_PROFILE_NAME and wrote:
            try:
                written = back_up(lock, now=datetime.now(UTC))
            except BACKUP_FAILURES as error:
                failure = error
        sys.stdout.write(f"{summary}{summaries.gold_line(published)}\n")
        sys.stdout.write(
            summaries.publication_changes(profile, published, silver_reviews)
        )
        if written is not None:
            sys.stdout.write(f"Backup   backup set {written.name} written\n")
        try:
            _show_completeness(profile)
        finally:
            # A failed completeness read must not hide the missing backup.
            if failure is not None:
                raise RebuiltWithoutBackupError(failure) from None


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
            _show_completeness(profile)
            return EXIT_OK
        diff_text = (
            summaries.publication_changes(profile, done.published, done.silver_reviews)
            if done.published is not None
            else ""
        )
        sys.stdout.write(summaries.import_summary(done, diff_text=diff_text))
        routine_logging.finished(
            profile,
            "import",
            counts=done.counts(),
            duration_ms=_milliseconds(started),
        )
        _show_completeness(profile)
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


def _transaction(profile: Profile, handle: str) -> str:
    """Return the one Silver transaction whose ID starts with `handle`.

    Review shows a transaction by its first 8 characters (`operations.md`,
    *Commands*); a handle that names no transaction, or more than one, is
    refused before anything is proposed.
    """
    with SilverStore(profile) as silver:
        matches = sorted(
            t.transaction_id
            for t in silver.read().transactions
            if t.transaction_id.startswith(handle)
        )
    if not matches:
        reason = f'no transaction in Silver has the handle "{handle}"'
        raise DecisionRejectedError((reason,))
    if len(matches) > 1:
        shown = ", ".join(f"{each[:12]}…" for each in matches)
        reason = (
            f'the handle "{handle}" matches more than one transaction ({shown}); '
            "type more of its ID"
        )
        raise DecisionRejectedError((reason,))
    return matches[0]


def _details(arguments: argparse.Namespace) -> tuple[list[str], dict[str, object]]:
    """Split the positionals into targets, and gather the kind's own fields.

    A `classify` names its category after its handle, as walkthrough W2 does,
    unless it is an adjustment. A wrong count is left to the boundary, which
    names it.
    """
    targets: list[str] = [str(target) for target in arguments.targets]
    details: dict[str, object] = {}
    if arguments.kind == "classify" and arguments.adjustment:
        details["adjustment"] = True
    elif arguments.kind == "classify" and targets:
        details["category"] = targets.pop()
    if arguments.counterpart is not None:
        details["counterpart_account_id"] = arguments.counterpart
    return targets, details


def _proposal(profile: Profile, arguments: argparse.Namespace) -> DecisionProposal:
    """Turn the command line into the proposal the boundary judges."""
    targets, details = _details(arguments)
    return DecisionProposal(
        kind=arguments.kind,
        targets=tuple(_transaction(profile, handle) for handle in targets),
        reason=arguments.reason,
        supersedes=tuple(arguments.supersedes),
        details=details,
    )


def _decide(profile: Profile, arguments: argparse.Namespace) -> None:
    """Propose a decision under the writer lock, then rebuild and publish."""
    started = perf_counter()
    with writer_lock(profile) as lock:
        require_committed_code(lock.profile)
        log = DecisionLog(lock, clock=lambda: datetime.now(UTC))
        recorded = log.propose(_proposal(profile, arguments))
        if not isinstance(recorded, Recorded):
            raise DecisionRejectedError(recorded.reasons)
        inputs = read_household_inputs(lock.profile)
        published = rebuild_from_gold(lock, now=datetime.now(UTC), inputs=inputs)
        routine_logging.finished(
            profile,
            "decide",
            counts={"published": int(published.published)},
            duration_ms=_milliseconds(started),
        )
        sys.stdout.write(
            f"Recorded {recorded.decision_id}.\n{summaries.gold_line(published)}\n"
        )
        sys.stdout.write(
            summaries.publication_changes(profile, published, SilverReviews())
        )
        _show_completeness(profile)


def _undo(profile: Profile) -> None:
    """Move the current Gold pointer back once, under the profile's writer lock."""
    started = perf_counter()
    with writer_lock(profile) as lock:
        if profile.name == PRODUCTION_PROFILE_NAME:
            require_backup_allowed(profile)
        with GoldStore(profile) as gold:
            move = gold.undo()
        routine_logging.finished(
            profile,
            "undo",
            counts={},
            duration_ms=_milliseconds(started),
        )
        summary = summaries.undo_line(move)
        if profile.name != PRODUCTION_PROFILE_NAME:
            sys.stdout.write(summary + "\n")
            return
        try:
            written = back_up(lock, now=datetime.now(UTC))
        except BACKUP_FAILURES as error:
            sys.stdout.write(summary + "\n")
            raise UndoneWithoutBackupError(error) from None
        sys.stdout.write(f"{summary}\nBackup   backup set {written.name} written\n")


def _show_completeness(profile: Profile) -> Completeness:
    """Print the completeness output to the terminal only, never to a log."""
    found = completeness(profile, now=datetime.now(UTC))
    sys.stdout.write(summaries.completeness_summary(found))
    return found


def _status(profile: Profile) -> int:
    """Show balance and classification completeness, with no lock.

    Completeness findings never change the exit status; evidence that cannot
    be read is a defect in a store, not a finding, so it does.
    """
    found = _show_completeness(profile)
    if found.evidence is not None and found.evidence.unreadable is not None:
        sys.stderr.write("budget: the import evidence could not be read\n")
        return (
            EXIT_VERIFICATION_FAILED
            if found.evidence.damaged
            else EXIT_REFUSED_ENVIRONMENT
        )
    return EXIT_OK


def _check(profile: Profile) -> int:
    """Validate the inputs and the decision log, with no lock; build nothing."""
    found = checking.check(profile)
    listed = (*found.problems, *found.mismatches)
    if not listed:
        sys.stdout.write("No problems found.\n")
        return EXIT_OK
    for problem in listed:
        sys.stdout.write(problem + "\n")
    noun = "problem" if len(listed) == 1 else "problems"
    sys.stdout.write(f"{len(listed)} {noun}. Nothing was built.\n")
    return EXIT_VERIFICATION_FAILED if found.mismatches else EXIT_REFUSED_INPUT


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


# The commands that take nothing but the profile.
_PROFILE_ONLY_COMMANDS: Final[Mapping[str, Callable[[Profile], None]]] = {
    "backup": _backup,
    "undo": _undo,
    "set-passphrase": _set_passphrase,
    "serve": _serve,
}


def _run(arguments: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Select and load the profile, run the command, and return its status."""
    if arguments.command == "demo":
        _demo(arguments.directory, arguments.port)
        return EXIT_OK
    profile_file = _selected_profile_file(arguments.profile, environ)
    profile = load_profile_file(profile_file)
    # Until a restore finishes, its stores are its own half-done work.
    if arguments.command not in {"restore", "set-passphrase"}:
        require_no_unfinished_restore(profile)
    if arguments.command == "import":
        return _import(profile, arguments.ranges)
    if arguments.command == "restore":
        return _restore(profile, arguments.backup_set)
    if arguments.command == "status":
        return _status(profile)
    if arguments.command == "check":
        return _check(profile)
    if arguments.command in _PROFILE_ONLY_COMMANDS:
        _PROFILE_ONLY_COMMANDS[arguments.command](profile)
    elif arguments.command == "dev":
        _dev_refresh(profile, inputs=arguments.inputs, writable=arguments.writable)
    elif arguments.command == "rebuild":
        _rebuild(profile, arguments.from_stage)
    elif arguments.command == "review":
        _review(profile, arguments.kind, arguments.account)
    elif arguments.command == "decide":
        _decide(profile, arguments)
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
        DecisionRejectedError,
        ConflictingDeclaredFormatsError,
        UnsupportedSourceFormatError,
        NoPassphraseFileError,
        NoPassphraseTypedError,
        EmptyPassphraseError,
        PassphraseMismatchError,
        DemoDirectoryExistsError,
        CatchUpInputsRefusedError,
    ) as error:
        return _refuse(error, EXIT_REFUSED_INPUT)
    except (
        NoProfileSelectedError,
        UncommittedCodeError,
        CatchUpCodeRefusedError,
        SilverNotBuiltError,
        WriterLockHeldError,
        StoresFolderUnavailableError,
        RestoreInsteadError,
        OccupiedProfileError,
        RestoreWriteError,
        NotRefreshableError,
        NotProductionsSetError,
        InputsNotReplacedError,
        RefreshWriteError,
        RefreshUndoError,
        NoUsableSetError,
        UnknownStageError,
        UnfinishedRestoreError,
        MigratedWithoutBackupError,
        ImportedWithoutBackupError,
        ImportedWithoutPublicationError,
        RebuiltWithoutBackupError,
        UndoneWithoutBackupError,
        UndoUnavailableError,
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
        IncompleteSetError,
        DamagedStoreError,
        CatchUpRefusedError,
        ImportLogDisagreesError,
        DecisionLogDivergedError,
        DecisionLogDamagedError,
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
