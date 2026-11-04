# Copyright 2026 Therkel
"""`budget check`: every problem the inputs and the decision log hold.

The check reads and never writes: it builds nothing, takes no lock and creates
no file (`operations.md`, *Commands*).
"""

from dataclasses import dataclass

from budget.decision_log import (
    RecordedPrefix,
    cut_off_problem,
    decision_log_bytes,
    prefix_problems,
    replay_decision_log,
)
from budget.gold.build import refuted_decisions
from budget.gold.store import GoldStore
from budget.inputs.snapshot import read_configuration
from budget.profiles import Profile


@dataclass(frozen=True)
class CheckFindings:
    """What `check` found, one line per problem.

    `problems` are refused input; `mismatches` name each publication whose
    recorded decision-log prefix the log no longer holds, a failed
    verification.
    """

    problems: tuple[str, ...]
    mismatches: tuple[str, ...]


def _recorded_prefixes(profile: Profile) -> tuple[RecordedPrefix, ...]:
    """Every recipe's recorded log prefix; none before a Gold store exists.

    The store is opened read-only, so the check creates nothing and writes
    nothing to it.
    """
    if not profile.gold_store.exists():
        return ()
    with GoldStore(profile, read_only=True) as store:
        return tuple(
            RecordedPrefix(
                publication_id,
                recipe.decision_log_position,
                recipe.decision_log_prefix_sha256,
            )
            for publication_id, recipe in store.recipes()
        )


def check(profile: Profile) -> CheckFindings:
    """Judge the profile's input files and decision log, listing every problem.

    The decisions the valid entries leave in force are judged against the
    configuration files that loaded, even when other entries are invalid.
    """
    configuration = read_configuration(profile)
    # Recipes first: the log is append-only, so a log read after them still
    # holds every prefix they record, even if a build appends and publishes
    # between the two reads.
    recorded = _recorded_prefixes(profile)
    content = decision_log_bytes(profile)
    log = replay_decision_log(content)
    cut_off = cut_off_problem(content)
    return CheckFindings(
        problems=(
            *configuration.problems,
            *log.problems,
            *refuted_decisions(log.read.gold, configuration.known),
            *(() if cut_off is None else (cut_off,)),
        ),
        mismatches=prefix_problems(content, recorded),
    )
