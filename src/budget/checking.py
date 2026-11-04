# Copyright 2026 Therkel
"""`budget check`: every problem the inputs and the decision log hold.

The check reads and never writes: it builds nothing, takes no lock and creates
no file (`operations.md`, *Commands*).
"""

from dataclasses import dataclass

from budget.decision_log import read_decision_log
from budget.gold.build import refuted_decisions
from budget.inputs import ConfigurationError
from budget.inputs.snapshot import read_configuration
from budget.profiles import Profile


@dataclass(frozen=True)
class CheckFindings:
    """What `check` found: refused input, one line per problem."""

    problems: tuple[str, ...]


def check(profile: Profile) -> CheckFindings:
    """Judge the profile's input files and decision log, listing every problem."""
    configuration = read_configuration(profile)
    problems = list(configuration.problems)
    try:
        log = read_decision_log(profile)
    except ConfigurationError as error:
        problems.extend(error.problems)
    else:
        problems.extend(refuted_decisions(log.gold, configuration.known))
    return CheckFindings(problems=tuple(problems))
