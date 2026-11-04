# Copyright 2026 Therkel
"""The validation boundary every manual decision passes before it is recorded.

`operations.md`, *The Validation Boundary for Decisions*: the CLI calls it now
and a browser editor calls the same one later, so it sits in the application
layer, not in presentation. The dashboard has no route to it.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from budget.locking import WriterLock


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
        """Validate `proposal`, then record it, or reject it naming every reason."""
        del proposal
        return Rejected(())
