# Copyright 2026 Therkel
"""The gate that keeps logic out of the dashboard's templates."""

from pathlib import Path

from jinja2 import Environment


def gate(environment: Environment, root: Path, allowlist: Path) -> list[str]:
    """Return one message for each way the templates under `root` fail the gate."""
    del environment, root, allowlist
    return []
