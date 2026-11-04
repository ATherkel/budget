# Copyright 2026 Therkel
"""`budget check`: every problem the inputs and the decision log hold.

The check reads and never writes: it builds nothing, takes no lock and creates
no file (`operations.md`, *Commands*).
"""

from collections.abc import Callable
from dataclasses import dataclass

from budget.decision_log import read_decision_log
from budget.inputs import ConfigurationError, load_configuration
from budget.profiles import Profile


@dataclass(frozen=True)
class CheckFindings:
    """What `check` found: refused input, one line per problem."""

    problems: tuple[str, ...]


def _problems_of(read: Callable[[], object]) -> tuple[str, ...]:
    """Run one reader, and give every problem it refuses with."""
    try:
        read()
    except ConfigurationError as error:
        return error.problems
    return ()


def check(profile: Profile) -> CheckFindings:
    """Judge the profile's input files and decision log, listing every problem."""
    return CheckFindings(
        problems=(
            *_problems_of(lambda: load_configuration(profile)),
            *_problems_of(lambda: read_decision_log(profile)),
        )
    )
