# Copyright 2026 Therkel
"""Danish sentences and lists the dashboard shows its reader."""

from collections.abc import Sequence
from datetime import date

from budget.analytics import (
    AccountMonth,
    AccountMonthCoverage,
    ActivityRow,
    BankBalanceObservation,
    InvalidSelectionError,
    MonthlyBalanceObservation,
    ReportCoverage,
)
from budget.analytics.reports import AccountMonthStatus
from budget.analytics.trust import AccountMonthState
from budget.dashboard.display.amounts import amount
from budget.dashboard.display.months import danish_date, month_label
from budget.gold.models import Coverage

_TRANSACTION_KINDS = {
    "income": "Indtægt",
    "expense": "Udgift",
    "refund": "Tilbagebetaling",
    "transfer": "Overførsel, ensidig",
    "adjustment": "Regulering",
}
_COVERAGE_LABELS = {
    "complete": "fuldt dækket",
    "partial": "delvist dækket",
    "no_data": "ingen data",
    "outside_history": "uden for historikken",
}


def selection_problems(error: InvalidSelectionError) -> list[str]:
    """Return a Danish sentence for every selection rule `error` names."""
    problems = [
        f"Kontoen {account_id} findes ikke i disse tal."
        for account_id in error.unknown_account_ids
    ]
    if "no_accounts" in error.reasons:
        problems.append("Vælg mindst én konto.")
    if "mixed_currencies" in error.reasons:
        problems.append("De valgte konti har forskellig valuta.")
    if "month_out_of_range" in error.reasons:
        problems.append("Den valgte måned ligger uden for de måneder, der kan vælges.")
    if "unknown_category" in error.reasons:
        problems.append("Kategorien findes ikke i disse tal.")
    return problems


def incomplete_months(coverage: ReportCoverage) -> list[AccountMonthCoverage]:
    """Return the account-months that lack something, in the report's order.

    Months outside an account's history are never missing anything.
    """
    return [
        account_month
        for account_month in coverage.account_months
        if account_month.status != "outside_history"
    ]


def account_names(months: Sequence[AccountMonth | AccountMonthCoverage]) -> str:
    """Return the accounts of `months` by name, as Danish lists them."""
    return danish_list([month.display_name for month in months])


def incomplete_by_account(coverage: ReportCoverage) -> list[str]:
    """Return each account with incomplete months, as `Konto (januar 2026, …)`.

    Months outside an account's history are never missing anything.
    """
    names: dict[str, str] = {}
    months: dict[str, list[str]] = {}
    for account_month in coverage.account_months:
        if account_month.status != "outside_history":
            names[account_month.account_id] = account_month.display_name
            months.setdefault(account_month.account_id, []).append(
                month_label(account_month.month)
            )
    return [
        f"{names[account_id]} ({', '.join(labels)})"
        for account_id, labels in months.items()
    ]


def transaction_kind(row: ActivityRow) -> str:
    """Return what kind of transaction `row` is, as the reader reads it."""
    paired_on = row.counterpart_transaction_date
    if row.transfer_pairing == "paired" and paired_on is not None:
        counterpart = row.counterpart_account_display_name
        return f"Overførsel, parret med {counterpart} den {danish_date(paired_on)}"
    return _TRANSACTION_KINDS.get(row.transaction_type, "Ukategoriseret")


def coverage_label(state: AccountMonthState) -> str:
    """Return how fully an account-month is covered, such as `delvist dækket`."""
    return _COVERAGE_LABELS[state]


def balance_observation(
    observation: BankBalanceObservation | None, currency: str, missing: str
) -> str:
    """Return the balance the bank stated on a date, or `missing` with none."""
    if observation is None:
        return missing
    on = danish_date(observation.transaction_date)
    if observation.balance_after is None:
        return f"Ukendt den {on}"
    return f"{amount(observation.balance_after, currency)} den {on}"


def coverage_note(status: Coverage, incomplete: list[str], period: str) -> str:
    """Return the sentence that says what the figures for `period` lack.

    `incomplete` names each account that lacks something; with none, no
    selected account has history in the period.
    """
    if not incomplete:
        return f"Ingen af de valgte konti har historik i {period}."
    if status == "no_data":
        return f"Der er ingen data endnu fra {danish_list(incomplete)}."
    return f"Tallene mangler noget fra {danish_list(incomplete)}."


def coverage_gap(status: AccountMonthStatus) -> str:
    """Return what an incomplete account-month lacks, as a sentence's end."""
    if status == "no_data":
        return "der er ingen data for måneden endnu."
    return "kun en del af måneden er dækket."


def evidence_line(through: date | None) -> str:
    """Return how far an account's imported data reaches, in Danish."""
    if through is None:
        return "Ingen importeret data"
    return f"Gennem {danish_date(through)}"


def monthly_snapshot_line(
    snapshot: MonthlyBalanceObservation | None, currency: str
) -> str:
    """Return an account-month's published opening and closing balances."""
    if snapshot is None:
        return "Ingen månedssnapshot"
    opening = amount(snapshot.opening_balance, currency)
    closing = amount(snapshot.closing_balance, currency)
    covered = coverage_label(snapshot.coverage)
    return f"Månedssnapshot: Åbning {opening}; lukning {closing}; {covered}."


def coverage_link_label(incomplete: Sequence[str]) -> str:
    """Return the text of the link that explains a coverage note."""
    return ", ".join(incomplete)


def danish_list(items: list[str]) -> str:
    """Return items as Danish lists them: `A`, `A og B`, `A, B og C`."""
    *rest, last = items or [""]
    return f"{', '.join(rest)} og {last}" if rest else last
