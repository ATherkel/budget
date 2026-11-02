"""Build the synthetic fixture for the #11 dashboard prototype.

Throwaway preparation, not an import engine: it reads nothing but the
constants in this file, writes ``example.json``, and never touches ``imports/``
or any bank data. It stands in for the analytics layer by precomputing the
report DTOs the screen renders, so the browser never adds up money.

Every account, amount, date and description below is invented. Run it from the
repository root:

    py -3.12 prototypes/dashboard-11/build_example.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "example.json"

CENT = Decimal("0.01")
CURRENCY = "DKK"
LATE_BOOKING_DAYS = 7
MONTH_NAMES = (
    "januar",
    "februar",
    "marts",
    "april",
    "maj",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "december",
)
KIND_LABELS = {
    "income": "Indtægter",
    "expense": "Køb eller betaling",
    "refund": "Penge tilbage",
    "transfer": "Mellem vores konti",
    "adjustment": "Anden rettelse",
    "unknown": "Mangler en kategori",
}
COMPLETE = "complete"
PARTIAL = "partial"
NO_DATA = "no_data"

UNCLASSIFIED_DETAIL = (
    "Ikke med i indtægter, udgifter eller beløbet tilbage. Posteringerne kan "
    "være køb, indtægter eller overførsler. Det er ikke afgjort i dette eksempel."
)
ADJUSTMENT_DETAIL = (
    "Rettelser uden kategori vises særskilt og er ikke med i indtægter og udgifter."
)
OPERATOR_ROUTE = {
    "review": "budget review",
    "decide": "budget decide",
    "detail": (
        "Manglende kategorier afgøres uden for visningen: `budget review` viser de "
        "åbne punkter, og `budget decide` registrerer afgørelsen. Prototypen "
        "udfører ingen af dem."
    ),
}
EXCLUDED_FROM_MEASURES = (
    "Beløb uden kategori",
    "Rettelser uden kategori",
    "Overførsler mellem vores konti",
)


def money(amount: str | Decimal) -> str:
    """Format an amount as a two-decimal string."""
    return f"{Decimal(amount).quantize(CENT):.2f}"


def total(amounts: Iterable[str | Decimal]) -> Decimal:
    """Sum amounts as decimals, never as floats."""
    return sum((Decimal(amount) for amount in amounts), Decimal(0))


def month_of(day: str) -> str:
    """Return the reporting month of an ISO date."""
    return day[:7]


def month_label(month: str) -> str:
    """Return a Danish month label such as ``september 2026``."""
    return f"{MONTH_NAMES[int(month[5:7]) - 1]} {month[:4]}"


def date_label(day: str) -> str:
    """Return a short Danish date label such as ``14. september``."""
    return f"{int(day[8:10])}. {MONTH_NAMES[int(day[5:7]) - 1]}"


def month_bounds(month: str) -> tuple[str, str]:
    """Return the first and last day of a reporting month."""
    year = int(month[:4])
    number = int(month[5:7])
    first = date(year, number, 1)
    last = date(year + number // 12, number % 12 + 1, 1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def months_between(first: str, last: str) -> list[str]:
    """Return every reporting month from first to last, inclusive."""
    start = int(first[:4]) * 12 + int(first[5:7]) - 1
    stop = int(last[:4]) * 12 + int(last[5:7]) - 1
    return [f"{index // 12}-{index % 12 + 1:02d}" for index in range(start, stop + 1)]


def amount_of(transaction: Transaction) -> Decimal:
    """Return a transaction amount as a decimal."""
    return Decimal(transaction.amount)


@dataclass(frozen=True)
class Account:
    """One synthetic account inside the reporting boundary."""

    account_id: str
    name: str
    owner_label: str
    managed_from: str
    opening_balance: str
    balance_carried_on: str
    account_type: str = "current"
    ownership_scope: str = "household"


@dataclass(frozen=True)
class Export:
    """One synthetic admitted export: the range it covers and when it was made."""

    covers_from: str
    covers_through: str
    produced_on: str
    imported_on: str
    account_id: str

    def covers(self, day: str) -> bool:
        """Return whether the export's declared range contains the date."""
        return self.covers_from <= day <= self.covers_through

    def finalizes(self, period_end: str) -> bool:
        """Return whether this export closes a period end under the seven-day rule."""
        needed = (
            date.fromisoformat(period_end) + timedelta(days=LATE_BOOKING_DAYS)
        ).isoformat()
        return self.covers(period_end) and self.produced_on >= needed


@dataclass(frozen=True)
class Category:
    """One synthetic category, with the names in force over time."""

    category_id: str
    name: str
    renamed_to: str | None = None
    renamed_on: str | None = None

    def name_at(self, moment: str) -> str:
        """Return the category name in force at the given date."""
        if self.renamed_on and self.renamed_to and self.renamed_on <= moment:
            return self.renamed_to
        return self.name


@dataclass(frozen=True)
class Stage:
    """One classification stage: what the household believed from a date."""

    effective_from: str
    kind: str
    category_id: str | None = None


@dataclass(frozen=True)
class Transaction:
    """One booked synthetic transaction with its classification history."""

    transaction_id: str
    account_id: str
    day: str
    amount: str
    description: str
    kind: str
    category_id: str | None = None
    imported_on: str | None = None
    restaged: tuple[Stage, ...] = ()
    transfer_group: str | None = None
    counterpart: str | None = None

    def imported_by(self, moment: str) -> bool:
        """Return whether the platform knew of this transaction by the date."""
        return (self.imported_on or self.day) <= moment

    def stage_at(self, moment: str) -> Stage:
        """Return the classification in force at the given date."""
        stage = Stage(self.day, self.kind, self.category_id)
        for change in self.restaged:
            if change.effective_from <= moment:
                stage = change
        return stage


