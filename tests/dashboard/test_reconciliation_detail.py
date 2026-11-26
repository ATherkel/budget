# Copyright 2026 Therkel
"""Opening-to-closing reconciliation in the monthly overview."""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import (
    GoldCategoryAllocation,
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
)
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

REFERENCE_DATE = "2026-05-14"


@dataclass(frozen=True)
class _Movement:
    transaction_id: str
    account_id: str
    transaction_date: date
    account_sequence: int
    amount: str
    description: str
    transaction_type: TransactionType
    category_id: str | None = None
    transfer_group_id: str | None = None


@dataclass(frozen=True)
class _EndpointCase:
    closing: str | None
    observed: str
    residual: str


def _transaction(movement: _Movement) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=movement.transaction_id,
        account_id=movement.account_id,
        transaction_date=movement.transaction_date,
        account_sequence=movement.account_sequence,
        amount=Decimal(movement.amount),
        description=movement.description,
        transaction_type=movement.transaction_type,
        transfer_group_id=movement.transfer_group_id,
        balance_after=None,
        balance_check="missing_balance",
    )


def _allocation(movement: _Movement) -> GoldCategoryAllocation:
    assert movement.category_id is not None
    return GoldCategoryAllocation(
        allocation_id=f"{movement.transaction_id}/{movement.category_id}",
        transaction_id=movement.transaction_id,
        account_id=movement.account_id,
        transaction_date=movement.transaction_date,
        category_id=movement.category_id,
        amount=Decimal(movement.amount),
    )


def _records(closing: str | None) -> GoldRecords:
    movements = (
        _Movement(
            "reconciliation-income",
            CURRENT,
            date(2026, 3, 2),
            1,
            "500.00",
            "INCOME",
            "income",
            "salary",
        ),
        _Movement(
            "reconciliation-expense",
            CURRENT,
            date(2026, 3, 3),
            2,
            "-200.00",
            "EXPENSE",
            "expense",
            "rent",
        ),
        _Movement(
            "reconciliation-transfer-out",
            CURRENT,
            date(2026, 3, 4),
            3,
            "-100.00",
            "TRANSFER OUT",
            "transfer",
            transfer_group_id="reconciliation-transfer",
        ),
        _Movement(
            "reconciliation-transfer-in",
            SAVINGS,
            date(2026, 3, 4),
            1,
            "100.00",
            "TRANSFER IN",
            "transfer",
            transfer_group_id="reconciliation-transfer",
        ),
        _Movement(
            "reconciliation-unknown-in",
            CURRENT,
            date(2026, 3, 5),
            4,
            "450.00",
            "UNKNOWN IN",
            "unknown",
        ),
        _Movement(
            "reconciliation-unknown-out",
            CURRENT,
            date(2026, 3, 6),
            5,
            "-450.00",
            "UNKNOWN OUT",
            "unknown",
        ),
        _Movement(
            "reconciliation-adjustment-in",
            CURRENT,
            date(2026, 3, 7),
            6,
            "25.00",
            "ADJUSTMENT IN",
            "adjustment",
        ),
        _Movement(
            "reconciliation-adjustment-out",
            CURRENT,
            date(2026, 3, 8),
            7,
            "-25.00",
            "ADJUSTMENT OUT",
            "adjustment",
        ),
    )
    previous = MonthlyBalanceSnapshot(
        account_id=CURRENT,
        month=ReportingMonth(2026, 2),
        opening_balance=Decimal("800.00"),
        closing_balance=Decimal("900.00"),
        coverage="complete",
        late_bookings_settled=True,
    )
    selected = MonthlyBalanceSnapshot(
        account_id=CURRENT,
        month=ReportingMonth(2026, 3),
        opening_balance=Decimal("1000.00"),
        closing_balance=None if closing is None else Decimal(closing),
        coverage="complete",
        late_bookings_settled=True,
    )
    return replace(
        RECORDS,
        transactions=tuple(_transaction(movement) for movement in movements),
        category_allocations=tuple(
            _allocation(movement)
            for movement in movements
            if movement.category_id is not None
        ),
        monthly_balances=(previous, selected),
    )


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(
        create_app(
            profile,
            clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC),
        ),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303
    return client


@pytest.mark.parametrize("mode", ["simple", "advanced"])
@pytest.mark.parametrize(
    "endpoints",
    [
        _EndpointCase("1235.00", "1.235,00 kr.", "+35,00 kr."),
        _EndpointCase(None, "Ingen data endnu", "Ikke mulig at afstemme"),
    ],
    ids=["complete-endpoints", "missing-closing"],
)
def test_overview_reconciles_opening_to_closing_with_named_components(
    profile: Profile,
    client: TestClient,
    mode: str,
    endpoints: _EndpointCase,
) -> None:
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                _records(endpoints.closing),
            ),
            RECIPE,
            CONFIGURATION,
        )

    response = client.get(
        "/report",
        params={
            "publication": "2",
            "reference_date": REFERENCE_DATE,
            "account": [CURRENT],
            "month": "2026-03",
            "mode": mode,
            "tab": "overview",
            "comparison": "amounts",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200, response.text
    page = read(response.text)

    assert (
        page.attributes("report").get("data-mode"),
        page.attributes("report").get("data-publication"),
        page.attributes("report").get("data-accounts"),
        page.attributes("report").get("data-month"),
        page.text_of("income"),
        page.text_of("expenses"),
        page.text_of("money-left"),
    ) == (
        mode,
        "2",
        CURRENT,
        "2026-03",
        "500,00 kr.",
        "200,00 kr.",
        "300,00 kr.",
    )
    assert [disclosure.summary for disclosure in page.disclosures[:3]] == [
        "Indtægter 500,00 kr.",
        "Udgifter 200,00 kr.",
        "Overførsler \N{MINUS SIGN}100,00 kr.",
    ]
    assert any(
        disclosure.summary == "Afstemning for Joint current"
        for disclosure in page.disclosures
    )
    reconciliation = next(
        disclosure
        for disclosure in page.disclosures
        if disclosure.summary == "Afstemning for Joint current"
    )
    assert reconciliation.open is False
    assert reconciliation.rows[0] == ("Post", "Beløb")
    details = {row[0]: row[1] for row in reconciliation.rows[1:]}
    assert details == {
        "Åbning": "1.000,00 kr.",
        "Indtægter minus udgifter": "+300,00 kr.",
        "Nettooverførsler": "\N{MINUS SIGN}100,00 kr.",
        "Ukategoriseret ind": "+450,00 kr.",
        "Ukategoriseret ud": "\N{MINUS SIGN}450,00 kr.",
        "Reguleringer ind": "+25,00 kr.",
        "Reguleringer ud": "\N{MINUS SIGN}25,00 kr.",
        "Forventet lukning": "1.200,00 kr.",
        "Observeret lukning": endpoints.observed,
        "Uforklaret forskel": endpoints.residual,
        "Åbningsafvigelse": "+100,00 kr.",
    }
