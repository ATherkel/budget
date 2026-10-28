# Copyright 2026 Therkel
"""The `rebuild` application operation: build a stage from its upstream.

Silver's build keeps its one definition, the pure `budget.silver.build`, and
this module is only the thin adapter a command calls: it reads the profile's
Bronze inputs and account registry, then hands them to the existing
`budget.silver.rebuild_silver`, which replaces the stored result. No build,
admission, or duplicate-resolution rule lives here.

The household's decision log is read here too, so a rebuild applies every
decision in force instead of building as if the household had made none, and
Silver records the log's exact prefix in its committed provenance.
"""

import platform
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from budget import sqlstore
from budget.bronze import BronzeStore
from budget.bronze.models import ImportRun
from budget.bronze.storage import bronze_stage
from budget.bronze.store import DerivedRecords
from budget.codeversion import committed_code_version
from budget.decision_log import DecisionLogRead, read_decision_log
from budget.gold import GoldPublication, GoldResult, build
from budget.gold.fingerprint import (
    CONTRACT_VERSION,
    FINGERPRINT_SCHEME,
    result_fingerprint,
)
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.storage import gold_stage
from budget.gold.store import GoldStore
from budget.inputs import (
    ConfigurationError,
    ConfigurationSnapshot,
    load_accounts,
    load_configuration,
)
from budget.locking import WriterLock
from budget.profiles import ACCOUNTS_FILE_NAME, Profile
from budget.silver import (
    AcceptDiscrepancy,
    SameTransaction,
    SilverBuild,
    SilverBuildInputs,
    SilverDecision,
    SilverProvenance,
    SilverResult,
    SilverStore,
    VoidImportRun,
    Withdrawn,
    derive_silver,
    rebuild_silver,
    silver_provenance,
    store_silver,
)
from budget.silver.currencies import UnknownCurrencyError, minor_unit_places
from budget.silver.storage import silver_stage


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


class SilverDecisionLogPrefixError(RuntimeError):
    """The retained decision-log prefix is no longer the current prefix."""

    def __init__(self) -> None:
        """Refuse changed history rather than accepting rewritten entries."""
        super().__init__(
            "the Silver decision-log prefix has been replaced or truncated; "
            "run `budget rebuild --from silver` before publishing Gold; "
            "nothing was published"
        )


@dataclass(frozen=True)
class GoldRebuild:
    """What one Gold rebuild left current, and whether it published it.

    A recipe equal to the current publication's builds and publishes nothing,
    so `publication` is then the one that was already current.
    """

    publication: GoldPublication
    published: bool


@dataclass(frozen=True)
class HouseholdInputs:
    """The household files one pipeline command reads once, before it writes.

    Reading them once means the Silver build, the Gold build and the recipe
    all see the same configuration and the same decision-log prefix, and a
    file Gold would refuse is refused before anything is replaced.
    """

    configuration: ConfigurationSnapshot
    log: DecisionLogRead


def read_household_inputs(profile: Profile) -> HouseholdInputs:
    """Check everything a Silver or Gold rebuild needs, writing nothing.

    The Gold store must exist, and the configuration and the decision log
    must load: each refusal names its file and happens before the first store
    is touched.
    """
    require_stores(profile)
    return HouseholdInputs(load_configuration(profile), read_decision_log(profile))


def require_stores(profile: Profile) -> None:
    """Refuse now, in stage order, a store a rebuild would find missing later.

    Gold's store is checked with the others, so Silver is never replaced just
    before publishing finds Gold missing.
    """
    for stage in (bronze_stage, silver_stage, gold_stage):
        store = stage(profile)
        if not store.path.exists():
            raise sqlstore.StoreNotFoundError(store.label, store.path)


