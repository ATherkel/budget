# Copyright 2026 Therkel
"""Dashboard features: each one a folder with its view, templates and CSS."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from jinja2 import Environment

from budget.profiles import Profile


@dataclass(frozen=True)
class Dashboard:
    """What a page needs from the dashboard that serves it."""

    profile: Profile
    clock: Callable[[], datetime]
    templates: Environment
