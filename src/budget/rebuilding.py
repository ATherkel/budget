# Copyright 2026 Therkel
"""The `rebuild` application operation: build a stage from its upstream.

Silver's build keeps its one definition, the pure `budget.silver.build`, and
this module is only the thin adapter a command calls: it reads the profile's
Bronze inputs and account registry, then hands them to the existing
`budget.silver.rebuild_silver`, which replaces the stored result. No build,
admission, or duplicate-resolution rule lives here.

Silver reads the validated effective decision log in the same command context
and records its exact prefix in the committed provenance.
"""

import platform
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from budget.bronze import BronzeStore
from budget.bronze.models import ImportRun
from budget.codeversion import committed_code_version
from budget.decision_log import read_decision_log
from budget.gold import GoldPublication, GoldResult, build
from budget.gold.fingerprint import (
    CONTRACT_VERSION,
    FINGERPRINT_SCHEME,
    result_fingerprint,
)
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.store import GoldStore
from budget.inputs import ConfigurationError, load_accounts, load_configuration
from budget.locking import WriterLock
from budget.profiles import ACCOUNTS_FILE_NAME, Profile
from budget.silver import (
    AcceptDiscrepancy,
    SameTransaction,
    SilverBuildInputs,
    SilverDecision,
    SilverResult,
    SilverStore,
    VoidImportRun,
    Withdrawn,
    rebuild_silver,
)
from budget.silver.currencies import UnknownCurrencyError, minor_unit_places


@dataclass(frozen=True)
class SilverRebuild:
    """One Silver rebuild's Bronze provenance and the result it stored.

    The runs are the import runs read under the command's own writer lock,
    before that lock was released, so a summary reports what the build actually
    read instead of rereading a store a later command may have changed.
    """

    runs: Sequence[ImportRun]
    result: SilverResult


class SilverNotBuiltError(RuntimeError):
    """Gold was asked to publish from a Silver no build has ever filled."""

    def __init__(self) -> None:
        """Say which command builds Silver first."""
        super().__init__(
            "Silver has never been built, so there is nothing to publish; run "
            "`budget rebuild --from silver` first; nothing was published"
        )


class SilverProvenanceUnavailableError(RuntimeError):
    """Gold cannot consume a Silver replacement with unknown build context."""

    def __init__(self) -> None:
        """Name the one recovery command."""
        super().__init__(
            "the stored Silver result has no trustworthy build provenance; "
            "run `budget rebuild --from silver` before publishing Gold; "
            "nothing was published"
        )


class SilverDecisionFreshnessError(RuntimeError):
    """Gold was asked to consume Silver before its effective decisions."""

    def __init__(self) -> None:
        """Name the earliest rebuild that applies the changed decisions."""
        super().__init__(
            "the current effective Silver decisions have not been applied to "
            "the stored Silver result; run `budget rebuild --from silver` "
            "before publishing Gold; nothing was published"
        )


@dataclass(frozen=True)
class GoldRebuild:
    """What one Gold rebuild left current, and whether it published it.

    A recipe equal to the current publication's builds and publishes nothing,
    so `publication` is then the one that was already current.
    """

    publication: GoldPublication
    published: bool


def bronze_inputs(profile: Profile) -> SilverBuildInputs:
    """Read every Bronze input one Silver build needs, and the currencies.

    The profile's import runs, each run's payload's source records or format
    failures, and each declared account's currency are read as they stand now.
    Manual decisions are not read: the caller refuses a log that holds one
    before it calls this.
    """
    currencies = {
        account_id: account.currency
        for account_id, account in load_accounts(profile).items()
    }
    with BronzeStore(profile) as store:
        runs = store.import_runs()
        source_records = {
            run.payload_id: store.get_source_records(run.payload_id) for run in runs
        }
        format_failures = {
            run.payload_id: store.get_format_failures(run.payload_id) for run in runs
        }
    _require_declared_accounts(currencies, runs)
    return SilverBuildInputs(
        runs=runs,
        source_records=source_records,
        format_failures=format_failures,
        currencies=currencies,
    )


def _require_declared_accounts(
    currencies: Mapping[str, str], runs: Sequence[ImportRun]
) -> None:
    """Refuse a rebuild the account registry cannot describe.

    The pure build reads each stored run's account and currency, so a registry
    that no longer declares one of them is a configuration error here, at the
    Bronze boundary, instead of a crash inside the build. Refused and repeat
    runs are ignored, exactly as the pure build ignores them.
    """
    for run in runs:
        if run.outcome != "stored":
            continue
        account_id = run.declared_account_id
        currency = currencies.get(account_id)
        if currency is None:
            raise ConfigurationError((_missing_account(account_id),))
        if not _known_currency(currency):
            raise ConfigurationError((_unknown_currency(account_id),))


def require_buildable_accounts(profile: Profile, importing: Collection[str]) -> None:
    """Refuse now what a Silver rebuild after imports to `importing` would refuse.

    A command that writes Bronze and then rebuilds, as `budget import` does,
    calls this before its first write, so a refused rebuild never follows
    Bronze writes. Every account with a stored run must be declared with a
    currency the build supports, and so must every account being imported.
    """
    currencies = {
        account_id: account.currency
        for account_id, account in load_accounts(profile).items()
    }
    with BronzeStore(profile) as store:
        _require_declared_accounts(currencies, store.import_runs())
    for account_id in sorted(importing):
        currency = currencies.get(account_id)
        if currency is not None and not _known_currency(currency):
            raise ConfigurationError((_unknown_currency(account_id),))


