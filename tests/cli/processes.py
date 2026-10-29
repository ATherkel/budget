# Copyright 2026 Therkel
"""An explicit environment for CLI tests that start a Python subprocess.

A child process never inherits the operator's environment, so a
`BUDGET_PROFILE` set in their shell cannot reach it. Windows needs
`SYSTEMROOT` to start Python at all, so that one variable is carried over.
"""

import os


def explicit_environment(**variables: str) -> dict[str, str]:
    """Return only the variables given, plus what Python needs to start."""
    environment = dict(variables)
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return environment