@dataclass(frozen=True)
class Publication:
    """One synthetic Gold publication the prototype can show."""

    publication_id: str
    kind: str
    kind_label: str
    label: str
    detail: str
    known_at: str
    built_at: str
    interpretation_at: str
    first_month: str
    last_month: str
    is_current: bool


@dataclass(frozen=True)
class Coverage:
    """The trust status of one account for one reporting month."""

    status: str
    label: str
    short_label: str
    detail: str
    reason: str

    def to_json(self) -> dict[str, object]:
        """Return the account-level coverage block."""
        return {
            "status": self.status,
            "label": self.label,
            "shortLabel": self.short_label,
            "detail": self.detail,
        }


ACCOUNTS = (
    Account("mine", "Min konto", "Min", "2026-04", "20000.00", "2026-09-14"),
    Account("common", "Fælleskonto", "Fælles", "2026-05", "18000.00", "2026-07-15"),
)

CATEGORIES = (
    Category("housing", "Bolig"),
    Category("groceries", "Dagligvarer"),
    Category("bills", "Faste regninger"),
    Category("transport", "Transport"),
    Category("dining", "Café og restaurant"),
    Category("clothes", "Tøj", renamed_to="Tøj og sko", renamed_on="2026-09-01"),
    Category("home", "Boligudstyr og møbler"),
)

EXPORTS = {
    "mine": (
        Export("2026-04-01", "2026-05-31", "2026-06-10", "2026-06-10", "mine"),
        Export("2026-06-01", "2026-06-30", "2026-07-12", "2026-07-12", "mine"),
        Export("2026-07-01", "2026-07-31", "2026-08-12", "2026-08-12", "mine"),
        Export("2026-08-01", "2026-08-25", "2026-08-25", "2026-08-25", "mine"),
        Export("2026-09-01", "2026-09-14", "2026-09-14", "2026-09-14", "mine"),
    ),
    "common": (
        Export("2026-05-01", "2026-06-30", "2026-07-12", "2026-07-12", "common"),
        Export("2026-07-01", "2026-07-31", "2026-08-12", "2026-08-12", "common"),
        Export("2026-08-01", "2026-08-31", "2026-09-05", "2026-09-05", "common"),
    ),
}

