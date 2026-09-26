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


type SilverDecision = AcceptDiscrepancy
