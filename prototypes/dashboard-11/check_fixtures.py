"""Audit the synthetic fixture of the #11 dashboard prototype.

Reads only ``example.json``: it never opens ``imports/``, a bank export or a
private report. Every expected figure below is a hand-checked constant, so the
audit fails when the fixture's arithmetic or its trust labels drift.

    py -3.12 prototypes/dashboard-11/check_fixtures.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import NoReturn

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "example.json"
CENT = Decimal("0.01")
NO_DATA = "no_data"
COMPLETE = "complete"
PARTIAL = "partial"

# Hand-checked income, expenses and net cash flow for the household view.
MEASURES = {
    "pipeline": {
        "2026-04": ("36000.00", "13940.00", "22060.00"),
        "2026-05": ("36000.00", "13450.00", "22550.00"),
        "2026-06": ("36000.00", "13110.00", "22890.00"),
        "2026-07": ("36000.00", "15990.00", "20010.00"),
        "2026-08": ("36000.00", "24630.00", "11370.00"),
        "2026-09": ("36000.00", "15110.00", "20890.00"),
    },
    "as_was": {
        "2026-04": ("36000.00", "13940.00", "22060.00"),
        "2026-05": ("36000.00", "13450.00", "22550.00"),
        "2026-06": ("36000.00", "11680.00", "24320.00"),
        "2026-07": ("36000.00", "15990.00", "20010.00"),
        "2026-08": ("36000.00", "24630.00", "11370.00"),
    },
    "as_known_at": {
        "2026-04": ("36000.00", "13940.00", "22060.00"),
        "2026-05": ("36000.00", "13450.00", "22550.00"),
        "2026-06": ("36000.00", "12570.00", "23430.00"),
        "2026-07": ("36000.00", "15990.00", "20010.00"),
        "2026-08": ("36000.00", "24630.00", "11370.00"),
    },
}

# Hand-checked coverage status per account, in declaration order.
COVERAGE_STATUS = {
    "pipeline": {
        "2026-04": ("complete", "no_data"),
        "2026-05": ("complete", "complete"),
        "2026-06": ("complete", "complete"),
        "2026-07": ("complete", "complete"),
        "2026-08": ("complete", "complete"),
        "2026-09": ("partial", "no_data"),
    },
    "as_was": {
        "2026-04": ("complete", "no_data"),
        "2026-05": ("complete", "complete"),
        "2026-06": ("complete", "complete"),
        "2026-07": ("complete", "complete"),
        "2026-08": ("partial", "no_data"),
    },
    "as_known_at": {
        "2026-04": ("complete", "no_data"),
        "2026-05": ("complete", "complete"),
        "2026-06": ("complete", "complete"),
        "2026-07": ("complete", "complete"),
        "2026-08": ("partial", "no_data"),
    },
}

# Hand-checked opening and closing balances per account and month.
PIPELINE_BALANCES: dict[str, dict[str, tuple[str | None, str | None]]] = {
    "mine": {
        "2026-04": ("20000.00", "40060.00"),
        "2026-05": ("40060.00", "61810.00"),
        "2026-06": ("61810.00", "85480.00"),
        "2026-07": ("85480.00", "100490.00"),
        "2026-08": ("100490.00", "111860.00"),
        "2026-09": ("111860.00", "132825.00"),
    },
    "common": {
        "2026-04": (None, None),
        "2026-05": ("18000.00", "17550.00"),
        "2026-06": ("17550.00", "16770.00"),
        "2026-07": ("16770.00", "21770.00"),
        "2026-08": ("21770.00", "21770.00"),
        "2026-09": (None, None),
    },
}
PAST_BALANCES: dict[str, dict[str, tuple[str | None, str | None]]] = {
    "mine": {
        "2026-04": ("20000.00", "40060.00"),
        "2026-05": ("40060.00", "61810.00"),
        "2026-06": ("61810.00", "86020.00"),
        "2026-07": ("86020.00", "101030.00"),
        "2026-08": ("101030.00", "112400.00"),
    },
    "common": {
        "2026-04": (None, None),
        "2026-05": ("18000.00", "17550.00"),
        "2026-06": ("17550.00", "16770.00"),
        "2026-07": ("16770.00", "21770.00"),
        "2026-08": (None, None),
    },
}

# Hand-checked unclassified money, adjustments and transfers for the household view.
UNCLASSIFIED = {
    "pipeline": {
        "2026-04": (0, "0.00", "0.00"),
        "2026-05": (1, "0.00", "-1250.00"),
        "2026-06": (0, "0.00", "0.00"),
        "2026-07": (0, "0.00", "0.00"),
        "2026-08": (2, "450.00", "-450.00"),
        "2026-09": (2, "600.00", "-600.00"),
    },
    "as_was": {
        "2026-04": (0, "0.00", "0.00"),
        "2026-05": (1, "0.00", "-1250.00"),
        "2026-06": (1, "0.00", "-890.00"),
        "2026-07": (0, "0.00", "0.00"),
        "2026-08": (2, "450.00", "-450.00"),
    },
    "as_known_at": {
        "2026-04": (0, "0.00", "0.00"),
        "2026-05": (1, "0.00", "-1250.00"),
        "2026-06": (0, "0.00", "0.00"),
        "2026-07": (0, "0.00", "0.00"),
        "2026-08": (2, "450.00", "-450.00"),
    },
}
ADJUSTMENTS = {
    "pipeline": {"2026-09": (2, "100.00", "-25.00")},
    "as_was": {},
    "as_known_at": {},
}
TRANSFERS = {
    "pipeline": {
        "2026-04": (1, 0, 1, "0.00", "-2000.00"),
        "2026-07": (2, 2, 0, "5000.00", "-5000.00"),
    },
    "as_was": {
        "2026-04": (1, 0, 1, "0.00", "-2000.00"),
        "2026-07": (2, 2, 0, "5000.00", "-5000.00"),
    },
    "as_known_at": {
        "2026-04": (1, 0, 1, "0.00", "-2000.00"),
        "2026-07": (2, 2, 0, "5000.00", "-5000.00"),
    },
}


# Hand-checked admitted exports: the range each one covers, when the bank made
# it, and when the household imported it.
@dataclass(frozen=True)
class AdmittedExport:
    """One admitted export as the household recorded it."""

    covers_from: str
    covers_through: str
    produced_on: str
    imported_on: str

    def covers(self, day: str) -> bool:
        """Return whether the export's declared range contains the date."""
        return self.covers_from <= day <= self.covers_through

    def finalizes(self, period_end: str) -> bool:
        """Return whether this export closes a period end under the seven-day rule."""
        needed = (
            date.fromisoformat(period_end) + timedelta(days=LATE_BOOKING_DAYS)
        ).isoformat()
        return self.covers(period_end) and self.produced_on >= needed