TRANSACTIONS = (
    # April: the first month for Min konto, and outside Fælleskonto's managed
    # period, which is why the large outgoing leg is a one-sided transfer.
    Transaction("tx-apr-salary", "mine", "2026-04-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-apr-rent", "mine", "2026-04-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-apr-bills",
        "mine",
        "2026-04-05",
        "-1100.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-apr-groceries",
        "mine",
        "2026-04-11",
        "-2300.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-apr-saving",
        "mine",
        "2026-04-18",
        "-2000.00",
        "Overførsel til Fælleskonto",
        "transfer",
        None,
        None,
        (),
        None,
        "common",
    ),
    Transaction(
        "tx-apr-transport",
        "mine",
        "2026-04-22",
        "-740.00",
        "Periodekort",
        "expense",
        "transport",
    ),
    # May: Fælleskonto's first month, and a transfer-looking leg with no
    # counterpart anywhere in the household's accounts.
    Transaction("tx-may-salary", "mine", "2026-05-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-may-rent", "mine", "2026-05-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-may-bills",
        "mine",
        "2026-05-05",
        "-1100.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-may-groceries",
        "mine",
        "2026-05-12",
        "-1450.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-may-dining", "mine", "2026-05-20", "-650.00", "Middag", "expense", "dining"
    ),
    Transaction(
        "tx-may-unmatched",
        "mine",
        "2026-05-26",
        "-1250.00",
        "Overførsel til opsparing",
        "unknown",
    ),
    Transaction(
        "tx-may-clothes",
        "common",
        "2026-05-15",
        "-450.00",
        "Tøj",
        "expense",
        "clothes",
    ),
    # June: one transaction was unclassified until a later manual decision,
    # and one purchase reached June in a September import.
    Transaction("tx-jun-salary", "mine", "2026-06-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-jun-rent", "mine", "2026-06-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-jun-bills",
        "mine",
        "2026-06-05",
        "-1100.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-jun-parking",
        "mine",
        "2026-06-18",
        "-890.00",
        "Parkering",
        "unknown",
        None,
        None,
        (Stage("2026-09-05", "expense", "transport"),),
    ),
    Transaction(
        "tx-jun-late-groceries",
        "mine",
        "2026-06-20",
        "-540.00",
        "Supermarked",
        "expense",
        "groceries",
        "2026-09-02",
    ),
    Transaction(
        "tx-jun-common-groceries",
        "common",
        "2026-06-12",
        "-780.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    # July: unchanged behaviour from the first round, including both legs of
    # one paired transfer.
    Transaction("tx-jul-salary", "mine", "2026-07-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-jul-rent", "mine", "2026-07-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-jul-groceries-1",
        "mine",
        "2026-07-03",
        "-1200.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-jul-bills",
        "mine",
        "2026-07-04",
        "-1100.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-jul-transport",
        "mine",
        "2026-07-05",
        "-740.00",
        "Periodekort",
        "expense",
        "transport",
    ),
    Transaction(
        "tx-jul-dining", "mine", "2026-07-09", "-650.00", "Middag", "expense", "dining"
    ),
    Transaction(
        "tx-jul-clothes", "mine", "2026-07-10", "-450.00", "Tøj", "expense", "clothes"
    ),
    Transaction(
        "tx-jul-groceries-2",
        "mine",
        "2026-07-12",
        "-1100.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-jul-transfer-out",
        "mine",
        "2026-07-15",
        "-5000.00",
        "Overførsel til Fælleskonto",
        "transfer",
        None,
        None,
        (),
        "tg-2026-07-15",
    ),
    Transaction(
        "tx-jul-transfer-in",
        "common",
        "2026-07-15",
        "5000.00",
        "Overførsel fra Min konto",
        "transfer",
        None,
        None,
        (),
        "tg-2026-07-15",
    ),
    Transaction(
        "tx-jul-groceries-3",
        "mine",
        "2026-07-24",
        "-950.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    # August: a quiet Fælleskonto month and a category that ends negative
    # because the refund is larger than the purchases.
    Transaction("tx-aug-salary", "mine", "2026-08-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-aug-rent", "mine", "2026-08-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-aug-groceries-1",
        "mine",
        "2026-08-03",
        "-1350.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-aug-bills",
        "mine",
        "2026-08-04",
        "-1250.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-aug-transport",
        "mine",
        "2026-08-05",
        "-810.00",
        "Periodekort",
        "expense",
        "transport",
    ),
    Transaction(
        "tx-aug-shelves",
        "mine",
        "2026-08-08",
        "-300.00",
        "Køkkenhylder",
        "expense",
        "home",
    ),
    Transaction(
        "tx-aug-lunch", "mine", "2026-08-10", "-420.00", "Frokost", "expense", "dining"
    ),
    Transaction(
        "tx-aug-washer",
        "mine",
        "2026-08-12",
        "-9200.00",
        "Ny vaskemaskine",
        "expense",
        "home",
    ),
    Transaction(
        "tx-aug-groceries-2",
        "mine",
        "2026-08-13",
        "-1220.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-aug-dining", "mine", "2026-08-20", "-650.00", "Middag", "expense", "dining"
    ),
    Transaction(
        "tx-aug-refund",
        "mine",
        "2026-08-19",
        "800.00",
        "Prisafslag på vaskemaskine",
        "refund",
        "home",
    ),
    Transaction(
        "tx-aug-clothes-refund",
        "mine",
        "2026-08-22",
        "600.00",
        "Returnering af et køb fra juli",
        "refund",
        "clothes",
    ),
    Transaction(
        "tx-aug-unknown-in",
        "mine",
        "2026-08-23",
        "450.00",
        "Ukendt indbetaling",
        "unknown",
    ),
    Transaction(
        "tx-aug-unknown-out",
        "mine",
        "2026-08-24",
        "-450.00",
        "Ukendt udbetaling",
        "unknown",
    ),
    Transaction(
        "tx-aug-groceries-3",
        "mine",
        "2026-08-25",
        "-1030.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    # September: the current, still-accumulating month.
    Transaction("tx-sep-salary", "mine", "2026-09-01", "36000.00", "Løn", "income"),
    Transaction(
        "tx-sep-rent", "mine", "2026-09-02", "-9800.00", "Husleje", "expense", "housing"
    ),
    Transaction(
        "tx-sep-groceries-1",
        "mine",
        "2026-09-03",
        "-890.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-sep-transport",
        "mine",
        "2026-09-04",
        "-460.00",
        "Periodekort",
        "expense",
        "transport",
    ),
    Transaction(
        "tx-sep-bills",
        "mine",
        "2026-09-05",
        "-1100.00",
        "El og internet",
        "expense",
        "bills",
    ),
    Transaction(
        "tx-sep-desk",
        "mine",
        "2026-09-06",
        "-2200.00",
        "Skrivebord og stol",
        "expense",
        "home",
    ),
    Transaction(
        "tx-sep-lunch", "mine", "2026-09-08", "-280.00", "Frokost", "expense", "dining"
    ),
    Transaction(
        "tx-sep-lamp-refund",
        "mine",
        "2026-09-10",
        "300.00",
        "Returneret lampe",
        "refund",
        "home",
    ),
    Transaction(
        "tx-sep-groceries-2",
        "mine",
        "2026-09-11",
        "-680.00",
        "Supermarked",
        "expense",
        "groceries",
    ),
    Transaction(
        "tx-sep-unknown-in",
        "mine",
        "2026-09-12",
        "600.00",
        "Ukendt indbetaling",
        "unknown",
    ),
    Transaction(
        "tx-sep-unknown-out",
        "mine",
        "2026-09-13",
        "-600.00",
        "Ukendt udbetaling",
        "unknown",
    ),
    Transaction(
        "tx-sep-correction-in",
        "mine",
        "2026-09-14",
        "100.00",
        "Rentekorrektion fra banken",
        "adjustment",
    ),
    Transaction(
        "tx-sep-correction-out",
        "mine",
        "2026-09-14",
        "-25.00",
        "Rettelse af kortgebyr",
        "adjustment",
    ),
)

PUBLICATIONS = (
    Publication(
        publication_id="pub-2026-09-15",
        kind="pipeline",
        kind_label="Nutid",
        label="Nutid · offentliggørelse 15. september 2026",
        detail=(
            "Den nuværende offentliggørelse. Alle importerede kontoudtog til og med "
            "15. september 2026 er med, med dagens kategorier og afgørelser."
        ),
        known_at="2026-09-15",
        built_at="2026-09-15T19:40:00Z",
        interpretation_at="2026-09-15",
        first_month="2026-04",
        last_month="2026-09",
        is_current=True,
    ),
    Publication(
        publication_id="pub-2026-08-31-as-was",
        kind="as_was",
        kind_label="Sådan så det ud dengang",
        label="Status 31. august 2026",
        detail=(
            "Offentliggørelsen, som den var 31. august 2026, med datidens "
            "kategorinavne og manuelle afgørelser. Kontoudtog importeret senere er "
            "ikke med."
        ),
        known_at="2026-08-31",
        built_at="2026-08-31T20:15:00Z",
        interpretation_at="2026-08-31",
        first_month="2026-04",
        last_month="2026-08",
        is_current=False,
    ),
    Publication(
        publication_id="pub-2026-08-31-known-at",
        kind="as_known_at",
        kind_label="Dengang kendt, dagens regler",
        label="Kendt 31. august 2026",
        detail=(
            "Kun de kontoudtog, der var importeret 31. august 2026, men med dagens "
            "kategorier og manuelle afgørelser. Viser hvad senere afgørelser ændrer "
            "på de samme data."
        ),
        known_at="2026-08-31",
        built_at="2026-09-15T19:45:00Z",
        interpretation_at="2026-09-15",
        first_month="2026-04",
        last_month="2026-08",
        is_current=False,
    ),
)

ACCOUNT_BY_ID = {account.account_id: account for account in ACCOUNTS}
CATEGORY_BY_ID = {category.category_id: category for category in CATEGORIES}
PUBLICATION_BY_ID = {
    publication.publication_id: publication for publication in PUBLICATIONS
}

BUDGET_PLAN = (
    ("housing", "Bolig", "10000.00"),
    ("home", "Boligudstyr og møbler", "1500.00"),
    ("groceries", "Dagligvarer", "3500.00"),
    ("bills", "Faste regninger", "1200.00"),
    ("transport", "Transport", "800.00"),
    ("dining", "Café og restaurant", "800.00"),
    ("clothes", "Tøj", "500.00"),
)
BUDGET_MONTHS = ("2026-07", "2026-08", "2026-09")
BUDGET_INCOME = "36000.00"
BUDGET_EARMARKED = "3000.00"
VACATION_LABEL = "Ferie"
BUDGET_NOTICE = (
    "Opdigtet budget for begge eksempelkonti. Beløb uden kategori og manglende "
    "kontodata kan ændre sammenligningen. Budgettet gælder hele måneden, også i "
    "september."
)


def category_name(category_id: str | None, interpretation_at: str) -> str | None:
    """Return the category name in force at a moment, or ``None``."""
    if category_id is None:
        return None
    return CATEGORY_BY_ID[category_id].name_at(interpretation_at)


def known_transactions(publication: Publication) -> tuple[Transaction, ...]:
    """Return the transactions the platform knew of at the publication's moment."""
    return tuple(
        transaction
        for transaction in TRANSACTIONS
        if transaction.imported_by(publication.known_at)
    )


def evidence_through(publication: Publication, account_id: str) -> str | None:
    """Return the last date the account's admitted exports cover, or ``None``."""
    covered = [
        export.covers_through
        for export in EXPORTS[account_id]
        if export.imported_on <= publication.known_at
    ]
    return max(covered) if covered else None


def account_coverage(
    publication: Publication, account: Account, month: str
) -> Coverage:
    """Return the coverage status of one account for one month."""
    start, end = month_bounds(month)
    if month < account.managed_from:
        return Coverage(
            NO_DATA,
            f"Ingen oplysninger for {MONTH_NAMES[int(month[5:7]) - 1]}",
            "Ufuldstændige tal",
            (
                f"Kontoudtoget begynder først i {month_label(account.managed_from)}. "
                "Der er ingen oplysninger for denne måned."
            ),
            f"Kontoudtoget begynder i {month_label(account.managed_from)}",
        )
    reached = evidence_through(publication, account.account_id)
    if reached is None or reached < start:
        return Coverage(
            NO_DATA,
            f"Ingen oplysninger for {MONTH_NAMES[int(month[5:7]) - 1]}",
            "Ufuldstændige tal",
            (
                "Oplysninger for denne måned mangler. Hverken bevægelser eller saldo "
                "kan bekræftes."
            ),
            f"Ingen oplysninger for {MONTH_NAMES[int(month[5:7]) - 1]}",
        )
    if reached < end:
        detail = (
            f"Kun oplysninger til og med {date_label(reached)}. "
            "Senere bevægelser er ikke med."
        )
        return Coverage(
            PARTIAL,
            "Kun en del af måneden",
            "Ufuldstændige tal",
            detail,
            f"Oplysninger til og med {date_label(reached)}",
        )
    return Coverage(
        COMPLETE,
        "Alle kontodata er med",
        "Alle kontodata er med",
        "Oplysningerne bekræfter, at hele måneden er med, fra start til slut.",
        "Hele måneden er dækket",
    )


SHORT_LABELS = {
    COMPLETE: "Alle kontodata er med",
    PARTIAL: "Ufuldstændige tal",
    NO_DATA: "Ingen oplysninger",
}


def coverage_label(
    status: str, accounts: Sequence[Account], coverage: dict[str, Coverage]
) -> str:
    """Return the household label that names the accounts behind the status."""
    names = " og ".join(account.name for account in accounts)
    if status == COMPLETE:
        return f"Alle kontodata er med — {names}"
    if status == NO_DATA:
        return f"Ingen oplysninger — {names}"
    states = []
    for account in accounts:
        state = coverage[account.account_id]
        if state.status == COMPLETE:
            continue
        word = "mangler" if state.status == NO_DATA else "er delvis med"
        states.append(f"{account.name} {word}")
    return f"Ufuldstændige tal — {'; '.join(states)}"


def combined_coverage(
    accounts: Sequence[Account], coverage: dict[str, Coverage]
) -> dict[str, object]:
    """Return the household coverage block for the selected accounts."""
    incomplete = [a for a in accounts if coverage[a.account_id].status != COMPLETE]
    if not incomplete:
        status = COMPLETE
    elif all(coverage[account.account_id].status == NO_DATA for account in accounts):
        status = NO_DATA
    else:
        status = PARTIAL
    detail = " ".join(
        f"{account.name}: {coverage[account.account_id].detail}" for account in accounts
    )
    if status == COMPLETE:
        detail += (
            " Posteringer uden kategori er stadig ikke med i indtægter og udgifter."
        )
    return {
        "status": status,
        "label": coverage_label(status, accounts, coverage),
        "shortLabel": SHORT_LABELS[status],
        "detail": detail,
        "incompleteAccounts": [
            {
                "id": account.account_id,
                "name": account.name,
                "status": coverage[account.account_id].status,
                "reason": coverage[account.account_id].reason,
            }
            for account in incomplete
        ],
    }


def provisional_reason(
    publication: Publication, account: Account, month: str
) -> str | None:
    """Return why a closed month still needs the provisional label, if it does."""
    _start, end = month_bounds(month)
    if evidence_through(publication, account.account_id) is None:
        # An account that has never been imported cannot be what the period waits
        # for; its own line already reports that it has no data.
        return None
    admitted = [
        export
        for export in EXPORTS[account.account_id]
        if export.imported_on <= publication.known_at
    ]
    if any(export.finalizes(end) for export in admitted):
        return None
    covering = [export for export in admitted if export.covers(end)]
    if not covering:
        return (
            f"{account.name}: Intet kontoudtog dækker månedens sidste dag "
            f"({date_label(end)})."
        )
    produced = max(export.produced_on for export in covering)
    return (
        f"{account.name}: Kontoudtoget er dateret {date_label(produced)}, mindre end "
        "syv dage efter månedens afslutning."
    )


def provisional_status(
    publication: Publication, month: str, accounts: Sequence[Account]
) -> tuple[bool, list[str]]:
    """Return the provisional label and its reasons for one month."""
    if month == month_of(publication.known_at):
        reason = "Måneden er stadig i gang ved dette kendskabstidspunkt."
        return True, [reason]
    reasons = [
        reason
        for reason in (
            provisional_reason(publication, account, month) for account in accounts
        )
        if reason is not None
    ]
    return bool(reasons), reasons


def period_block(
    month: str, reasons: Sequence[str], *, provisional: bool, current: bool
) -> dict[str, object]:
    """Return the period block of one monthly report."""
    start, end = month_bounds(month)
    if provisional:
        detail = (
            f"{month_label(month).capitalize()} er foreløbig for denne visning. "
            + " ".join(reasons)
        )
        status_label = (
            "Måneden indtil nu — foreløbige tal" if current else "Foreløbige tal"
        )
    else:
        detail = (
            "Måneden er afsluttet. I dette eksempel dækker kontoudtogene hele måneden "
            "og er dateret mere end syv dage efter månedens afslutning."
        )
        status_label = "Måneden er afsluttet"
    return {
        "id": month,
        "label": month_label(month),
        "start": start,
        "end": end,
        "provisional": provisional,
        "detail": detail,
        "statusLabel": status_label,
        "provisionalReasons": list(reasons),
    }


def transaction_json(
    transaction: Transaction, publication: Publication
) -> dict[str, object]:
    """Return the display shape of one transaction."""
    stage = transaction.stage_at(publication.interpretation_at)
    entry: dict[str, object] = {
        "id": transaction.transaction_id,
        "accountId": transaction.account_id,
        "accountName": ACCOUNT_BY_ID[transaction.account_id].name,
        "date": transaction.day,
        "amount": money(amount_of(transaction)),
        "kind": stage.kind,
        "category": category_name(stage.category_id, publication.interpretation_at),
        "description": transaction.description,
        "kindLabel": KIND_LABELS[stage.kind],
    }
    if stage.kind == "transfer":
        entry |= transfer_evidence(transaction, publication)
    return entry


def transfer_evidence(
    transaction: Transaction, publication: Publication
) -> dict[str, object]:
    """Return the display evidence for one transfer leg."""
    if transaction.transfer_group:
        others = [
            other
            for other in known_transactions(publication)
            if other.transfer_group == transaction.transfer_group
            and other.transaction_id != transaction.transaction_id
        ]
        counterpart = ACCOUNT_BY_ID[others[0].account_id].name if others else "ukendt"
        return {
            "transferGroupId": transaction.transfer_group,
            "transferBasis": "paired",
            "counterpartAccountId": others[0].account_id if others else None,
            "counterpartAccountName": counterpart,
            "transferLabel": f"Parret overførsel med {counterpart}",
        }
    counterpart = ACCOUNT_BY_ID[transaction.counterpart or ""].name
    return {
        "transferGroupId": None,
        "transferBasis": "one_sided",
        "counterpartAccountId": transaction.counterpart,
        "counterpartAccountName": counterpart,
        "transferLabel": (
            f"Enkeltsidet overførsel til {counterpart} (afgjort manuelt)"
        ),
    }


def sort_rows(rows: Iterable[Transaction]) -> list[Transaction]:
    """Return rows newest first, money out before money in on one date."""
    return sorted(rows, key=lambda row: (row.day, -amount_of(row)), reverse=True)


@dataclass(frozen=True)
class MonthAmounts:
    """Every amount one monthly report needs, as decimals."""

    income: Decimal
    expenses: Decimal
    net: Decimal
    categories: dict[str, Decimal]
    income_rows: tuple[Transaction, ...]
    spending_rows: tuple[Transaction, ...]
    unclassified: tuple[Transaction, ...]
    adjustments: tuple[Transaction, ...]
    transfers: tuple[Transaction, ...]


def month_amounts(
    publication: Publication, month: str, account_ids: Sequence[str]
) -> MonthAmounts:
    """Derive one month's amounts from the synthetic facts."""
    staged = [
        (row, row.stage_at(publication.interpretation_at))
        for row in known_transactions(publication)
        if month_of(row.day) == month and row.account_id in account_ids
    ]
    income_rows = tuple(row for row, stage in staged if stage.kind == "income")
    spending_rows = tuple(
        row for row, stage in staged if stage.kind in {"expense", "refund"}
    )
    categories: dict[str, Decimal] = {}
    for row in spending_rows:
        stage = row.stage_at(publication.interpretation_at)
        if stage.category_id is None:
            continue
        # Net spending is minus the signed amount: an expense adds, a refund subtracts.
        categories[stage.category_id] = categories.get(
            stage.category_id, Decimal(0)
        ) - Decimal(row.amount)
    income = total([row.amount for row in income_rows])
    expenses = -total([row.amount for row in spending_rows])
    return MonthAmounts(
        income=income,
        expenses=expenses,
        net=income - expenses,
        categories=categories,
        income_rows=income_rows,
        spending_rows=spending_rows,
        unclassified=tuple(row for row, stage in staged if stage.kind == "unknown"),
        adjustments=tuple(row for row, stage in staged if stage.kind == "adjustment"),
        transfers=tuple(row for row, stage in staged if stage.kind == "transfer"),
    )


@dataclass(frozen=True)
class GroupText:
    """The heading and explanation of one reporting group."""

    label: str
    detail: str


def group_block(
    rows: Sequence[Transaction],
    heading: GroupText,
    publication: Publication,
    *,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return one reporting group: unclassified money, adjustments or transfers."""
    money_in = total([row.amount for row in rows if amount_of(row) > 0])
    money_out = total([row.amount for row in rows if amount_of(row) < 0])
    block: dict[str, object] = {
        "moneyIn": money(money_in),
        "moneyOut": money(money_out),
        "count": len(rows),
        "label": heading.label,
        "detail": heading.detail,
        "transactions": [transaction_json(row, publication) for row in sort_rows(rows)],
    }
    if extra:
        block |= extra
    return block


def empty_group(heading: GroupText) -> dict[str, object]:
    """Return one reporting group with no known amounts at all."""
    return {
        "moneyIn": None,
        "moneyOut": None,
        "count": 0,
        "label": heading.label,
        "detail": heading.detail,
        "transactions": [],
    }


def category_blocks(
    amounts: MonthAmounts,
    publication: Publication,
    coverage: dict[str, object],
) -> list[dict[str, object]]:
    """Return the category list of one monthly report."""
    blocks: list[dict[str, object]] = []
    for category_id, net in amounts.categories.items():
        entries = [
            row
            for row in amounts.spending_rows
            if row.stage_at(publication.interpretation_at).category_id == category_id
        ]
        purchases = -total(
            [
                row.amount
                for row in entries
                if row.stage_at(publication.interpretation_at).kind == "expense"
            ]
        )
        refunds = total(
            [
                row.amount
                for row in entries
                if row.stage_at(publication.interpretation_at).kind == "refund"
            ]
        )
        blocks.append(
            {
                "id": category_id,
                "name": category_name(category_id, publication.interpretation_at),
                "purchases": money(purchases),
                "refunds": money(refunds),
                "netSpending": money(net),
                "netRefund": net < 0,
                "coverage": coverage,
                "transactions": [
                    transaction_json(row, publication) for row in sort_rows(entries)
                ],
            }
        )
    biggest = max(amounts.categories.values(), default=Decimal(0))
    for block in blocks:
        net = amounts.categories[str(block["id"])]
        block["barPercent"] = (
            float(max(net, Decimal(0)) / biggest * 100) if biggest > 0 else 0.0
        )
    blocks.sort(key=lambda block: amounts.categories[str(block["id"])], reverse=True)
    return blocks


def transfer_group_block(
    rows: Sequence[Transaction], publication: Publication
) -> dict[str, object]:
    """Return the transfer group with paired and one-sided counts."""
    one_sided = [row for row in rows if not row.transfer_group]
    paired = len(rows) - len(one_sided)
    if not rows:
        label = "Ingen bekræftede overførsler mellem de to konti i dette eksempel."
    elif len(rows) == 1:
        label = "1 postering for overførsel mellem vores konti."
    else:
        label = f"{len(rows)} posteringer for overførsler mellem vores konti."
    if one_sided:
        label += f" Heraf {len(one_sided)} enkeltsidet."
    detail = (
        "Begge sider af en overførsel vises. Ingen af dem tæller som indtægt eller "
        "udgift."
    )
    if one_sided:
        detail += (
            " En enkeltsidet overførsel er afgjort manuelt, fordi det andet ben ligger "
            "uden for den anden kontos kontoudtog."
        )
    return group_block(
        rows,
        GroupText(label, detail),
        publication,
        extra={"pairedCount": paired, "oneSidedCount": len(one_sided)},
    )


def account_balance_chain(
    publication: Publication,
    account: Account,
    known: Sequence[Transaction],
) -> dict[str, dict[str, str | None]]:
    """Return one account's opening and closing balance per reporting month."""
    months = months_between(publication.first_month, publication.last_month)
    result: dict[str, dict[str, str | None]] = {}
    carried: str | None = None
    for month in months:
        rows = [
            row
            for row in known
            if row.account_id == account.account_id and month_of(row.day) == month
        ]
        if account_coverage(publication, account, month).status == NO_DATA:
            result[month] = {"opening": None, "closing": None, "as_of": None}
            continue
        opening = carried if carried is not None else account.opening_balance
        closing = money(Decimal(opening) + total([row.amount for row in rows]))
        result[month] = {
            "opening": money(opening),
            "closing": closing,
            "as_of": max((row.day for row in rows), default=account.balance_carried_on),
        }
        carried = closing
    return result


def account_balances(publication: Publication) -> dict[str, dict[str, str | None]]:
    """Return every account's opening and closing balance per reporting month."""
    known = known_transactions(publication)
    return {
        f"{account.account_id}:{month}": balance
        for account in ACCOUNTS
        for month, balance in account_balance_chain(publication, account, known).items()
    }


@dataclass(frozen=True)
class ReportContext:
    """Everything one monthly report needs before its amounts are grouped."""

    publication: Publication
    month: str
    accounts: tuple[Account, ...]
    period: dict[str, object]
    coverage: dict[str, object]
    account_coverages: dict[str, Coverage]
    balances: dict[str, dict[str, str | None]]


def account_blocks(
    context: ReportContext, rows: Sequence[Transaction]
) -> list[dict[str, object]]:
    """Return the per-account blocks of one monthly report."""
    blocks: list[dict[str, object]] = []
    for account in context.accounts:
        publication = context.publication
        own = [row for row in rows if row.account_id == account.account_id]
        balance = context.balances[f"{account.account_id}:{context.month}"]
        coverage = context.account_coverages[account.account_id]
        blocks.append(
            {
                "id": account.account_id,
                "name": account.name,
                "ownerLabel": account.owner_label,
                "accountType": account.account_type,
                "ownershipScope": account.ownership_scope,
                "coverage": coverage.to_json(),
                "evidenceThrough": evidence_through(publication, account.account_id),
                "balance": {"amount": balance["closing"], "asOf": balance["as_of"]},
                "quietConfirmed": not own and coverage.status == COMPLETE,
                "openingBalance": balance["opening"],
                "activityNote": (
                    "Kun posteringerne i dette faste eksempel vises. Der kan mangle "
                    "bevægelser."
                ),
                "transactions": [
                    transaction_json(row, publication) for row in sort_rows(own)
                ],
            }
        )
    return blocks


def empty_report(context: ReportContext) -> dict[str, object]:
    """Return a report whose selected accounts have no evidence at all."""
    empty = "Ingen oplysninger for den valgte konto i denne måned."
    return {
        "publicationId": context.publication.publication_id,
        "publicationKind": context.publication.kind,
        "currency": CURRENCY,
        "accountIds": sorted(account.account_id for account in context.accounts),
        "period": context.period,
        "coverage": context.coverage,
        "measureNote": "Ingen oplysninger",
        "reconciliation": {
            "income": None,
            "expenses": None,
            "netCashFlow": None,
            "categoryTotal": None,
            "entryCounts": {
                "income": 0,
                "categories": 0,
                "unclassified": 0,
                "adjustments": 0,
                "transfers": 0,
            },
            "entryCount": 0,
            "excluded": EXCLUDED_FROM_MEASURES,
        },
        "measures": {
            "income": None,
            "expenses": None,
            "netCashFlow": None,
            "savings": None,
            "savingsRate": None,
            "coverage": context.coverage,
        },
        "incomeTransactions": [],
        "categories": [],
        "unclassified": empty_group(GroupText(empty, UNCLASSIFIED_DETAIL))
        | {"operatorRoute": OPERATOR_ROUTE},
        "adjustments": empty_group(GroupText(empty, ADJUSTMENT_DETAIL)),
        "transfers": empty_group(
            GroupText(empty, "Ingen overførsler kan bekræftes uden oplysninger.")
        ),
        "accounts": account_blocks(context, []),
    }


def build_report(
    publication: Publication, month: str, account_ids: Sequence[str]
) -> dict[str, object]:
    """Build one monthly report for one account selection."""
    accounts = tuple(
        account for account in ACCOUNTS if account.account_id in account_ids
    )
    account_coverages = {
        account.account_id: account_coverage(publication, account, month)
        for account in accounts
    }
    coverage = combined_coverage(accounts, account_coverages)
    provisional, reasons = provisional_status(publication, month, accounts)
    context = ReportContext(
        publication=publication,
        month=month,
        accounts=accounts,
        period=period_block(
            month,
            reasons,
            provisional=provisional,
            current=month == month_of(publication.known_at),
        ),
        coverage=coverage,
        account_coverages=account_coverages,
        balances=account_balances(publication),
    )
    if coverage["status"] == NO_DATA:
        return empty_report(context)
    amounts = month_amounts(publication, month, account_ids)
    rate = (
        (amounts.net / amounts.income * 100).quantize(CENT)
        if amounts.income > 0
        else None
    )
    rows = [
        row
        for row in known_transactions(publication)
        if month_of(row.day) == month and row.account_id in account_ids
    ]
    return {
        "publicationId": publication.publication_id,
        "publicationKind": publication.kind,
        "currency": CURRENCY,
        "accountIds": sorted(account.account_id for account in accounts),
        "period": context.period,
        "coverage": coverage,
        "measureNote": (
            "Posteringer med kategori"
            if coverage["status"] == COMPLETE
            else coverage["shortLabel"]
        ),
        "reconciliation": {
            "income": money(amounts.income),
            "expenses": money(amounts.expenses),
            "netCashFlow": money(amounts.net),
            "categoryTotal": money(sum(amounts.categories.values(), Decimal(0))),
            "entryCounts": {
                "income": len(amounts.income_rows),
                "categories": len(amounts.spending_rows),
                "unclassified": len(amounts.unclassified),
                "adjustments": len(amounts.adjustments),
                "transfers": len(amounts.transfers),
            },
            "entryCount": len(amounts.income_rows)
            + len(amounts.spending_rows)
            + len(amounts.unclassified)
            + len(amounts.adjustments)
            + len(amounts.transfers),
            "excluded": EXCLUDED_FROM_MEASURES,
        },
        "measures": {
            "income": money(amounts.income),
            "expenses": money(amounts.expenses),
            "netCashFlow": money(amounts.net),
            "savings": money(amounts.net),
            "savingsRate": None if rate is None else f"{rate:.2f}",
            "coverage": coverage,
        },
        "incomeTransactions": [
            transaction_json(row, publication) for row in sort_rows(amounts.income_rows)
        ],
        "categories": category_blocks(amounts, publication, coverage),
        "unclassified": group_block(
            amounts.unclassified,
            GroupText(
                count_label(
                    len(amounts.unclassified),
                    "postering uden kategori",
                    "posteringer uden kategori",
                    "Ingen posteringer uden kategori",
                ),
                UNCLASSIFIED_DETAIL,
            ),
            publication,
            extra={"operatorRoute": OPERATOR_ROUTE},
        ),
        "adjustments": group_block(
            amounts.adjustments,
            GroupText(
                count_label(
                    len(amounts.adjustments),
                    "postering uden kategori",
                    "posteringer uden kategori",
                    "Ingen rettelser",
                ),
                ADJUSTMENT_DETAIL,
            ),
            publication,
        ),
        "transfers": transfer_group_block(amounts.transfers, publication),
        "accounts": account_blocks(context, rows),
    }


def count_label(count: int, singular: str, plural: str, empty: str) -> str:
    """Return a short Danish count label."""
    if count == 0:
        return empty
    return f"{count} {singular if count == 1 else plural}"


def build_view(
    publication: Publication, account_ids: Sequence[str]
) -> dict[str, object]:
    """Build every monthly report of one account selection, newest first."""
    months = months_between(publication.first_month, publication.last_month)
    return {
        "accountIds": sorted(account_ids),
        "reports": [
            build_report(publication, month, account_ids) for month in reversed(months)
        ],
    }


def build_budget(publication: Publication) -> dict[str, object]:
    """Build the synthetic budget comparison for the current publication."""
    account_ids = sorted(account.account_id for account in ACCOUNTS)
    previous_carried = Decimal(0)
    reports: list[dict[str, object]] = []
    planned_spending = total([allocated for _id, _name, allocated in BUDGET_PLAN])
    planned_income = Decimal(BUDGET_INCOME)
    planned_savings = planned_income - planned_spending - Decimal(BUDGET_EARMARKED)
    for month in BUDGET_MONTHS:
        amounts = month_amounts(publication, month, account_ids)
        rows: list[dict[str, object]] = []
        for category_id, name, allocated in BUDGET_PLAN:
            actual = amounts.categories.get(category_id, Decimal(0))
            available = Decimal(allocated)
            remaining = available - actual
            rows.append(
                {
                    "id": category_id,
                    "categoryId": (
                        category_id if category_id in amounts.categories else None
                    ),
                    "name": name,
                    "carryForward": False,
                    "allocated": money(allocated),
                    "opening": "0.00",
                    "available": money(available),
                    "actual": money(actual),
                    "remaining": money(remaining),
                    "carriedForward": "0.00",
                    "savingsImpact": money(remaining),
                }
            )
        vacation_available = previous_carried + Decimal(BUDGET_EARMARKED)
        rows.append(
            {
                "id": "vacation",
                "categoryId": None,
                "name": VACATION_LABEL,
                "carryForward": True,
                "allocated": money(BUDGET_EARMARKED),
                "opening": money(previous_carried),
                "available": money(vacation_available),
                "actual": "0.00",
                "remaining": money(vacation_available),
                "carriedForward": money(vacation_available),
                "savingsImpact": "0.00",
            }
        )
        previous_carried = vacation_available
        actual_savings = amounts.net - Decimal(BUDGET_EARMARKED)
        reports.append(
            {
                "month": month,
                "plannedIncome": money(planned_income),
                "plannedSpending": money(planned_spending),
                "earmarked": money(BUDGET_EARMARKED),
                "plannedSavings": money(planned_savings),
                "actualSavings": money(actual_savings),
                "savingsDifference": money(actual_savings - planned_savings),
                "incomeDifference": "0.00",
                "rows": rows,
            }
        )
    return {
        "accountIds": account_ids,
        "notice": BUDGET_NOTICE,
        "reports": reports,
    }


def build_publication(publication: Publication) -> dict[str, object]:
    """Build one publication with every account selection."""
    months = months_between(publication.first_month, publication.last_month)
    account_ids = [account.account_id for account in ACCOUNTS]
    views = [
        build_view(publication, list(scope))
        for size in range(1, len(account_ids) + 1)
        for scope in combinations(account_ids, size)
    ]
    block: dict[str, object] = {
        "publicationId": publication.publication_id,
        "kind": publication.kind,
        "kindLabel": publication.kind_label,
        "label": publication.label,
        "detail": publication.detail,
        "knownAt": publication.known_at,
        "builtAt": publication.built_at,
        "isCurrent": publication.is_current,
        "months": list(reversed(months)),
        "defaultMonth": months[-1],
        "views": views,
        "budgetExample": build_budget(publication) if publication.is_current else None,
    }
    return block


def main() -> None:
    """Write the synthetic fixture and report what it contains."""
    current = next(pub for pub in PUBLICATIONS if pub.is_current)
    fixture = {
        "schemaVersion": "prototype-11/v2",
        "kind": "synthetic",
        "label": "Opdigtet eksempel — fiktive beløb og konti",
        "notice": (
            "Alle oplysninger er opdigtede. Markeringerne af manglende kontodata er "
            "fastlagt til denne afprøvning."
        ),
        "syntheticNow": "15. september 2026",
        "asOf": current.known_at,
        "currency": CURRENCY,
        "currentPublicationId": current.publication_id,
        "availableAccounts": [
            {
                "id": account.account_id,
                "name": account.name,
                "ownerLabel": account.owner_label,
                "managedFrom": account.managed_from,
                "accountType": account.account_type,
                "ownershipScope": account.ownership_scope,
            }
            for account in ACCOUNTS
        ],
        "publications": [build_publication(pub) for pub in PUBLICATIONS],
    }
    OUTPUT.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.write(
        f"Wrote {OUTPUT.name}: {len(PUBLICATIONS)} publications, "
        f"{len(TRANSACTIONS)} synthetic transactions.\n"
    )


if __name__ == "__main__":
    main()
