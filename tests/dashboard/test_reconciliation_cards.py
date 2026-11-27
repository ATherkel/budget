# Copyright 2026 Therkel
"""Overblik's Afstemning per account, rendered through the one card macro.

Expected values are the Gold worked example's tables in
`tests/gold/worked_example.py`; the dashboard is driven in-process.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.analytics import ReportContext, diagnostics
from budget.dashboard.features.report.reconciliation_cards import (
    reconciliation_cards,
)
from budget.gold import GoldResult, ReportingMonth
from tests.dashboard.pages import Disclosure, Page, read
from tests.dashboard.test_summary_cards import CARDS, _logged_in
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS

MINUS = "\N{MINUS SIGN}"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _logged_in(tmp_path)


def _overview(client: TestClient, month: str, accounts: list[str]) -> Page:
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": "2026-05-14",
            "account": accounts,
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_overblik_shows_a_closed_afstemning_card_for_each_account(
    client: TestClient,
) -> None:
    # report-contract.md's March example: opening 37,037.50, income minus
    # expenses -1,000.00, unclassified out -450.00, closing 35,587.50 and an
    # opening gap of -500.00 against February's close of 37,537.50.
    page = _overview(client, "2026-03", [CURRENT])

    assert page.disclosures.get(f"reconciliation-{CURRENT}-card") == Disclosure(
        open=False,
        summary="Afstemning, Joint current 0,00 kr.",
        rows=[
            ("Startsaldo", "37.037,50 kr."),
            ("Indtægter minus udgifter", f"{MINUS}1.000,00 kr."),
            ("Overførsler", "0,00 kr."),
            ("Ukategoriseret ind", "0,00 kr."),
            ("Ukategoriseret ud", f"{MINUS}450,00 kr."),
            ("Regulering ind", "0,00 kr."),
            ("Regulering ud", "0,00 kr."),
            ("Beregnet slutsaldo", "35.587,50 kr."),
            ("Bankens slutsaldo", "35.587,50 kr."),
            ("Uforklaret forskel", "0,00 kr."),
            ("Åbningsforskel", f"{MINUS}500,00 kr."),
        ],
    )


def test_a_month_without_evidence_reads_unknown_and_cannot_be_reconciled() -> None:
    # June is after the latest published month, so nothing about it is known.
    context = ReportContext(
        publication_id=PUBLICATION.publication_id,
        account_ids=frozenset((CURRENT,)),
        month=ReportingMonth(2026, 6),
        reference_date=date(2026, 6, 3),
    )
    report = diagnostics(GoldResult(PUBLICATION, RECORDS), context, is_current=True)
    page = read(CARDS.render(cards=reconciliation_cards(report)))

    assert page.disclosures.get(f"reconciliation-{CURRENT}-card") == Disclosure(
        open=False,
        summary="Afstemning, Joint current Ikke mulig at afstemme",
        rows=[
            ("Startsaldo", "Ukendt"),
            ("Indtægter minus udgifter", "Ukendt"),
            ("Overførsler", "Ukendt"),
            ("Ukategoriseret ind", "Ukendt"),
            ("Ukategoriseret ud", "Ukendt"),
            ("Regulering ind", "Ukendt"),
            ("Regulering ud", "Ukendt"),
            ("Beregnet slutsaldo", "Ukendt"),
            ("Bankens slutsaldo", "Ukendt"),
            ("Uforklaret forskel", "Ikke mulig at afstemme"),
            ("Åbningsforskel", "Ukendt"),
        ],
    )