EXPORTS = {
    "mine": (
        AdmittedExport("2026-04-01", "2026-05-31", "2026-06-10", "2026-06-10"),
        AdmittedExport("2026-06-01", "2026-06-30", "2026-07-12", "2026-07-12"),
        AdmittedExport("2026-07-01", "2026-07-31", "2026-08-12", "2026-08-12"),
        AdmittedExport("2026-08-01", "2026-08-25", "2026-08-25", "2026-08-25"),
        AdmittedExport("2026-09-01", "2026-09-14", "2026-09-14", "2026-09-14"),
    ),
    "common": (
        AdmittedExport("2026-05-01", "2026-06-30", "2026-07-12", "2026-07-12"),
        AdmittedExport("2026-07-01", "2026-07-31", "2026-08-12", "2026-08-12"),
        AdmittedExport("2026-08-01", "2026-08-31", "2026-09-05", "2026-09-05"),
    ),
}
LATE_BOOKING_DAYS = 7
CURRENCY = "DKK"
ACCOUNT_TYPES = ("current", "savings")
OWNERSHIP_SCOPES = ("household", "person")

# Hand-checked provisional months and months with a negative category.
PROVISIONAL = {
    "pipeline": ("2026-04", "2026-08", "2026-09"),
    "as_was": ("2026-04", "2026-08"),
    "as_known_at": ("2026-04", "2026-08"),
}
NEGATIVE_MONTHS = {
    "pipeline": ("2026-08",),
    "as_was": ("2026-08",),
    "as_known_at": ("2026-08",),
}
BUDGET_EXPECTED = {
    "2026-07": ("3000.00", "17010.00", "2310.00"),
    "2026-08": ("6000.00", "8370.00", "-6330.00"),
    "2026-09": ("9000.00", "17890.00", "3190.00"),
}
BUDGET_PLANNED_SPENDING = "18300.00"
BUDGET_PLANNED_SAVINGS = "14700.00"
RATE_QUANTUM = Decimal("0.01")

# Hand-checked category trend for the household view: net spending per month,
# purchases minus refunds. A category a month has no rows for is a confirmed
# zero only when every account is complete that month; otherwise it is unknown.
TREND_NET = {
    "2026-04": {
        "bills": "1100.00",
        "groceries": "2300.00",
        "housing": "9800.00",
        "transport": "740.00",
    },
    "2026-05": {
        "bills": "1100.00",
        "clothes": "450.00",
        "dining": "650.00",
        "groceries": "1450.00",
        "housing": "9800.00",
    },
    "2026-06": {
        "bills": "1100.00",
        "groceries": "1320.00",
        "housing": "9800.00",
        "transport": "890.00",
    },
    "2026-07": {
        "bills": "1100.00",
        "clothes": "450.00",
        "dining": "650.00",
        "groceries": "3250.00",
        "housing": "9800.00",
        "transport": "740.00",
    },
    "2026-08": {
        "bills": "1250.00",
        "clothes": "-600.00",
        "dining": "1070.00",
        "groceries": "3600.00",
        "home": "8700.00",
        "housing": "9800.00",
        "transport": "810.00",
    },
    "2026-09": {
        "bills": "1100.00",
        "dining": "280.00",
        "groceries": "1570.00",
        "home": "1900.00",
        "housing": "9800.00",
        "transport": "460.00",
    },
}
TREND_CATEGORIES = (
    "bills",
    "clothes",
    "dining",
    "groceries",
    "home",
    "housing",
    "transport",
)
TREND_ABSENT = {
    "2026-04": "unknown",
    "2026-05": "zero",
    "2026-06": "zero",
    "2026-07": "zero",
    "2026-08": "zero",
    "2026-09": "unknown",
}

# Hand-checked monthly expense plans the trend chart may show, and the explicit
# months the budget covers. The earmarked vacation is not one of them.
TREND_BUDGET = {
    "housing": "10000.00",
    "home": "1500.00",
    "groceries": "3500.00",
    "bills": "1200.00",
    "transport": "800.00",
    "dining": "800.00",
    "clothes": "500.00",
}
TREND_BUDGET_MONTHS = ("2026-07", "2026-08", "2026-09")
TREND_BUDGET_SCOPE = ("common", "mine")


