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
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from budget.gold.decisions import (
    Classify,
    ClassifyAdjustment,
    GoldDecision,
    OneSidedTransfer,
    Pair,
)
from budget.inputs import ConfigurationError
from budget.inputs.fields import (
    TEXT,
    FieldRule,
    is_durable_id,
    is_text,
    key_problems,
    optional,
)
from budget.profiles import DECISION_LOG_FILE_NAME, Profile
from budget.silver.decisions import (
    AcceptDiscrepancy,
    SameTransaction,
    SilverDecision,
    VoidImportRun,
    Withdrawn,
)

_FORMAT_VERSION = 1
_RETRACT = "retract"

# `recorded_at` as the platform writes it: UTC, to the second.
_UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

type Entry = Mapping[str, Any]


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


def _is_id(value: object) -> bool:
    """Accept a durable ID such as `d-0001` or `joint-savings`."""
    return isinstance(value, str) and is_durable_id(value)


def _is_utc_time(value: object) -> bool:
    """Accept a real UTC time to the second, such as `2026-04-10T17:02:11Z`."""
    if not isinstance(value, str) or _UTC_TIME.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_ordinal(value: object) -> bool:
    """Accept a whole number from 0; JSON's `true` is not one."""
    return type(value) is int and value >= 0


def _lists_ids(value: object) -> bool:
    """Accept a list of durable IDs, which may be empty."""
    return isinstance(value, list) and all(_is_id(item) for item in value)


def _targets(count: int) -> FieldRule:
    """Accept a list of exactly `count` non-empty identifiers."""
    noun = "target" if count == 1 else "targets"
    return FieldRule(
        accepts=lambda value: (
            isinstance(value, list)
            and len(value) == count
            and all(is_text(target) for target in value)
        ),
        rule=f"must list exactly {count} {noun}",
    )


# Keys judged apart from the table: `format` and `kind` before the others,
# and a retract's `targets` by its kind.
_JUDGED_APART = FieldRule(lambda _: True, "is judged apart")
_ID = FieldRule(_is_id, "must be lowercase words joined by hyphens")
_RECORD_FIELDS: Mapping[str, FieldRule] = {
    "payload_id": TEXT,
    "record_ordinal": FieldRule(_is_ordinal, "must be a whole number from 0"),
}


def _no_problems(_: Entry) -> list[str]:
    """Find nothing beyond the keys, which say everything for most kinds."""
    return []


def _classify_problems(entry: Entry) -> list[str]:
    """Require a category or `"adjustment": true` of a `classify`, not both."""
    if ("category" in entry) == ("adjustment" in entry):
        return ["classify must give exactly one of category or adjustment"]
    return []


def _record_problems(entry: Entry) -> list[str]:
    """Judge a `same-transaction` record's own keys."""
    record = entry.get("record")
    if not isinstance(record, dict):
        return []
    return key_problems(record, _RECORD_FIELDS, prefix="record.")


def _retract_problems(entry: Entry) -> list[str]:
    """Require a `retract` to target nothing and withdraw at least one decision."""
    problems = []
    if entry.get("targets", []) != []:
        problems.append("a retract has no targets")
    if not entry.get("supersedes"):
        problems.append("a retract must supersede a decision")
    return problems


@dataclass(frozen=True)
class _Kind:
    """What an entry of one kind carries beyond the keys every entry has."""

    targets: int
    fields: Mapping[str, FieldRule]
    problems: Callable[[Entry], list[str]] = _no_problems


_KINDS: Mapping[str, _Kind] = {
    "classify": _Kind(
        1,
        {
            "category": optional(_ID),
            "adjustment": optional(FieldRule(lambda v: v is True, "must be true")),
        },
        _classify_problems,
    ),
    "pair": _Kind(2, {}),
    "one-sided-transfer": _Kind(1, {"counterpart_account_id": _ID}),
    "void-import-run": _Kind(1, {}),
    "accept-discrepancy": _Kind(1, {}),
    "withdrawn": _Kind(1, {}),
    "same-transaction": _Kind(
        1,
        {"record": FieldRule(lambda v: isinstance(v, dict), "must be an object")},
        _record_problems,
    ),
    _RETRACT: _Kind(0, {"targets": _JUDGED_APART}, _retract_problems),
}


