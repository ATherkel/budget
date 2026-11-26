# Copyright 2026 Therkel
"""What Kontrol prints: each diagnostic of a selection as a ready line."""

from dataclasses import dataclass, replace
from decimal import Decimal

from budget.analytics import Diagnostics, Provisional, Reconciliation
from budget.dashboard.addresses import answered_address, pinned_url
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.text import (
    account_names,
    coverage_label,
    evidence_line,
    incomplete_months,
)
from budget.dashboard.features.view_state import DEFAULT_VIEW, ViewState

RECONCILIATION_NOTE = (
    "En forskel på 0,00 kr. beviser ikke, at alle posteringer er importeret: "
    "saldiene kan bygge på de samme ufuldstændige posteringer."
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
class ResidualLink:
    """One nonzero residual, linking to its account's activity."""

    element_id: str
    line: str
    url: str


@dataclass(frozen=True)
class AccountRow:
    """One account's row in Kontrol's table: its verdict for the month."""

    account_id: str
    name: str
    # The account's own "Detaljer" for the same month.
    url: str
    verdict: str


@dataclass(frozen=True)
class ChecksView:
    """Kontrol's lines, so its template only loops and prints."""

    accounts: list[AccountRow]
    coverage: str
    incomplete: list[str]
    # Empty when the figures are settled: the template then prints nothing.
    provisional: list[str]
    evidence: list[EvidenceLine]
    nonzero_residuals: list[ResidualLink]
    # The list's heading, or nothing when no residual is known to be nonzero:
    # the template then prints neither heading nor list.
    residuals_heading: list[str]
    reconciliations: list[ReconciliationLines]
    reconciliation_note: str


def _reconciliation_lines(
    reconciliation: Reconciliation, currency: str, period: str
) -> ReconciliationLines:
    """Return each balance and activity component of one account-month."""
    components = (
        ("Startsaldo", reconciliation.opening_balance),
        ("Indtægter minus udgifter", reconciliation.income_minus_expenses),
        ("Overførsler", reconciliation.transfers),
        ("Ukategoriseret ind", reconciliation.unclassified_in),
        ("Ukategoriseret ud", reconciliation.unclassified_out),
        ("Regulering ind", reconciliation.adjustments_in),
        ("Regulering ud", reconciliation.adjustments_out),
        ("Slutsaldo", reconciliation.closing_balance),
    )
    internal = _difference(reconciliation.internal_residual, currency)
    previous = _figure(reconciliation.previous_closing_balance, currency)
    gap = _difference(reconciliation.opening_gap, currency)
    return ReconciliationLines(
        reconciliation.account_id,
        # The account-month's own Coverage: arithmetic never upgrades it.
        f"{reconciliation.display_name}, {period}: "
        f"{coverage_label(reconciliation.coverage)}",
        [f"{label}: {_figure(value, currency)}" for label, value in components],
        [
            f"Intern forskel: {internal}",
            f"Slutsaldo forrige måned: {previous}",
            f"Åbningsforskel: {gap}",
        ],
    )


def _nonzero_residuals(diagnostics: Diagnostics, view: ViewState) -> list[ResidualLink]:
    """Return a link for each residual that is known and nonzero, by account.

    An unknown residual is not listed: it is neither zero nor a known gap.
    Each link keeps the reader's other view choices, such as the comparison.
    """
    address = answered_address(diagnostics.context)
    details = replace(view, mode="advanced", tab="details")
    return [
        ResidualLink(
            f"checks-residual-{reconciliation.account_id}-{kind}",
            f"{reconciliation.display_name}: {label} "
            f"{_difference(value, diagnostics.currency)} (se Detaljer)",
            pinned_url(
                replace(address, accounts=(reconciliation.account_id,)),
                view=details,
            ),
        )
        for reconciliation in diagnostics.reconciliations
        for kind, label, value in (
            ("opening-gap", "Åbningsforskel", reconciliation.opening_gap),
            ("internal", "Intern forskel", reconciliation.internal_residual),
        )
        if value
    ]


def _verdict(reconciliation: Reconciliation) -> str:
    """Return whether one account-month can be trusted, never claiming it adds up."""
    if reconciliation.coverage in ("partial", "no_data"):
        return "Data mangler"
    return "Ingen fundne forskelle"


def _account_rows(diagnostics: Diagnostics, view: ViewState) -> list[AccountRow]:
    """Return each selected account's row, linking to its own "Detaljer"."""
    address = answered_address(diagnostics.context)
    details = replace(view, mode="advanced", tab="details")
    return [
        AccountRow(
            reconciliation.account_id,
            reconciliation.display_name,
            pinned_url(
                replace(address, accounts=(reconciliation.account_id,)),
                view=details,
            ),
            _verdict(reconciliation),
        )
        for reconciliation in diagnostics.reconciliations
    ]


def _figure(value: Decimal | None, currency: str) -> str:
    """Return a reconciliation figure, with a missing one unknown rather than 0."""
    return "Ukendt" if value is None else amount(value, currency)


def _difference(value: Decimal | None, currency: str) -> str:
    """Return a residual with its direction signed, or unknown rather than 0."""
    return "Ukendt" if value is None else signed_amount(value, currency)


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


def checks_view(
    diagnostics: Diagnostics, period: str, view: ViewState = DEFAULT_VIEW
) -> ChecksView:
    """Return Kontrol's lines for `diagnostics` of the month called `period`.

    `view` is the reader's view state, which Kontrol's links carry on.
    """
    incomplete = [
        f"{month.display_name}, {period}: {coverage_label(month.status)}."
        for month in incomplete_months(diagnostics.coverage)
    ]
    nonzero_residuals = _nonzero_residuals(diagnostics, view)
    return ChecksView(
        accounts=_account_rows(diagnostics, view),
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
        nonzero_residuals=nonzero_residuals,
        residuals_heading=["Forskelle at undersøge"] if nonzero_residuals else [],
        reconciliations=[
            _reconciliation_lines(reconciliation, diagnostics.currency, period)
            for reconciliation in diagnostics.reconciliations
        ],
        reconciliation_note=RECONCILIATION_NOTE,
    )
