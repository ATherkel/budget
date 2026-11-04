# Copyright 2026 Therkel
"""`budget check`: every problem the inputs and the decision log hold.

The check reads and never writes: it builds nothing, takes no lock and creates
no file (`operations.md`, *Commands*).
"""

from collections.abc import Callable
from dataclasses import dataclass

from budget.decision_log import read_decision_log
from budget.gold.build import refuted_decisions
from budget.inputs import ConfigurationError, load_configuration
from budget.inputs.rule_checks import KnownIds
from budget.profiles import Profile


@dataclass(frozen=True)
class CheckFindings:
    """What `check` found: refused input, one line per problem."""

    problems: tuple[str, ...]


def _attempt[T](read: Callable[[], T], problems: list[str]) -> T | None:
    """Run one reader, or keep every problem it refuses with and give nothing."""
    try:
        return read()
    except ConfigurationError as error:
        problems.extend(error.problems)
        return None


def check(profile: Profile) -> CheckFindings:
    """Judge the profile's input files and decision log, listing every problem."""
    problems: list[str] = []
    configuration = _attempt(lambda: load_configuration(profile), problems)
    log = _attempt(lambda: read_decision_log(profile), problems)
    if configuration is not None and log is not None:
        known = KnownIds(
            accounts=configuration.accounts.keys(),
            categories=configuration.taxonomy.categories.keys(),
        )
        problems.extend(refuted_decisions(log.gold, known))
    return CheckFindings(problems=tuple(problems))
