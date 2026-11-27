# Copyright 2026 Therkel
"""What Kontrol prints: each diagnostic of a selection as a ready line."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from budget.analytics import Diagnostics, Provisional, Reconciliation
from budget.dashboard.addresses import answered_address, pinned_url
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import (
    account_names,
    coverage_label,
    incomplete_months,
)
from budget.dashboard.features.view_state import DEFAULT_VIEW, ViewState

RECONCILIATION_NOTE = (
    "En forskel på 0,00 kr. beviser ikke, at alle posteringer er importeret: "
    "saldiene kan bygge på de samme ufuldstændige posteringer."
)


@dataclass(frozen=True)
class WaterfallStep:
    """One line of an account's month, from its start to its end balance."""

    label: str
    # Empty where the line has no amount of its own, such as the computed close.
    amount: str
    # Empty where the line is not part of the running total.
    total: str


@dataclass(frozen=True)
class AccountRow:
    """One account's row in Kontrol's table: its verdict for the month."""

    account_id: str
    name: str
    # The account's own "Detaljer" for the same month.
    url: str
    verdict: str
    opening: str
    closing: str
    internal: str
    gap: str
    through: str
    waterfall: list[WaterfallStep]


@dataclass(frozen=True)
class ChecksView:
    """Kontrol's lines, so its template only loops and prints."""

    accounts: list[AccountRow]
    coverage: str
    incomplete: list[str]
    # Empty when the figures are settled: the template then prints nothing.
    provisional: list[str]
    reconciliation_note: str


def _verdict(reconciliation: Reconciliation, currency: str) -> str:
    """Return whether one account-month can be trusted, never claiming it adds up."""
    if reconciliation.coverage in ("partial", "no_data"):
        return "Data mangler"
    if reconciliation.coverage == "outside_history":
        return "Uden for historikken"
    unknown = None in (
        reconciliation.opening_balance,
        reconciliation.closing_balance,
        reconciliation.internal_residual,
        reconciliation.opening_gap,
    )
    if unknown:
        return "Ukendt"
    # The internal residual is shown first: it is the month's own arithmetic.
    residual = reconciliation.internal_residual or reconciliation.opening_gap
    if residual:
        return f"Går ikke op ({signed_amount(residual, currency)})"
    return "Ingen fundne forskelle"


def _waterfall(reconciliation: Reconciliation, currency: str) -> list[WaterfallStep]:
    """Return the month's steps with a running total, unknown from a missing step."""
    flows = (
        ("Indtægter minus udgifter", reconciliation.income_minus_expenses),
        ("Overførsler", reconciliation.transfers),
        ("Ukategoriseret ind", reconciliation.unclassified_in),
        ("Ukategoriseret ud", reconciliation.unclassified_out),
        ("Regulering ind", reconciliation.adjustments_in),
        ("Regulering ud", reconciliation.adjustments_out),
    )
    total = reconciliation.opening_balance
    steps = [WaterfallStep("Startsaldo", "", _figure(total, currency))]
    for label, value in flows:
        total = None if total is None or value is None else total + value
        steps.append(
            WaterfallStep(label, _difference(value, currency), _figure(total, currency))
        )
    return [
        *steps,
        WaterfallStep("Beregnet slutsaldo", "", _figure(total, currency)),
        # Under the computed close, so the two closes compare in one column.
        WaterfallStep(
            "Bankens slutsaldo", "", _figure(reconciliation.closing_balance, currency)
        ),
        WaterfallStep(
            "Forskel", _difference(reconciliation.internal_residual, currency), ""
        ),
    ]


def _account_rows(diagnostics: Diagnostics, view: ViewState) -> list[AccountRow]:
    """Return each selected account's row, linking to its own "Detaljer"."""
    address = answered_address(diagnostics.context)
    details = replace(view, mode="advanced", tab="details")
    currency = diagnostics.currency
    through = {
        account.account_id: _data_reach(account.evidence_through)
        for account in diagnostics.evidence
    }
    return [
        AccountRow(
            reconciliation.account_id,
            reconciliation.display_name,
            pinned_url(
                replace(address, accounts=(reconciliation.account_id,)),
                view=details,
            ),
            _verdict(reconciliation, currency),
            _figure(reconciliation.opening_balance, currency),
            _figure(reconciliation.closing_balance, currency),
            _difference(reconciliation.internal_residual, currency),
            _difference(reconciliation.opening_gap, currency),
            through.get(reconciliation.account_id, "Ukendt"),
            _waterfall(reconciliation, currency),
        )
        for reconciliation in diagnostics.reconciliations
    ]


def _data_reach(through: date | None) -> str:
    """Return the date under "Data til og med", or say nothing was imported."""
    return "Ingen importeret data" if through is None else danish_date(through)


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
    return ChecksView(
        accounts=_account_rows(diagnostics, view),
        coverage=f"Dækning: {coverage_label(diagnostics.coverage.status)}.",
        incomplete=incomplete or ["Ingen valgte kontomåneder mangler dækning."],
        provisional=_provisional_lines(diagnostics.provisional, period),
        reconciliation_note=RECONCILIATION_NOTE,
    )
