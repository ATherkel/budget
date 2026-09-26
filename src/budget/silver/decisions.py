# Copyright 2026 Therkel
"""The manual decisions Silver reads, each already effective.

Supersession and retraction are resolved by the decision log boundary
(`operations.md`), so Silver receives only decisions in force.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptDiscrepancy:
    """Admit an import run whose balance break is real in the source (ADR-010)."""

    decision_id: str
    import_run_id: str


@dataclass(frozen=True)
class Withdrawn:
    """The bank removed an admitted transaction (ADR-017)."""

    decision_id: str
    transaction_id: str


@dataclass(frozen=True)
class SameTransaction:
    """A source record shows an existing transaction under new text (ADR-017)."""

    decision_id: str
    transaction_id: str
    payload_id: str
    record_ordinal: int


type SilverDecision = AcceptDiscrepancy | Withdrawn | SameTransaction
