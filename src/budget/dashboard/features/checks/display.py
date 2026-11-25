# Copyright 2026 Therkel
"""What Kontrol prints: each diagnostic of a selection as a ready line."""

from dataclasses import dataclass, replace
from decimal import Decimal

from budget.analytics import (
    Diagnostics,
    MoneyInOut,
    Provisional,
    Reconciliation,
    TransferSummary,
)
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


OBSERVED_NOTE = (
    "Antallene er observerede transaktioner på de valgte konti. "
    "En overførsel kan tælle to gange, når begge konti er valgt."
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
class ObservedLines:
    """One selected transaction type, with its two directions kept apart."""

    kind: str
    title: str
    money_in: str
    money_out: str
    count: str


@dataclass(frozen=True)
class ChecksView:
    """Kontrol's lines, so its template only loops and prints."""

    coverage: str
    incomplete: list[str]
    # Empty when the figures are settled: the template then prints nothing.
    provisional: list[str]
    evidence: list[EvidenceLine]
    # Empty when no residual is known to be nonzero: the template prints nothing.
    nonzero_residuals: list[ResidualLink]
    reconciliations: list[ReconciliationLines]
    reconciliation_note: str
    observed: list[ObservedLines]
    observed_note: str
    transfer_pairing: str


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


def _observed_lines(
    kind: str, title: str, values: MoneyInOut | TransferSummary | None, currency: str
) -> ObservedLines:
    """Format analytics-supplied directions and the observed transaction count."""
    if values is None:
        return ObservedLines(kind, title, "Ukendt", "Ukendt", "Ukendt")
    return ObservedLines(
        kind,
        title,
        signed_amount(values.money_in, currency),
        signed_amount(values.money_out, currency),
        str(values.count),
    )


def _transfer_pairing(transfers: TransferSummary | None) -> str:
    """Describe selected paired and one-sided legs, keeping unknown counts explicit."""
    if transfers is None:
        return (
            "Parring af overførsler: Ukendt antal parrede ben "
            "og Ukendt antal ensidige ben."
        )
    paired = "parret ben" if transfers.paired_count == 1 else "parrede ben"
    one_sided = "ensidigt ben" if transfers.one_sided_count == 1 else "ensidige ben"
    return (
        f"Parring af overførsler: {transfers.paired_count} {paired} "
        f"og {transfers.one_sided_count} {one_sided}."
    )


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
        nonzero_residuals=_nonzero_residuals(diagnostics, view),
        reconciliations=[
            _reconciliation_lines(reconciliation, diagnostics.currency, period)
            for reconciliation in diagnostics.reconciliations
        ],
        reconciliation_note=RECONCILIATION_NOTE,
        observed_note=OBSERVED_NOTE,
        transfer_pairing=_transfer_pairing(diagnostics.transfers),
        observed=[
            _observed_lines(kind, title, values, diagnostics.currency)
            for kind, title, values in (
                ("unclassified", "Ukategoriseret", diagnostics.unclassified),
                ("adjustments", "Reguleringer", diagnostics.adjustments),
                ("transfers", "Overførsler", diagnostics.transfers),
            )
        ],
    )
