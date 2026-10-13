# Copyright 2026 Therkel
"""The manual decisions Gold classification reads, each already effective.

Supersession and retraction are resolved by the decision log reader
(`publications.md`, *The Decision Log*), so Gold receives only decisions in
force. Their kinds are `classification.md`'s *Manual Decisions*.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Classify:
    """Classify one transaction into a category."""

    decision_id: str
    transaction_id: str
    category_id: str


@dataclass(frozen=True)
class ClassifyAdjustment:
    """Classify one transaction as an adjustment, which takes no category."""

    decision_id: str
    transaction_id: str


@dataclass(frozen=True)
class Pair:
    """Join two transactions on different accounts as one transfer (ADR-012)."""

    decision_id: str
    transaction_ids: tuple[str, str]


@dataclass(frozen=True)
class OneSidedTransfer:
    """A transfer whose other leg falls outside its account's managed period."""

    decision_id: str
    transaction_id: str
    counterpart_account_id: str


type GoldDecision = Classify | ClassifyAdjustment | Pair | OneSidedTransfer
