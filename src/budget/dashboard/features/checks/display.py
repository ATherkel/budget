# Copyright 2026 Therkel
"""What Kontrol prints: each diagnostic of a selection as a ready line."""

from dataclasses import dataclass
from decimal import Decimal

from budget.analytics import Diagnostics, Provisional, Reconciliation
from budget.dashboard.display.amounts import amount
from budget.dashboard.display.text import (
    account_names,
    coverage_label,
    evidence_line,
    incomplete_months,
)


@dataclass(frozen=True)
class EvidenceLine:
    """How far one account's imported data reaches, keyed by the account."""

    account_id: str
    line: str


@dataclass(frozen=True)
class ReconciliationLines:
    """One account-month's reconciliation, keyed by the account."""

    account_id: str
    title: str
    components: list[str]
    residuals: list[str]


@dataclass(frozen=True)
class ChecksView:
    """Kontrol's lines, so its template only loops and prints."""

    coverage: str
    incomplete: list[str]
    # Empty when the figures are settled: the template then prints nothing.
    provisional: list[str]
    evidence: list[EvidenceLine]
    reconciliations: list[ReconciliationLines]
    reconciliation_note: str = (
        "En difference på 0,00 kr. beviser ikke, at alle posteringer er "
        "importeret: manglende posteringer og saldi kan gå lige op."
    )


def _reconciliation_lines(
    reconciliation: Reconciliation, currency: str, period: str
) -> ReconciliationLines:
    """Return each balance and activity component of one account-month."""
    components = (
        ("Åbning", reconciliation.opening_balance),
        ("Indtægter minus udgifter", reconciliation.income_minus_expenses),
        ("Overførsler", reconciliation.transfers),
        ("Ukategoriseret ind", reconciliation.unclassified_in),
        ("Ukategoriseret ud", reconciliation.unclassified_out),
        ("Regulering ind", reconciliation.adjustments_in),
        ("Regulering ud", reconciliation.adjustments_out),
        ("Lukning", reconciliation.closing_balance),
    )
    residuals = (
        ("Intern difference", reconciliation.internal_residual),
        ("Lukning forrige måned", reconciliation.previous_closing_balance),
        ("Åbningsforskel", reconciliation.opening_gap),
    )
    return ReconciliationLines(
        reconciliation.account_id,
        # The account-month's own Coverage: arithmetic never upgrades it.
        f"{reconciliation.display_name}, {period}: "
        f"{coverage_label(reconciliation.coverage)}",
        [f"{label}: {_figure(value, currency)}" for label, value in components],
        [f"{label}: {_figure(value, currency)}" for label, value in residuals],
    )


def _figure(value: Decimal | None, currency: str) -> str:
    """Return a reconciliation figure, with a missing one unknown rather than 0."""
    return "Ukendt" if value is None else amount(value, currency)


def _provisional_lines(provisional: Provisional | None, period: str) -> list[str]:
    """Return why the figures for `period` may still change, or nothing."""
    if provisional is None:
        return []
    sentences = []
    if "current_month" in provisional.reasons:
        sentences.append(
            f"{period} er indeværende måned, så der kan stadig komme posteringer."
        )
    if "late_bookings_unsettled" in provisional.reasons:
        names = account_names(provisional.unsettled)
        sentences.append(f"Sene bogføringer kan stadig komme fra {names}.")
    return [f"Foreløbigt: {' '.join(sentences)}"]


def checks_view(diagnostics: Diagnostics, period: str) -> ChecksView:
    """Return Kontrol's lines for `diagnostics` of the month called `period`."""
    incomplete = [
        f"{month.display_name}, {period}: {coverage_label(month.status)}."
        for month in incomplete_months(diagnostics.coverage)
    ]
    return ChecksView(
        coverage=f"Dækning: {coverage_label(diagnostics.coverage.status)}.",
        incomplete=incomplete or ["Ingen valgte kontomåneder mangler dækning."],
        provisional=_provisional_lines(diagnostics.provisional, period),
        evidence=[
            EvidenceLine(
                account.account_id,
                f"{account.display_name}: {evidence_line(account.evidence_through)}",
            )
            for account in diagnostics.evidence
        ],
        reconciliations=[
            _reconciliation_lines(reconciliation, diagnostics.currency, period)
            for reconciliation in diagnostics.reconciliations
        ],
    )
