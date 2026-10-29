# Copyright 2026 Therkel
"""Test package for unittest discovery from the repository root.

The suite never inherits a profile from the operator's shell, so a value set in
`BUDGET_PROFILE` is removed as soon as the package is imported.
"""

import os

os.environ.pop("BUDGET_PROFILE", None)