class FixtureError(Exception):
    """The fixture does not have the shape this audit expects."""


def fail(location: str, problem: str) -> NoReturn:
    """Stop the audit because the fixture has the wrong shape."""
    message = f"{location}: {problem}" if location else problem
    raise FixtureError(message)


class Audit:
    """Collect expectations and count the checks performed."""

    def __init__(self) -> None:
        """Start an audit with no failures and no checks."""
        self.failures: list[str] = []
        self.checks = 0

    def expect(self, *, condition: bool, message: str) -> None:
        """Record one expectation about the fixture."""
        self.checks += 1
        if not condition:
            self.failures.append(message)

    def equal(self, actual: object, expected: object, message: str) -> None:
        """Record one equality expectation."""
        self.expect(
            condition=actual == expected,
            message=f"{message}: expected {expected!r}, got {actual!r}",
        )


def obj(node: object, label: str) -> dict[str, object]:
    """Return a JSON object."""
    if not isinstance(node, dict):
        fail(label, "is not a JSON object")
    return cast("dict[str, object]", node)


def arr(node: object, label: str) -> list[object]:
    """Return a JSON array."""
    if not isinstance(node, list):
        fail(label, "is not a JSON array")
    return cast("list[object]", node)


def field(node: object, key: str) -> object:
    """Return one JSON field."""
    mapping = obj(node, f"the node that should hold {key!r}")
    if key not in mapping:
        fail("the fixture", f"is missing the field {key!r}")
    return mapping[key]


def text(node: object, key: str) -> str:
    """Return one text field."""
    value = field(node, key)
    if not isinstance(value, str):
        fail("the fixture", f"field {key!r} is not text")
    return value


def entries(node: object, key: str) -> list[object]:
    """Return one array field."""
    return arr(field(node, key), f"{key!r}")


