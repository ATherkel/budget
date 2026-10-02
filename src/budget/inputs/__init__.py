# Copyright 2026 Therkel
"""Household inputs: what the household authors as text in its inputs folder.

`budget.inputs` is the seam the rest of the application imports. Each file is
read through the profile that names the folder, validated whole, and returned
as an immutable value; a file that breaks its rules is a `ConfigurationError`
naming the file, the entry and the problem (`operations.md`, *Household
Inputs*).
"""

from budget.inputs.accounts import (
    Account,
    ConfigurationError,
    MisfiledExportError,
    load_accounts,
)

__all__ = ["Account", "ConfigurationError", "MisfiledExportError", "load_accounts"]
