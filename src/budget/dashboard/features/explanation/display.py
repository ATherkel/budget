# Copyright 2026 Therkel
"""What the explanation page prints, prepared so its template only loops and prints."""

from budget.analytics import MonthlyOverview
from budget.dashboard.display.notices import (
    Notice,
    Paragraph,
    newer_figures,
    section,
    shown,
)
from budget.dashboard.display.text import account_names, incomplete_months

_UNCLASSIFIED = (
    "Nogle betalinger i måneden er endnu ikke placeret i en kategori. "
    "Penge tilbage medregner dem ikke, så beløbet kan ændre sig, "
    "når de bliver placeret."
)


def _coverage(overview: MonthlyOverview, month: str) -> Notice:
    """Return why figures are incomplete, or why there are none for `month`."""
    if incomplete_months(overview.coverage):
        return Notice("explanation/coverage_months.html")
    return section(
        "coverage",
        "Hvorfor der ingen tal er",
        (
            Paragraph(
                f"Ingen af de valgte konti har historik i {month}, så der er ingen "
                "tal for måneden. Vælg en anden måned eller andre konti.",
                {"id": "explanation-coverage"},
            ),
        ),
    )


def explanation_notices(overview: MonthlyOverview, month: str) -> tuple[Notice, ...]:
    """Return the sections that explain `overview`, in the order the page shows them.

    `month` is the month's label, as the page names it in a sentence.
    """
    unclassified = overview.unclassified
    return (
        *newer_figures(overview.publication),
        *shown(
            (overview.coverage.status != "complete", _coverage(overview, month)),
            (
                overview.provisional is not None,
                Notice("explanation/provisional.html"),
            ),
            (
                unclassified is not None and unclassified.count > 0,
                section(
                    "unclassified",
                    "Betalinger uden kategori",
                    (Paragraph(_UNCLASSIFIED, {"id": "explanation-unclassified"}),),
                ),
            ),
        ),
    )


def provisional_reasons(overview: MonthlyOverview, month: str) -> tuple[str, ...]:
    """Return a sentence for each reason the figures are provisional, in order.

    `month` is the month's label; it opens the sentence about the current month.
    """
    provisional = overview.provisional
    if provisional is None:
        return ()
    reasons = []
    if "current_month" in provisional.reasons:
        reasons.append(
            f"{month.capitalize()} er indeværende måned, "
            "så der kommer flere posteringer."
        )
    if "late_bookings_unsettled" in provisional.reasons:
        reasons.append(
            "Banken kan stadig bogføre sene posteringer på "
            f"{account_names(provisional.unsettled)}."
        )
    return tuple(reasons)
