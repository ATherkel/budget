# Copyright 2026 Therkel
"""Dashboard features: each one a folder with its view, templates and CSS."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from jinja2 import Environment

from budget.profiles import Profile


@dataclass(frozen=True)
class Dashboard:
    """What a page needs from the dashboard that serves it."""

    profile: Profile
    clock: Callable[[], datetime]
    templates: Environment
    app: FastAPI
    # Answers a logged-in reader with the response; sends anyone else to log in.
    for_reader: Callable[[Request, Callable[[], Response]], Response]


@dataclass(frozen=True)
class Feature:
    """A feature's folder of templates and CSS, and how it adds its routes."""

    folder: Path
    register: Callable[[Dashboard], None]