def _kind_refusal(entry: Entry) -> list[str]:
    """Refuse an entry whose format or kind gives its other keys no meaning."""
    version = entry.get("format")
    if version is None:
        return ["format is missing"]
    if type(version) is not int or version != _FORMAT_VERSION:
        return [f"format must be {_FORMAT_VERSION}"]
    kind = entry.get("kind")
    if kind is None:
        return ["kind is missing"]
    if not isinstance(kind, str) or kind not in _KINDS:
        return [f"kind {json.dumps(kind)} is not a decision kind"]
    return []


def _shape_problems(entry: Entry, position: int) -> list[str]:
    """Judge one entry on its own: its format, kind and keys."""
    refusal = _kind_refusal(entry)
    if refusal:
        return refusal
    kind = _KINDS[entry["kind"]]
    fields = {
        "format": _JUDGED_APART,
        "entry": FieldRule(
            lambda value: type(value) is int and value == position,
            f"must be {position}, its position in the log",
        ),
        "decision_id": _ID,
        "recorded_at": FieldRule(
            _is_utc_time, "must be a UTC time such as 2026-04-10T17:02:11Z"
        ),
        "kind": _JUDGED_APART,
        "targets": _targets(kind.targets),
        "reason": TEXT,
        "supersedes": FieldRule(_lists_ids, "must list decision IDs"),
        **kind.fields,
    }
    return [
        *key_problems(entry, fields),
        *_repeats(entry, "targets"),
        *_repeats(entry, "supersedes"),
        *kind.problems(entry),
    ]


def _repeats(entry: Entry, key: str) -> list[str]:
    """Name each ID a list key holds more than once.

    A `pair` of one transaction with itself is no transfer, and a decision
    superseded twice would be withdrawn twice.
    """
    values = entry.get(key)
    if not isinstance(values, list):
        return []
    ids = [value for value in values if isinstance(value, str)]
    return [
        f"{key} lists {value} more than once"
        for value in dict.fromkeys(ids)
        if ids.count(value) > 1
    ]


def _clashes(entry: Entry, in_force: Mapping[str, Entry]) -> list[str]:
    """Each target a decision in force holds that `entry` does not supersede.

    ADR-011 allows at most one decision per target, so a new one must list
    the old in `supersedes` (`publications.md`, *The Decision Log*).
    """
    holders = {
        target: decision_id
        for decision_id, held in in_force.items()
        for target in held["targets"]
    }
    return [
        f"{target} is already decided by {holders[target]}, "
        "which supersedes does not list"
        for target in entry["targets"]
        if target in holders and holders[target] not in entry["supersedes"]
    ]