def _known_currency(currency: str) -> bool:
    """Whether the ISO 4217 table knows a currency, without naming its value."""
    try:
        minor_unit_places(currency)
    except UnknownCurrencyError:
        return False
    return True


def _missing_account(account_id: str) -> str:
    """Name a stored run's account that the registry no longer declares."""
    return (
        f'{ACCOUNTS_FILE_NAME}: account "{account_id}" is not declared, but '
        "Bronze holds a stored import run for it; restore or add the account in "
        "accounts.toml before rebuilding; nothing was written"
    )


def _unknown_currency(account_id: str) -> str:
    """Name the currency field, never repeating the value it holds."""
    return (
        f'{ACCOUNTS_FILE_NAME}: account "{account_id}": currency is not '
        "supported by this Silver build; correct it in accounts.toml before "
        "rebuilding; nothing was written"
    )


def rebuild_from_gold(lock: WriterLock, *, now: datetime) -> GoldRebuild:
    """Publish the locked profile's Gold from its stored Silver and inputs.

    The recipe names the import runs Silver was built from, the profile's
    configuration, its decision log and the code that builds; Gold never
    reads Bronze, and Silver is taken as it stands. `now` only
    stamps the publication's `built_at` and `known_at`: no figure reads it.
    """
    profile = lock.profile
    configuration = load_configuration(profile)
    log = read_decision_log(profile)
    with SilverStore(profile) as silver_store:
        if not silver_store.is_built():
            raise SilverNotBuiltError
        stored_silver = silver_store.read_build()
    silver = stored_silver.result
    provenance = stored_silver.provenance
    if provenance is None:
        raise SilverProvenanceUnavailableError
    _require_current_silver_decisions(provenance.decisions, log.silver)
    recipe = Recipe(
        import_runs=frozenset(
            RecipeImportRun(run.import_run_id, run.payload_id)
            for run in provenance.import_runs
        ),
        configuration_fingerprint=configuration.fingerprint,
        decision_log_position=log.position,
        decision_log_prefix_sha256=log.prefix_sha256,
        code_version=committed_code_version(profile),
        contract_version=CONTRACT_VERSION,
        silver_identity_version=provenance.identity_version,
        late_booking_days=profile.late_booking_window.days,
        python_version=platform.python_version(),
        sqlite_version=sqlite3.sqlite_version,
        silver_fingerprint_scheme=provenance.fingerprint_scheme,
        silver_result_fingerprint=provenance.result_fingerprint,
        silver_code_version=provenance.code_version,
        silver_decision_log_position=provenance.decision_log_position,
        silver_decision_log_prefix_sha256=provenance.decision_log_prefix_sha256,
        silver_bronze_parser_provenance=provenance.bronze_parser_provenance,
        silver_currencies=frozenset(provenance.currencies.items()),
        silver_decisions=tuple(provenance.decisions),
    )
    with GoldStore(profile) as gold:
        current = gold.current()
        if current is not None and gold.recipe(current.publication_id) == recipe:
            return GoldRebuild(publication=current, published=False)
        draft = GoldPublication(
            publication_id=gold.next_publication_id(),
            kind="pipeline",
            label=None,
            known_at=now,
            built_at=now,
            replayed_at=None,
            contract_version=CONTRACT_VERSION,
            fingerprint_scheme=FINGERPRINT_SCHEME,
            result_fingerprint="",
        )
        built = build(
            silver=silver,
            configuration=configuration,
            decisions=log.gold,
            publication=draft,
            late_booking_window=profile.late_booking_window,
        )
        publication = replace(draft, result_fingerprint=result_fingerprint(built))
        gold.publish(
            GoldResult(publication, built.records, built.lineage), recipe, configuration
        )
    return GoldRebuild(publication=publication, published=True)


def _require_current_silver_decisions(
    consumed: Sequence[SilverDecision],
    current: Sequence[SilverDecision],
) -> None:
    """Refuse if any effective Silver decision differs from the build."""
    if sorted(consumed, key=_silver_decision_key) != sorted(
        current, key=_silver_decision_key
    ):
        raise SilverDecisionFreshnessError


def _silver_decision_key(decision: SilverDecision) -> tuple[object, ...]:
    """Return every typed field in one deterministic decision key."""
    match decision:
        case AcceptDiscrepancy():
            return ("accept-discrepancy", decision.decision_id, decision.import_run_id)
        case VoidImportRun():
            return ("void-import-run", decision.decision_id, decision.import_run_id)
        case Withdrawn():
            return ("withdrawn", decision.decision_id, decision.transaction_id)
        case SameTransaction():
            return (
                "same-transaction",
                decision.decision_id,
                decision.transaction_id,
                decision.payload_id,
                decision.record_ordinal,
            )


def rebuild_from_silver(lock: WriterLock) -> SilverRebuild:
    """Rebuild the locked profile's Silver from its Bronze store.

    The caller holds the profile's writer lock for its whole command, so the
    Bronze inputs are read under that one lock and handed to the existing
    `budget.silver.rebuild_silver`, which replaces the stored result. The runs
    read here come back with the result, so no caller rereads Bronze. A
    decision log is validated and its effective Silver decisions are included
    in the stored build provenance.
    """
    profile = lock.profile
    log = read_decision_log(profile)
    inputs = replace(
        bronze_inputs(profile),
        decisions=log.silver,
        decision_log_position=log.position,
        decision_log_prefix_sha256=log.prefix_sha256,
        code_version=committed_code_version(profile),
    )
    result = rebuild_silver(lock, inputs=inputs)
    return SilverRebuild(runs=inputs.runs, result=result)
