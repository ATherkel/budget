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

from budget.decision_log import (
    DECISION_LOG_FORMAT,
    history_problems,
    read_decision_log,
    shape_problems,
    typed_decision,
)
from budget.durability import sync_folder
from budget.gold.build import decision_problem
from budget.gold.decisions import Classify, ClassifyAdjustment, OneSidedTransfer, Pair
from budget.inputs import load_configuration
from budget.inputs.rule_checks import KnownIds
from budget.locking import WriterLock
from budget.profiles import DECISION_LOG_FILE_NAME, Profile


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
            *_configuration_problems(profile, entry),
        )
        if problems:
            return Rejected(problems)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        _append(profile.input_file(DECISION_LOG_FILE_NAME), line.encode("utf-8"))
        return recorded


def _configuration_problems(
    profile: Profile, entry: Mapping[str, object]
) -> tuple[str, ...]:
    """Name what the configuration shows wrong with a well-formed entry."""
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
    return () if problem is None else (problem,)


def _append(path: Path, data: bytes) -> None:
    """Append to the log and force it to disk before going on."""
    created = not path.exists()
    with path.open("ab") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    if created:
        sync_folder(path.parent)