def _parse(line: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Read one line as a JSON object, or `None`, with each key it repeats.

    `json.loads` alone keeps the last of a repeated key, so what a person
    reads in the line would differ from what takes effect.
    """
    repeated: list[str] = []

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        table: dict[str, Any] = {}
        for key, value in pairs:
            if key in table and key not in repeated:
                repeated.append(key)
            table[key] = value
        return table

    try:
        entry = json.loads(line, object_pairs_hook=unique)
    except json.JSONDecodeError:
        return None, []
    return (entry if isinstance(entry, dict) else None), repeated


def _problem(position: int, decision_id: object, text: str) -> str:
    """Name the log, then the entry by its position and, if it has one, its ID."""
    name = f"entry {position}"
    if isinstance(decision_id, str):
        name += f" ({decision_id})"
    return f"{DECISION_LOG_FILE_NAME}: {name}: {text}"


@dataclass
class _Replay:
    """The log read so far: the decisions in force, and what was wrong.

    An invalid entry never comes into force, so the entries after it are
    judged against the log as if it were not there.
    """

    in_force: dict[str, Entry] = field(default_factory=dict)
    used: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def read(self, position: int, line: str) -> None:
        """Judge the entry at `position`, then bring it into force if valid."""
        entry, repeated = _parse(line)
        if entry is None:
            self.problems.append(_problem(position, None, "must be one JSON object"))
            return
        found = (
            [f'key "{key}" appears more than once' for key in repeated]
            or _shape_problems(entry, position)
            or self._history_problems(entry)
        )
        if found:
            decision_id = entry.get("decision_id")
            self.problems.extend(_problem(position, decision_id, t) for t in found)
            return
        self.used[entry["decision_id"]] = position
        for superseded in entry["supersedes"]:
            del self.in_force[superseded]
        if entry["kind"] != _RETRACT:
            self.in_force[entry["decision_id"]] = entry

    def _history_problems(self, entry: Entry) -> list[str]:
        """Judge a well-formed entry against the entries before it."""
        decision_id = entry["decision_id"]
        problems = []
        if decision_id in self.used:
            problems.append(
                f"decision_id {decision_id} is already used by "
                f"entry {self.used[decision_id]}"
            )
        problems.extend(
            f"supersedes {superseded}, which is not in force"
            for superseded in entry["supersedes"]
            if superseded not in self.in_force
        )
        problems.extend(_clashes(entry, self.in_force))
        return problems


def _classify(entry: Entry) -> Classify | ClassifyAdjustment:
    (target,) = entry["targets"]
    if entry.get("adjustment") is True:
        return ClassifyAdjustment(entry["decision_id"], target)
    return Classify(entry["decision_id"], target, entry["category"])


def _pair(entry: Entry) -> Pair:
    first, second = entry["targets"]
    return Pair(entry["decision_id"], (first, second))


def _one_sided_transfer(entry: Entry) -> OneSidedTransfer:
    (target,) = entry["targets"]
    return OneSidedTransfer(
        entry["decision_id"], target, entry["counterpart_account_id"]
    )


def _void_import_run(entry: Entry) -> VoidImportRun:
    (target,) = entry["targets"]
    return VoidImportRun(entry["decision_id"], target)


def _accept_discrepancy(entry: Entry) -> AcceptDiscrepancy:
    (target,) = entry["targets"]
    return AcceptDiscrepancy(entry["decision_id"], target)


def _withdrawn(entry: Entry) -> Withdrawn:
    (target,) = entry["targets"]
    return Withdrawn(entry["decision_id"], target)


def _same_transaction(entry: Entry) -> SameTransaction:
    (target,) = entry["targets"]
    record = entry["record"]
    return SameTransaction(
        entry["decision_id"], target, record["payload_id"], record["record_ordinal"]
    )


# How each kind in force becomes its typed decision.
_GOLD_KINDS: Mapping[str, Callable[[Entry], GoldDecision]] = {
    "classify": _classify,
    "pair": _pair,
    "one-sided-transfer": _one_sided_transfer,
}
_SILVER_KINDS: Mapping[str, Callable[[Entry], SilverDecision]] = {
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
    try:
        lines = prefix.decode("utf-8-sig").split("\n")[:-1]
    except UnicodeDecodeError:
        problem = f"{DECISION_LOG_FILE_NAME}: the file is not UTF-8"
        raise ConfigurationError((problem,)) from None
    replay = _Replay()
    for position, line in enumerate(lines, start=1):
        replay.read(position, line)
    if replay.problems:
        raise ConfigurationError(tuple(replay.problems))
    in_force = replay.in_force.values()
    return DecisionLogRead(
        silver=tuple(
            _SILVER_KINDS[e["kind"]](e) for e in in_force if e["kind"] in _SILVER_KINDS
        ),
        gold=tuple(
            _GOLD_KINDS[e["kind"]](e) for e in in_force if e["kind"] in _GOLD_KINDS
        ),
        position=len(lines),
        prefix_sha256=hashlib.sha256(prefix).hexdigest(),
    )
