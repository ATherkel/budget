# Copyright 2026 Therkel
"""`budget check`: every problem the inputs and the decision log hold.

The check reads and never writes: it builds nothing, takes no lock and creates
no file (`operations.md`, *Commands*).
"""

from dataclasses import dataclass

from budget.decision_log import (
    cut_off_problem,
    decision_log_bytes,
    replay_decision_log,
)
from budget.gold.build import refuted_decisions
from budget.inputs.snapshot import read_configuration
from budget.profiles import Profile


@dataclass(frozen=True)
class CheckFindings:
    """What `check` found: refused input, one line per problem."""

    problems: tuple[str, ...]


def check(profile: Profile) -> CheckFindings:
    """Judge the profile's input files and decision log, listing every problem.

    The decisions the valid entries leave in force are judged against the
    configuration files that loaded, even when other entries are invalid.
    """
    configuration = read_configuration(profile)
    content = decision_log_bytes(profile)
    log = replay_decision_log(content)
    cut_off = cut_off_problem(content)
    return CheckFindings(
        problems=(
            *configuration.problems,
            *log.problems,
            *refuted_decisions(log.read.gold, configuration.known),
            *(() if cut_off is None else (cut_off,)),
        )
    )
