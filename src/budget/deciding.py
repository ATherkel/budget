# Copyright 2026 Therkel
"""The validation boundary every manual decision passes before it is recorded.

`operations.md`, *The Validation Boundary for Decisions*: the CLI calls it now
and a browser editor calls the same one later, so it sits in the application
layer, not in presentation. The dashboard has no route to it.
"""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from budget.bronze import BronzeStore
from budget.decision_log import (
    DECISION_LOG_FORMAT,
    IMPORT_RUN_KINDS,
    RETRACT,
    history_problems,
    read_decision_log,
    shape_problems,
    typed_decision,
)
from budget.durability import sync_folder
from budget.gold.build import decision_problem
from budget.gold.classification import inapplicable
from budget.gold.decisions import (
    Classify,
    ClassifyAdjustment,
    OneSidedTransfer,
    Pair,
    targets,
)
from budget.gold.transactions import gold_transactions
from budget.inputs import load_configuration
from budget.inputs.rule_checks import KnownIds
from budget.locking import WriterLock
from budget.profiles import DECISION_LOG_FILE_NAME, Profile
from budget.silver.store import SilverStore


@dataclass(frozen=True)
class DecisionProposal:
    """A decision as a person proposes it, before the platform numbers it.

    `details` are the fields the kind carries beyond `targets`, as the log
    writes them: `category` or `adjustment`, `counterpart_account_id`, or
    `record`.
    """

    kind: str
    targets: tuple[str, ...]
    reason: str
    supersedes: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Recorded:
    """The entry the boundary appended to the log."""

    decision_id: str
    entry: int
    recorded_at: str


@dataclass(frozen=True)
class Rejected:
    """Every reason the proposal was refused; nothing was recorded."""

    reasons: tuple[str, ...]


class DecisionLog:
    """The profile's decision log, written only through `propose`."""

    def __init__(self, lock: WriterLock, *, clock: Callable[[], datetime]) -> None:
        """Hold the profile's writer lock; `clock` stamps `recorded_at`."""
        self._lock = lock
        self._clock = clock

    def propose(self, proposal: DecisionProposal) -> Recorded | Rejected:
        """Validate `proposal`, then record it, or reject it naming every reason.

        A recorded entry is appended and forced to disk with `fsync` before
        this returns.
        """
        profile = self._lock.profile
        position = read_decision_log(profile).position + 1
        recorded = Recorded(
            decision_id=f"d-{position:04d}",
            entry=position,
            recorded_at=self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        entry = {
            "format": DECISION_LOG_FORMAT,
            "entry": recorded.entry,
            "decision_id": recorded.decision_id,
            "recorded_at": recorded.recorded_at,
            "kind": proposal.kind,
            "targets": list(proposal.targets),
            **proposal.details,
            "reason": proposal.reason,
            "supersedes": list(proposal.supersedes),
        }
        problems = shape_problems(entry, position) or (
            *history_problems(profile, entry),
            *_target_problems(profile, entry),
            *_configuration_problems(profile, entry),
        )
        if problems:
            return Rejected(problems)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        _append(profile.input_file(DECISION_LOG_FILE_NAME), line.encode("utf-8"))
        return recorded


def _target_problems(profile: Profile, entry: Mapping[str, Any]) -> tuple[str, ...]:
    """Name each target, and a `same-transaction` record, that does not exist.

    Transactions are looked for in the stored Silver, which the rebuild after
    the decision reads; import runs and source records in Bronze.
    """
    kind = entry["kind"]
    if kind == RETRACT:
        return ()
    with BronzeStore(profile) as bronze:
        runs = {run.import_run_id for run in bronze.import_runs()}
        record = entry.get("record")
        record_missing = isinstance(record, dict) and record["record_ordinal"] not in {
            each.record_ordinal
            for each in bronze.get_source_records(record["payload_id"])
        }
    if kind in IMPORT_RUN_KINDS:
        return tuple(
            f"{target} is not an import run in Bronze"
            for target in entry["targets"]
            if target not in runs
        )
    with SilverStore(profile) as silver:
        transactions = {t.transaction_id for t in silver.read().transactions}
    problems = [
        f"{target} is not a transaction in Silver"
        for target in entry["targets"]
        if target not in transactions
    ]
    if record_missing:
        problems.append(
            f"record {record['payload_id']}:{record['record_ordinal']} "
            "is not a source record in Bronze"
        )
    return tuple(problems)


def _configuration_problems(
    profile: Profile, entry: Mapping[str, object]
) -> tuple[str, ...]:
    """Name what the configuration and Silver show wrong with a Gold decision.

    A decision Gold could not apply would only raise a
    `decision-not-applicable` item once built, so it is refused here instead.
    A missing target is named by `_target_problems` already.
    """
    decision = typed_decision(entry)
    if not isinstance(
        decision, Classify | ClassifyAdjustment | Pair | OneSidedTransfer
    ):
        return ()
    configuration = load_configuration(profile)
    known = KnownIds(
        accounts=configuration.accounts.keys(),
        categories=configuration.taxonomy.categories.keys(),
    )
    problem = decision_problem(decision, known)
    if problem is not None:
        return (problem,)
    with SilverStore(profile) as silver:
        transactions = {
            t.transaction_id: t for t in gold_transactions(silver.read().transactions)
        }
    reason = inapplicable(decision, transactions, configuration)
    if reason is None or reason == "target-missing":
        return ()
    return (_NOT_APPLICABLE[reason].format(*targets(decision)),)


# What each `decision-not-applicable` reason says of the decision's targets.
_NOT_APPLICABLE: Mapping[str, str] = {
    "zero-amount": "{0} has a zero amount, so it is neither money in nor out",
    "amounts-do-not-cancel": "the amounts of {0} and {1} do not cancel",
    "same-account": "{0} and {1} are in the same account",
    "inside-managed-period": (
        "{0} falls inside the counterpart account's managed period, "
        "so it is no one-sided transfer"
    ),
}


def _append(path: Path, data: bytes) -> None:
    """Append to the log and force it to disk before going on."""
    created = not path.exists()
    with path.open("ab") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    if created:
        sync_folder(path.parent)
