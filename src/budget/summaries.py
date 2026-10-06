# Copyright 2026 Therkel
"""The terminal summaries the pipeline commands end with.

These lines reach the operator's terminal, never a routine log: they count
import runs and review items and name no amount, balance, description, bank
category, original filename, or account number.
"""

from budget.silver import SilverResult


def rebuild_summary(result: SilverResult) -> str:
    """Report one rebuild's admitted and quarantined import-run counts."""
    admitted = sum(1 for run in result.import_run_results if run.status == "accepted")
    quarantined = sum(
        1 for run in result.import_run_results if run.status == "quarantined"
    )
    return f"Silver   {admitted} admitted, {quarantined} quarantined\n"
