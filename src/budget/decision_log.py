# Copyright 2026 Therkel
"""Reading `decisions.jsonl` into the decisions in force.

The log is append-only (`operations.md`, *`decisions.jsonl`*): every read
re-validates every entry, and an invalid one is a `ConfigurationError` naming
it. The reader returns the effective decisions, typed for Silver and Gold,
with the log position and the SHA-256 of the log up to it, which a recipe
records.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from budget.gold.decisions import Classify, GoldDecision, OneSidedTransfer, Pair
from budget.profiles import DECISION_LOG_FILE_NAME, Profile
from budget.silver.decisions import (
    AcceptDiscrepancy,
    SameTransaction,
    SilverDecision,
    VoidImportRun,
    Withdrawn,
)

_RETRACT = "retract"


@dataclass(frozen=True)
class DecisionLogRead:
    """The decisions in force at the end of the log, and where that end is.

    `position` counts the complete entries read; `prefix_sha256` is the hex
    SHA-256 of the log's bytes through the last line feed.
    """

    silver: tuple[SilverDecision, ...]
    gold: tuple[GoldDecision, ...]
    position: int
    prefix_sha256: str


def _classify(entry: Mapping[str, Any]) -> Classify:
    (target,) = entry["targets"]
    return Classify(entry["decision_id"], target, entry.get("category"))


def _pair(entry: Mapping[str, Any]) -> Pair:
    first, second = entry["targets"]
    return Pair(entry["decision_id"], (first, second))


def _one_sided_transfer(entry: Mapping[str, Any]) -> OneSidedTransfer:
    (target,) = entry["targets"]
    return OneSidedTransfer(
        entry["decision_id"], target, entry["counterpart_account_id"]
    )


def _void_import_run(entry: Mapping[str, Any]) -> VoidImportRun:
    (target,) = entry["targets"]
    return VoidImportRun(entry["decision_id"], target)


def _accept_discrepancy(entry: Mapping[str, Any]) -> AcceptDiscrepancy:
    (target,) = entry["targets"]
    return AcceptDiscrepancy(entry["decision_id"], target)


def _withdrawn(entry: Mapping[str, Any]) -> Withdrawn:
    (target,) = entry["targets"]
    return Withdrawn(entry["decision_id"], target)


def _same_transaction(entry: Mapping[str, Any]) -> SameTransaction:
    (target,) = entry["targets"]
    record = entry["record"]
    return SameTransaction(
        entry["decision_id"], target, record["payload_id"], record["record_ordinal"]
    )


# How each kind in force becomes its typed decision.
_GOLD_KINDS: Mapping[str, Callable[[Mapping[str, Any]], GoldDecision]] = {
    "classify": _classify,
    "pair": _pair,
    "one-sided-transfer": _one_sided_transfer,
}
_SILVER_KINDS: Mapping[str, Callable[[Mapping[str, Any]], SilverDecision]] = {
    "void-import-run": _void_import_run,
    "accept-discrepancy": _accept_discrepancy,
    "withdrawn": _withdrawn,
    "same-transaction": _same_transaction,
}


def read_decision_log(profile: Profile) -> DecisionLogRead:
    """Read and validate the profile's decision log.

    A missing log holds no decisions. A final line without a line feed was cut
    off while it was being written, so it counts as never written.
    """
    try:
        content = profile.input_file(DECISION_LOG_FILE_NAME).read_bytes()
    except FileNotFoundError:
        content = b""
    prefix = content[: content.rfind(b"\n") + 1]
    lines = prefix.decode("utf-8-sig").split("\n")[:-1]
    in_force: dict[str, Mapping[str, Any]] = {}
    for line in lines:
        entry = json.loads(line)
        for superseded in entry["supersedes"]:
            del in_force[superseded]
        if entry["kind"] != _RETRACT:
            in_force[entry["decision_id"]] = entry
    return DecisionLogRead(
        silver=tuple(
            _SILVER_KINDS[e["kind"]](e)
            for e in in_force.values()
            if e["kind"] in _SILVER_KINDS
        ),
        gold=tuple(
            _GOLD_KINDS[e["kind"]](e)
            for e in in_force.values()
            if e["kind"] in _GOLD_KINDS
        ),
        position=len(lines),
        prefix_sha256=hashlib.sha256(prefix).hexdigest(),
    )