def bronze_inputs(
    profile: Profile,
    log: DecisionLogRead | None = None,
    derived: DerivedRecords | None = None,
) -> SilverBuildInputs:
    """Read every Bronze input one Silver build needs, and the currencies.

    The profile's import runs, each run's payload's source records or format
    failures, and each declared account's currency are read as they stand now.
    `log` is the decision log already read; without it the profile's log is
    read. Its Silver decisions, position and prefix go into the inputs with the
    producing code version, for Silver's provenance. `derived` are source
    records and format failures freshly parsed from the retained payloads,
    which stand in for the stored ones when a rebuild starts from Bronze.
    """
    currencies = {
        account_id: account.currency
        for account_id, account in load_accounts(profile).items()
    }
    with BronzeStore(profile) as store:
        runs = store.import_runs()
        records = (
            store.get_source_records if derived is None else derived.source_records
        )
        failures = (
            store.get_format_failures if derived is None else derived.format_failures
        )
        source_records = {run.payload_id: records(run.payload_id) for run in runs}
        format_failures = {run.payload_id: failures(run.payload_id) for run in runs}
    _require_declared_accounts(currencies, runs)
    read = read_decision_log(profile) if log is None else log
    return SilverBuildInputs(
        runs=runs,
        source_records=source_records,
        format_failures=format_failures,
        currencies=currencies,
        decisions=read.silver,
        decision_log_position=read.position,
        decision_log_prefix_sha256=read.prefix_sha256,
        code_version=committed_code_version(profile),
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


@dataclass(frozen=True)
class _GoldPlan:
    """A Gold build derived in memory, ready to publish when its turn comes."""

    recipe: Recipe
    configuration: ConfigurationSnapshot
    built: GoldResult


@dataclass(frozen=True)
class PipelineRebuild:
    """One rebuild through Silver and Gold: what each stage left behind.

    `silver_changed` is whether the stored Silver differed from the one just
    derived, which tells `import` whether a retry had work left to finish.
    """

    silver: SilverRebuild
    silver_changed: bool
    gold: GoldRebuild


def _recipe(
    profile: Profile, provenance: SilverProvenance, household: HouseholdInputs
) -> Recipe:
    """Name every input a build from Silver and the household's files reads.

    Silver's part is its `provenance`: what built the Silver result Gold reads.
    """
    log = household.log
    return Recipe(
        import_runs=frozenset(
            RecipeImportRun(run.import_run_id, run.payload_id)
            for run in provenance.import_runs
        ),
        configuration_fingerprint=household.configuration.fingerprint,
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


def _plan_gold(
    profile: Profile,
    silver: SilverBuild,
    household: HouseholdInputs,
    now: datetime,
) -> _GoldPlan | GoldRebuild:
    """Derive Gold from `silver`, writing nothing, or find it already current.

    A recipe equal to the current publication's builds nothing and comes back
    as the rebuild that publishes nothing. A configuration error is raised
    here, before any store is replaced.
    """
    if silver.provenance is None:
        raise SilverProvenanceUnavailableError
    current_prefix = household.log.prefix_sha256_at(
        silver.provenance.decision_log_position
    )
    if current_prefix != silver.provenance.decision_log_prefix_sha256:
        raise SilverDecisionLogPrefixError
    _require_current_silver_decisions(silver.provenance.decisions, household.log.silver)
    recipe = _recipe(profile, silver.provenance, household)
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
        silver=silver.result,
        configuration=household.configuration,
        decisions=household.log.gold,
        publication=draft,
        late_booking_window=profile.late_booking_window,
    )
    publication = replace(draft, result_fingerprint=result_fingerprint(built))
    result = GoldResult(publication, built.records, built.lineage)
    return _GoldPlan(recipe, household.configuration, result)


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


def _publish(profile: Profile, plan: _GoldPlan | GoldRebuild) -> GoldRebuild:
    """Publish a planned build, or report the publication already current."""
    if isinstance(plan, GoldRebuild):
        return plan
    with GoldStore(profile) as gold:
        gold.publish(plan.built, plan.recipe, plan.configuration)
    return GoldRebuild(publication=plan.built.publication(), published=True)


def rebuild_from_gold(
    lock: WriterLock, *, now: datetime, inputs: HouseholdInputs | None = None
) -> GoldRebuild:
    """Publish the locked profile's Gold from its stored Silver and inputs.

    The recipe names the import runs Silver was built from, the profile's
    configuration, its decision log and the code that builds; Gold never
    reads Bronze, and Silver is taken as it stands. `now` only
    stamps the publication's `built_at` and `known_at`: no figure reads it.
    `inputs` are the household files the caller already read; without them
    they are read here.
    """
    profile = lock.profile
    household = read_household_inputs(profile) if inputs is None else inputs
    with SilverStore(profile) as silver_store:
        if not silver_store.is_built():
            raise SilverNotBuiltError
        silver = silver_store.read_build()
    return _publish(profile, _plan_gold(profile, silver, household, now))


def rebuild_through_gold(
    lock: WriterLock,
    *,
    now: datetime,
    inputs: HouseholdInputs | None = None,
    from_bronze: bool = False,
) -> PipelineRebuild:
    """Rebuild Silver from Bronze, then publish Gold from it.

    With `from_bronze`, Bronze's source records and format failures are parsed
    again from the retained payloads first. Every stage is derived in memory
    before anything is stored, so a refusal Bronze's parsers, Silver's build or
    Gold's build make leaves every store as it was; only then are the stages
    replaced in order and Gold published.
    """
    profile = lock.profile
    household = read_household_inputs(profile) if inputs is None else inputs
    reparsed = None
    if from_bronze:
        with BronzeStore(profile) as bronze:
            reparsed = bronze.derive_records()
    silver_inputs = bronze_inputs(profile, household.log, reparsed)
    derived = derive_silver(silver_inputs)
    # The provenance `store_silver` will record, known before anything is stored.
    silver = SilverBuild(
        result=derived,
        currencies=silver_inputs.currencies,
        provenance=silver_provenance(silver_inputs, derived),
    )
    plan = _plan_gold(profile, silver, household, now)
    with SilverStore(profile) as silver_store:
        changed = silver_store.read() != derived
    if reparsed is not None:
        with BronzeStore(profile) as bronze:
            bronze.replace_derived_records(reparsed)
    store_silver(lock, silver_inputs, derived)
    return PipelineRebuild(
        silver=SilverRebuild(runs=silver_inputs.runs, result=derived),
        silver_changed=changed,
        gold=_publish(profile, plan),
    )


def rebuild_from_silver(
    lock: WriterLock, inputs: HouseholdInputs | None = None
) -> SilverRebuild:
    """Rebuild the locked profile's Silver from its Bronze store.

    The caller holds the profile's writer lock for its whole command, so the
    Bronze inputs are read under that one lock and handed to the existing
    `budget.silver.rebuild_silver`, which replaces the stored result. The runs
    read here come back with the result, so no caller rereads Bronze. `inputs`
    are the household files the caller already read; without them the decision
    log is read here.
    """
    profile = lock.profile
    log = None if inputs is None else inputs.log
    silver_inputs = bronze_inputs(profile, log)
    result = rebuild_silver(lock, inputs=silver_inputs)
    return SilverRebuild(runs=silver_inputs.runs, result=result)
