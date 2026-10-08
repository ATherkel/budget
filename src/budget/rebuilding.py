# Copyright 2026 Therkel
"""The `rebuild` application operation: build a stage from its upstream.

Silver's build keeps its one definition, the pure `budget.silver.build`, and
this module is only the thin adapter a command calls: it reads the profile's
Bronze inputs and account registry, then hands them to the existing
`budget.silver.rebuild_silver`, which replaces the stored result. No build,
admission, or duplicate-resolution rule lives here.

The decision-log reader is not built yet, so a decision log that holds any
decision refuses the rebuild rather than silently build as if the household had
made none. That guard runs before anything is read or replaced.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from budget.bronze import BronzeStore
from budget.bronze.models import ImportRun
from budget.inputs import ConfigurationError, load_accounts
from budget.locking import WriterLock
from budget.profiles import ACCOUNTS_FILE_NAME, Profile
from budget.silver import SilverBuildInputs, SilverResult, rebuild_silver
from budget.silver.currencies import UnknownCurrencyError, minor_unit_places

DECISION_LOG_NAME: Final = "decisions.jsonl"
_UNREADABLE_DECISIONS: Final = (
    f"{DECISION_LOG_NAME}: the decision-log reader is not built yet, so a log "
    "that holds a decision cannot be ignored; nothing was written. Keep the "
    "log as it is, and rebuild once decision-log support exists."
)


@dataclass(frozen=True)
class SilverRebuild:
    """One Silver rebuild's Bronze provenance and the result it stored.

    The runs are the import runs read under the command's own writer lock,
    before that lock was released, so a summary reports what the build actually
    read instead of rereading a store a later command may have changed.
    """

    runs: Sequence[ImportRun]
    result: SilverResult


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


def rebuild_from_silver(lock: WriterLock) -> SilverRebuild:
    """Rebuild the locked profile's Silver from its Bronze store.

    The caller holds the profile's writer lock for its whole command, so the
    Bronze inputs are read under that one lock and handed to the existing
    `budget.silver.rebuild_silver`, which replaces the stored result. The runs
    read here come back with the result, so no caller rereads Bronze. A
    decision log that holds a decision refuses the rebuild before either.
    """
    profile = lock.profile
    require_no_decisions(profile)
    inputs = bronze_inputs(profile)
    result = rebuild_silver(lock, inputs=inputs)
    return SilverRebuild(runs=inputs.runs, result=result)


def require_no_decisions(profile: Profile) -> None:
    """Refuse a build this code cannot honour the household's decisions in.

    The decision-log reader is not built yet, so a log that holds any decision
    is a configuration error rather than something to ignore. A missing file,
    and a file holding nothing but a byte-order mark or whitespace, mean no
    decisions. A file that cannot be read, or is not UTF-8 text, refuses too:
    nothing was written, the refusal states only the operating system's own
    reason string, and it never repeats the file's contents.
    """
    path = profile.input_file(DECISION_LOG_NAME)
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise ConfigurationError(
            (f"{DECISION_LOG_NAME}: cannot be read: {reason}",)
        ) from None
    if not content:
        return
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ConfigurationError(
            (f"{DECISION_LOG_NAME}: the file is not UTF-8 text",)
        ) from None
    if text.strip():
        raise ConfigurationError((_UNREADABLE_DECISIONS,))