def amount(node: object, key: str = "amount") -> Decimal:
    """Return one decimal amount field."""
    value = field(node, key)
    if not isinstance(value, str):
        fail("the fixture", f"field {key!r} is not a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation:
        fail("the fixture", f"field {key!r} is not a decimal: {value!r}")


def total(items: Sequence[object]) -> Decimal:
    """Sum the amounts of display transactions."""
    return sum((amount(item) for item in items), Decimal(0))


def identifiers(items: Sequence[object]) -> list[str]:
    """Return the identifiers of display transactions."""
    return [text(item, "id") for item in items]


def kind_of(item: object) -> str:
    """Return the household type of one display transaction."""
    return text(item, "kind")


def scope_of(view: object) -> list[str]:
    """Return the sorted account identifiers of one view."""
    return sorted(str(value) for value in entries(view, "accountIds"))


def month_end(month: str) -> str:
    """Return the last day of a reporting month."""
    year = int(month[:4])
    number = int(month[5:7])
    first_of_next = date(year + number // 12, number % 12 + 1, 1)
    return (first_of_next - timedelta(days=1)).isoformat()


def admitted_exports(account_id: str, known_at: str) -> list[AdmittedExport]:
    """Return the exports of one account that were imported by a moment."""
    return [export for export in EXPORTS[account_id] if export.imported_on <= known_at]


def rule_evidence_through(account_id: str, known_at: str) -> str | None:
    """Return the last day an account's admitted exports cover."""
    covered = [
        export.covers_through for export in admitted_exports(account_id, known_at)
    ]
    return max(covered) if covered else None


def rule_provisional(month: str, known_at: str, account_ids: Sequence[str]) -> bool:
    """Return the contract's provisional verdict for one month and selection."""
    if month == known_at[:7]:
        return True
    end = month_end(month)
    for account_id in account_ids:
        if rule_evidence_through(account_id, known_at) is None:
            # Never imported: no export of it is outstanding.
            continue
        if any(
            export.finalizes(end) for export in admitted_exports(account_id, known_at)
        ):
            continue
        return True
    return False


def audit_export_rule(audit: Audit) -> None:
    """Audit the export rules against the cases the older rule got wrong."""
    late = AdmittedExport("2026-05-01", "2026-06-30", "2026-07-12", "2026-07-12")
    audit.expect(
        condition=not late.finalizes("2026-04-30"),
        message=(
            "an export that begins after the period's last day must not finalize it"
        ),
    )
    early = AdmittedExport("2026-08-01", "2026-08-31", "2026-09-05", "2026-09-05")
    audit.expect(
        condition=not early.finalizes("2026-08-31"),
        message=(
            "an export produced less than seven days after the period end must not "
            "finalize it"
        ),
    )
    good = AdmittedExport("2026-04-01", "2026-05-31", "2026-06-10", "2026-06-10")
    audit.expect(
        condition=good.finalizes("2026-04-30"),
        message=(
            "an export covering the last day, produced seven days later, must "
            "finalize it"
        ),
    )


def audit_report(
    audit: Audit, publication: object, report: object, expected_scope: Sequence[str]
) -> None:
    """Audit one monthly report for one account selection."""
    month = text(field(report, "period"), "id")
    where = f"{text(publication, 'publicationId')} {month} {'+'.join(expected_scope)}"
    audit.equal(
        text(report, "publicationId"),
        text(publication, "publicationId"),
        f"{where}: publication identity",
    )
    audit.equal(
        text(report, "publicationKind"),
        text(publication, "kind"),
        f"{where}: publication kind",
    )
    audit.equal(
        entries(report, "accountIds"),
        list(expected_scope),
        f"{where}: account selection",
    )
    audit.equal(text(report, "currency"), CURRENCY, f"{where}: currency")
    coverage = text(field(report, "coverage"), "status")
    own = [
        item
        for account in entries(report, "accounts")
        for item in entries(account, "transactions")
    ]
    if coverage == NO_DATA:
        audit_empty_report(audit, report, own, where)
        return
    measures = field(report, "measures")
    income = total([item for item in own if kind_of(item) == "income"])
    spending = [item for item in own if kind_of(item) in {"expense", "refund"}]
    expenses = -total(spending)
    audit.equal(amount(measures, "income"), income, f"{where}: income")
    audit.equal(amount(measures, "expenses"), expenses, f"{where}: expenses")
    audit.equal(
        amount(measures, "netCashFlow"), income - expenses, f"{where}: net cash flow"
    )
    audit.equal(amount(measures, "savings"), income - expenses, f"{where}: savings")
    rate = field(measures, "savingsRate")
    expected_rate = (
        ((income - expenses) / income * 100).quantize(RATE_QUANTUM)
        if income > 0
        else None
    )
    audit.equal(
        None if rate is None else Decimal(str(rate)),
        expected_rate,
        f"{where}: savings rate",
    )
    audit_grouping(audit, report, own, expenses, where)
    audit_reconciliation(audit, report, expenses, where)


def audit_empty_report(
    audit: Audit, report: object, own: Sequence[object], where: str
) -> None:
    """Audit a report whose selected accounts have no evidence at all."""
    measures = field(report, "measures")
    audit.expect(
        condition=all(
            field(measures, key) is None
            for key in ("income", "expenses", "netCashFlow", "savings")
        ),
        message=f"{where}: a no-data month must not report amounts",
    )
    audit.expect(
        condition=not own, message=f"{where}: a no-data month must show no entries"
    )
    for key in ("unclassified", "adjustments", "transfers"):
        group = field(report, key)
        audit.expect(
            condition=field(group, "moneyIn") is None
            and field(group, "moneyOut") is None,
            message=f"{where}: a no-data month must not show {key} amounts",
        )
    for account in entries(report, "accounts"):
        audit.expect(
            condition=field(field(account, "balance"), "amount") is None,
            message=f"{where}: a no-data account must have an unknown balance",
        )
    reconciliation = field(report, "reconciliation")
    audit.expect(
        condition=all(
            field(reconciliation, key) is None
            for key in ("income", "expenses", "netCashFlow", "categoryTotal")
        ),
        message=f"{where}: a no-data month must not reconcile amounts",
    )


def audit_reconciliation(
    audit: Audit, report: object, expenses: Decimal, where: str
) -> None:
    """Audit the precomputed reconciliation the checks screen displays."""
    measures = field(report, "measures")
    reconciliation = field(report, "reconciliation")
    for key in ("income", "expenses", "netCashFlow"):
        audit.equal(
            amount(reconciliation, key),
            amount(measures, key),
            f"{where}: reconciliation {key}",
        )
    audit.equal(
        amount(reconciliation, "categoryTotal"),
        expenses,
        f"{where}: reconciliation category total",
    )
    counts = field(reconciliation, "entryCounts")
    expected = {
        "income": len(entries(report, "incomeTransactions")),
        "categories": sum(
            len(entries(category, "transactions"))
            for category in entries(report, "categories")
        ),
        "unclassified": field(field(report, "unclassified"), "count"),
        "adjustments": field(field(report, "adjustments"), "count"),
        "transfers": field(field(report, "transfers"), "count"),
    }
    for key, value in expected.items():
        audit.equal(field(counts, key), value, f"{where}: reconciliation count {key}")
    audit.equal(
        field(reconciliation, "entryCount"),
        sum(count for count in expected.values() if isinstance(count, int)),
        f"{where}: reconciliation entry count",
    )


def audit_grouping(
    audit: Audit, report: object, own: Sequence[object], expenses: Decimal, where: str
) -> None:
    """Audit that every entry belongs to one group and the categories add up."""
    counted = (
        identifiers(entries(report, "incomeTransactions"))
        + [
            identifier
            for category in entries(report, "categories")
            for identifier in identifiers(entries(category, "transactions"))
        ]
        + identifiers(entries(field(report, "unclassified"), "transactions"))
        + identifiers(entries(field(report, "adjustments"), "transactions"))
        + identifiers(entries(field(report, "transfers"), "transactions"))
    )
    audit.equal(
        sorted(counted),
        sorted(identifiers(own)),
        f"{where}: every entry belongs to exactly one reporting group",
    )
    audit.equal(len(counted), len(set(counted)), f"{where}: no entry is counted twice")
    audit.equal(
        sum(
            (
                amount(category, "netSpending")
                for category in entries(report, "categories")
            ),
            Decimal(0),
        ),
        expenses,
        f"{where}: categories add up to expenses",
    )
    for category in entries(report, "categories"):
        category_rows = entries(category, "transactions")
        purchases = -total(
            [item for item in category_rows if kind_of(item) == "expense"]
        )
        refunds = total([item for item in category_rows if kind_of(item) == "refund"])
        audit.equal(amount(category, "purchases"), purchases, f"{where}: purchases")
        audit.equal(amount(category, "refunds"), refunds, f"{where}: refunds")
        audit.equal(
            amount(category, "netSpending"),
            purchases - refunds,
            f"{where}: category net spending",
        )


def audit_accounts(
    audit: Audit,
    publication: object,
    report: object,
    expected: dict[str, dict[str, tuple[str | None, str | None]]],
) -> None:
    """Audit coverage, balances and quiet months of one household report."""
    month = text(field(report, "period"), "id")
    where = f"{text(publication, 'publicationId')} {month}"
    for account in entries(report, "accounts"):
        account_id = text(account, "id")
        if account_id not in expected or month not in expected[account_id]:
            fail(where, f"unexpected account {account_id!r}")
        audit.equal(
            field(account, "evidenceThrough"),
            rule_evidence_through(account_id, text(publication, "knownAt")),
            f"{where} {account_id}: evidence through",
        )
        audit.expect(
            condition=text(account, "accountType") in ACCOUNT_TYPES,
            message=f"{where} {account_id}: account type",
        )
        audit.expect(
            condition=text(account, "ownershipScope") in OWNERSHIP_SCOPES,
            message=f"{where} {account_id}: ownership scope",
        )
        audit_account(
            audit, account, expected[account_id][month], f"{where} {account_id}"
        )


def audit_account(
    audit: Audit,
    account: object,
    expected: tuple[str | None, str | None],
    where: str,
) -> None:
    """Audit one account's coverage, balances and quiet month."""
    opening_expected, closing_expected = expected
    coverage = field(account, "coverage")
    balance = field(account, "balance")
    opening = field(account, "openingBalance")
    own = entries(account, "transactions")
    if text(coverage, "status") == NO_DATA:
        audit.expect(
            condition=field(balance, "amount") is None
            and field(balance, "asOf") is None,
            message=f"{where}: a no-data balance must be unknown",
        )
        audit.expect(
            condition=opening is None and not own,
            message=f"{where}: a no-data month has no opening balance or entries",
        )
    else:
        audit.equal(
            None if opening is None else Decimal(str(opening)),
            None if opening_expected is None else Decimal(opening_expected),
            f"{where}: opening balance",
        )
        audit.equal(
            Decimal(str(field(balance, "amount"))),
            Decimal(str(closing_expected)),
            f"{where}: closing balance",
        )
        audit.equal(
            Decimal(str(opening)) + total(own),
            Decimal(str(field(balance, "amount"))),
            f"{where}: balance chain",
        )
        audit.equal(
            field(account, "quietConfirmed"),
            not own and text(coverage, "status") == COMPLETE,
            f"{where}: quiet month",
        )
    for item in own:
        audit.equal(
            text(item, "accountId"), text(account, "id"), f"{where}: entry account"
        )


def audit_transfer_evidence(audit: Audit, publication: object, report: object) -> None:
    """Audit the transfer evidence of one household report."""
    month = text(field(report, "period"), "id")
    where = f"{text(publication, 'publicationId')} {month}"
    legs = entries(field(report, "transfers"), "transactions")
    for leg in legs:
        if kind_of(leg) != "transfer":
            continue
        group = field(leg, "transferGroupId")
        if group is None:
            audit.equal(
                text(leg, "transferBasis"), "one_sided", f"{where}: one-sided basis"
            )
            audit.expect(
                condition=bool(text(leg, "counterpartAccountName")),
                message=f"{where}: a one-sided transfer must name its counterpart",
            )
        else:
            others = [
                other
                for other in legs
                if field(other, "transferGroupId") == group and other is not leg
            ]
            audit.equal(
                len(others), 1, f"{where}: a transfer group must have exactly two legs"
            )
            audit.equal(text(leg, "transferBasis"), "paired", f"{where}: paired basis")


def audit_household(
    audit: Audit, publication: object, report: object, kind: str, month: str
) -> None:
    """Audit the household figures that are hand-checked."""
    where = f"{text(publication, 'publicationId')} {month}"
    measures = field(report, "measures")
    audit.equal(
        (
            str(field(measures, "income")),
            str(field(measures, "expenses")),
            str(field(measures, "netCashFlow")),
        ),
        MEASURES[kind][month],
        f"{where}: hand-checked measures",
    )
    unclassified = field(report, "unclassified")
    audit.equal(
        (
            field(unclassified, "count"),
            str(field(unclassified, "moneyIn")),
            str(field(unclassified, "moneyOut")),
        ),
        UNCLASSIFIED[kind].get(month, (0, "0.00", "0.00")),
        f"{where}: unclassified money",
    )
    adjustments = field(report, "adjustments")
    audit.equal(
        (
            field(adjustments, "count"),
            str(field(adjustments, "moneyIn")),
            str(field(adjustments, "moneyOut")),
        ),
        ADJUSTMENTS[kind].get(month, (0, "0.00", "0.00")),
        f"{where}: adjustments",
    )
    transfers = field(report, "transfers")
    audit.equal(
        (
            field(transfers, "count"),
            field(transfers, "pairedCount"),
            field(transfers, "oneSidedCount"),
            str(field(transfers, "moneyIn")),
            str(field(transfers, "moneyOut")),
        ),
        TRANSFERS[kind].get(month, (0, 0, 0, "0.00", "0.00")),
        f"{where}: transfers",
    )
    statuses = tuple(
        text(field(account, "coverage"), "status")
        for account in entries(report, "accounts")
    )
    audit.equal(statuses, COVERAGE_STATUS[kind][month], f"{where}: coverage status")
    combined = (
        COMPLETE
        if all(status == COMPLETE for status in statuses)
        else NO_DATA
        if all(status == NO_DATA for status in statuses)
        else PARTIAL
    )
    audit.equal(
        text(field(report, "coverage"), "status"),
        combined,
        f"{where}: combined coverage",
    )
    audit.equal(
        [
            text(entry, "id")
            for entry in entries(field(report, "coverage"), "incompleteAccounts")
        ],
        [
            account_id
            for account_id, status in zip(("mine", "common"), statuses, strict=True)
            if status != COMPLETE
        ],
        f"{where}: incomplete accounts",
    )
    if month in PROVISIONAL[kind]:
        audit.expect(
            condition=field(field(report, "period"), "provisional") is True
            and bool(entries(field(report, "period"), "provisionalReasons")),
            message=(
                f"{where}: a provisional month must carry the label and its reasons"
            ),
        )
    else:
        audit.expect(
            condition=field(field(report, "period"), "provisional") is False,
            message=f"{where}: a closed, fully covered month must not be provisional",
        )


@dataclass(frozen=True)
class PublicationFacts:
    """The publication fields the audit reuses."""

    kind: str
    label: str
    months: tuple[str, ...]
    known_at: str


def publication_facts(publication: object) -> PublicationFacts:
    """Return the fields the audit reuses, or fail when one is missing."""
    return PublicationFacts(
        kind=text(publication, "kind"),
        label=text(publication, "publicationId"),
        months=tuple(str(month) for month in entries(publication, "months")),
        known_at=text(publication, "knownAt"),
    )


def audit_publication(audit: Audit, publication: object) -> None:
    """Audit one publication: metadata, selections, reports and trust labels."""
    facts = publication_facts(publication)
    where = facts.label
    default = text(publication, "defaultMonth")
    audit.equal(default, facts.months[0], f"{where}: default month")
    audit.expect(
        condition=text(publication, "knownAt")[:7] in facts.months,
        message=f"{where}: the knowledge date must fall inside the shown months",
    )
    if facts.kind == "pipeline":
        audit.expect(
            condition=field(publication, "isCurrent") is True,
            message=f"{where}: pipeline must be current",
        )
    else:
        audit.expect(
            condition=field(publication, "isCurrent") is False,
            message=f"{where}: a view is never current",
        )
    audit_publication_views(audit, publication, facts)


def audit_publication_views(
    audit: Audit, publication: object, facts: PublicationFacts
) -> None:
    """Audit every account selection of one publication."""
    where = facts.label
    views = entries(publication, "views")
    expected_scopes = {
        tuple(sorted(scope))
        for size in range(1, 3)
        for scope in combinations(("common", "mine"), size)
    }
    audit.equal(
        {tuple(scope_of(view)) for view in views},
        expected_scopes,
        f"{where}: account selections",
    )
    provisional: set[str] = set()
    negative: set[str] = set()
    for view in views:
        scope = scope_of(view)
        for report in entries(view, "reports"):
            month, is_provisional, is_negative = audit_view_report(
                audit, publication, report, scope, facts
            )
            if is_provisional:
                provisional.add(month)
            if is_negative:
                negative.add(month)
    audit.equal(
        provisional, set(PROVISIONAL[facts.kind]), f"{where}: provisional months"
    )
    audit.equal(
        negative,
        set(NEGATIVE_MONTHS[facts.kind]),
        f"{where}: negative category months",
    )


def audit_view_report(
    audit: Audit,
    publication: object,
    report: object,
    scope: Sequence[str],
    facts: PublicationFacts,
) -> tuple[str, bool, bool]:
    """Audit one report of one account selection and return its flags."""
    where = facts.label
    month = text(field(report, "period"), "id")
    audit.expect(
        condition=month in facts.months,
        message=f"{where}: report month {month} is not listed",
    )
    audit_report(audit, publication, report, scope)
    audit.expect(
        condition=field(field(report, "period"), "provisional")
        is rule_provisional(month, facts.known_at, scope),
        message=f"{where} {month} {'+'.join(scope)}: provisional rule",
    )
    if scope == ["common", "mine"]:
        audit_accounts(
            audit,
            publication,
            report,
            PIPELINE_BALANCES if facts.kind == "pipeline" else PAST_BALANCES,
        )
        audit_transfer_evidence(audit, publication, report)
        audit_household(audit, publication, report, facts.kind, month)
    return (
        month,
        field(field(report, "period"), "provisional") is True,
        any(
            amount(category, "netSpending") < 0
            for category in entries(report, "categories")
        ),
    )


def audit_budget(audit: Audit, fixture: object) -> None:
    """Audit the synthetic budget comparison of the current publication."""
    current = next(
        publication
        for publication in entries(fixture, "publications")
        if field(publication, "isCurrent") is True
    )
    budget = field(current, "budgetExample")
    previous = Decimal(0)
    for block in entries(budget, "reports"):
        month = text(block, "month")
        audit.equal(
            amount(block, "plannedSpending"),
            Decimal(BUDGET_PLANNED_SPENDING),
            f"budget {month}: planned spending",
        )
        audit.equal(
            amount(block, "plannedSavings"),
            Decimal(BUDGET_PLANNED_SAVINGS),
            f"budget {month}: planned savings",
        )
        budget_rows = entries(block, "rows")
        audit.equal(
            sum(
                (
                    amount(row, "allocated")
                    for row in budget_rows
                    if field(row, "carryForward") is False
                ),
                Decimal(0),
            ),
            Decimal(BUDGET_PLANNED_SPENDING),
            f"budget {month}: allocations",
        )
        for row in budget_rows:
            available = amount(row, "available")
            actual = amount(row, "actual")
            audit.equal(
                available,
                amount(row, "opening") + amount(row, "allocated"),
                f"budget {month}: available",
            )
            audit.equal(
                amount(row, "remaining"),
                available - actual,
                f"budget {month}: remaining",
            )
            if field(row, "carryForward") is False:
                audit.equal(
                    amount(row, "opening"), Decimal(0), f"budget {month}: plain opening"
                )
                audit.equal(
                    amount(row, "savingsImpact"),
                    available - actual,
                    f"budget {month}: savings impact",
                )
        vacation = next(
            row for row in budget_rows if field(row, "carryForward") is True
        )
        audit.equal(
            amount(vacation, "opening"), previous, f"budget {month}: carried forward"
        )
        previous = amount(vacation, "carriedForward")
        audit.equal(
            (
                str(previous.quantize(CENT)),
                str(amount(block, "actualSavings").quantize(CENT)),
                str(amount(block, "savingsDifference").quantize(CENT)),
            ),
            BUDGET_EXPECTED[month],
            f"budget {month}: hand-checked result",
        )


def category_net(report: object) -> dict[str, str]:
    """Return one report's frozen net spending per category."""
    return {
        text(category, "id"): str(amount(category, "netSpending"))
        for category in entries(report, "categories")
    }


def household_reports(publication: object) -> dict[str, object]:
    """Return the household view's reports, keyed by month."""
    return {
        text(field(report, "period"), "id"): report
        for view in entries(publication, "views")
        if scope_of(view) == ["common", "mine"]
        for report in entries(view, "reports")
    }


def audit_trend_categories(audit: Audit, publication: object) -> None:
    """Audit the category series the trend chart may draw."""
    reports = household_reports(publication)
    for month, expected in TREND_NET.items():
        audit.equal(
            category_net(reports[month]), expected, f"trend {month}: categories"
        )
        # A category a month has no rows for may read zero only when every
        # account is complete that month; otherwise it stays unknown.
        confirmed = all(
            status == COMPLETE for status in COVERAGE_STATUS["pipeline"][month]
        )
        audit.equal(
            TREND_ABSENT[month],
            "zero" if confirmed else "unknown",
            f"trend {month}: a category with no rows",
        )
    seen = sorted({category for values in TREND_NET.values() for category in values})
    audit.equal(seen, sorted(TREND_CATEGORIES), "the category universe")
    audit.expect(
        condition=set(TREND_NET["2026-09"]) != set(seen),
        message="the selector must not stop at the newest month's categories",
    )
    audit.expect(
        condition=Decimal(TREND_NET["2026-08"]["clothes"]) < 0,
        message="a net refund stays negative in the category trend",
    )


def audit_trend_budget(audit: Audit, fixture: object, current: object) -> None:
    """Audit the budget points the trend chart may draw."""
    budget = field(current, "budgetExample")
    months = [text(block, "month") for block in entries(budget, "reports")]
    published = [str(month) for month in entries(current, "months")]
    audit.equal(months, list(TREND_BUDGET_MONTHS), "the months the budget covers")
    audit.equal(
        sorted(str(value) for value in entries(budget, "accountIds")),
        list(TREND_BUDGET_SCOPE),
        "the account scope the budget covers",
    )
    audit.expect(
        condition=set(months) <= set(published),
        message="every budget month must be a month of its own publication",
    )
    audit.expect(
        condition=set(published) != set(months),
        message="months outside the budget must keep an unknown budget, not zero",
    )
    for publication in entries(fixture, "publications"):
        if field(publication, "isCurrent") is True:
            continue
        audit.equal(
            field(publication, "budgetExample"),
            None,
            f"{text(publication, 'publicationId')}: no budget points in a past view",
        )
    for block in entries(budget, "reports"):
        month = text(block, "month")
        rows = {text(row, "id"): row for row in entries(block, "rows")}
        audit.equal(
            {key: str(amount(rows[key], "allocated")) for key in TREND_BUDGET},
            TREND_BUDGET,
            f"budget {month}: the category plans",
        )
        audit.equal(
            str(amount(block, "plannedSpending")),
            BUDGET_PLANNED_SPENDING,
            f"budget {month}: the all-category plan",
        )
        audit.equal(
            amount(block, "plannedIncome")
            - amount(block, "plannedSpending")
            - amount(block, "earmarked"),
            amount(block, "plannedSavings"),
            f"budget {month}: the earmarked reserve stays outside the expense plan",
        )
        reserve = rows["vacation"]
        audit.expect(
            condition=field(reserve, "carryForward") is True,
            message=f"budget {month}: the reserve is not a monthly expense budget",
        )
        audit.expect(
            condition=field(reserve, "categoryId") is None,
            message=f"budget {month}: the reserve names no spending category",
        )


def audit_trend_contract(audit: Audit, fixture: object) -> None:
    """Audit the frozen figures the trend chart is allowed to show."""
    current = next(
        publication
        for publication in entries(fixture, "publications")
        if field(publication, "isCurrent") is True
    )
    audit_trend_categories(audit, current)
    audit_trend_budget(audit, fixture, current)


def audit_scenarios(audit: Audit, fixture: object) -> None:
    """Audit the single-case scenarios this round has to keep available."""
    published = entries(fixture, "publications")
    managed = {
        text(account, "id"): str(field(account, "managedFrom"))[:7]
        for account in entries(fixture, "availableAccounts")
    }
    audit_export_rule(audit)
    audit_publication_set(audit, fixture, published, managed)
    current = next(
        publication
        for publication in published
        if field(publication, "isCurrent") is True
    )
    household = [
        report
        for view in entries(current, "views")
        if scope_of(view) == ["common", "mine"]
        for report in entries(view, "reports")
    ]
    audit_one_sided_scenario(audit, household, managed)
    audit_unmatched_scenario(audit, household)


def audit_publication_set(
    audit: Audit,
    fixture: object,
    published: Sequence[object],
    managed: dict[str, str],
) -> None:
    """Audit the publication metadata and the account registry."""
    audit.equal(managed, {"mine": "2026-04", "common": "2026-05"}, "managed periods")
    audit.equal(text(fixture, "currency"), CURRENCY, "fixture currency")
    for account in entries(fixture, "availableAccounts"):
        audit.expect(
            condition=text(account, "accountType") in ACCOUNT_TYPES,
            message=f"availableAccounts {text(account, 'id')}: account type",
        )
        audit.expect(
            condition=text(account, "ownershipScope") in OWNERSHIP_SCOPES,
            message=f"availableAccounts {text(account, 'id')}: ownership scope",
        )
    audit.equal(
        [
            text(publication, "publicationId")
            for publication in published
            if field(publication, "isCurrent") is True
        ],
        [text(fixture, "currentPublicationId")],
        "the current publication",
    )
    audit.equal(
        sorted(text(publication, "kind") for publication in published),
        ["as_known_at", "as_was", "pipeline"],
        "publication kinds",
    )
    for publication in published:
        expected_budget = field(publication, "isCurrent") is True
        audit.equal(
            field(publication, "budgetExample") is not None,
            expected_budget,
            f"{text(publication, 'publicationId')}: budget example",
        )


def audit_one_sided_scenario(
    audit: Audit, household: Sequence[object], managed: dict[str, str]
) -> None:
    """Audit the manually decided one-sided transfer."""
    one_sided = [
        leg
        for report in household
        for leg in entries(field(report, "transfers"), "transactions")
        if field(leg, "transferGroupId") is None
    ]
    audit.equal(len(one_sided), 1, "one-sided transfer legs in the current publication")
    for leg in one_sided:
        counterpart = text(leg, "counterpartAccountId")
        audit.expect(
            condition=managed.get(counterpart, "") > text(leg, "date")[:7],
            message=(
                "the one-sided transfer must lie outside the counterpart's "
                "managed period"
            ),
        )
        audit.expect(
            condition=text(leg, "accountId") != counterpart,
            message="a one-sided transfer needs a counterpart on another account",
        )


def audit_unmatched_scenario(audit: Audit, household: Sequence[object]) -> None:
    """Audit the unmatched transfer claim and the wording of unknown money."""
    claims = [
        item
        for report in household
        for item in entries(field(report, "unclassified"), "transactions")
        if "Overførsel" in text(item, "description")
    ]
    audit.equal(len(claims), 1, "unmatched transfer claims shown as unknown")
    for claim in claims:
        audit.equal(kind_of(claim), "unknown", "an unmatched claim must stay unknown")
        audit.equal(
            field(claim, "category"), None, "an unmatched claim must have no category"
        )
    from_any_report = [
        item
        for report in household
        for item in entries(field(report, "unclassified"), "transactions")
    ]
    audit.expect(
        condition=all(has_no_review_reason(item) for item in from_any_report),
        message="unclassified money must not expose a privileged reason",
    )


def has_no_review_reason(item: object) -> bool:
    """Return whether an unclassified entry carries no review reason."""
    return not any(
        key in obj(item, "unclassified entry")
        for key in ("reviewReason", "reviewItemId", "ruleIds", "decisionId")
    )


def main() -> int:
    """Audit the fixture and print one summary line."""
    if not FIXTURE.exists():
        sys.stdout.write(f"{FIXTURE.name} is missing. Run build_example.py first.\n")
        return 1
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    audit = Audit()
    try:
        audit.equal(text(fixture, "schemaVersion"), "prototype-11/v2", "schema version")
        audit_scenarios(audit, fixture)
        for publication in entries(fixture, "publications"):
            audit_publication(audit, publication)
        audit_budget(audit, fixture)
        audit_trend_contract(audit, fixture)
    except FixtureError as error:
        sys.stdout.write(f"FAIL: {error}\n")
        return 1
    except StopIteration:
        sys.stdout.write("FAIL: the fixture has no current publication.\n")
        return 1
    if audit.failures:
        sys.stdout.write(
            f"FAIL: {len(audit.failures)} af {audit.checks} kontroller fejlede.\n"
        )
        for failure in audit.failures:
            sys.stdout.write(f"  - {failure}\n")
        return 1
    sys.stdout.write(
        f"OK: {len(entries(fixture, 'publications'))} offentliggørelser og "
        f"{audit.checks} kontroller uden fejl. Regnestykker, dækning, foreløbige "
        "måneder, overførsler og budget stemmer.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
