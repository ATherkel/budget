# Copyright 2026 Therkel
"""Detaljer's Ind and Ud per account, rendered through the one card macro.

Expected values are the Gold worked example's tables in
`tests/gold/worked_example.py`; the dashboard is driven in-process.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.dashboard.pages import Disclosure, Page, read
from tests.dashboard.test_summary_cards import _logged_in
from tests.gold.worked_example import CURRENT, PUBLICATION, SAVINGS


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _logged_in(tmp_path)


def _details(client: TestClient, month: str, account: str = CURRENT) -> Page:
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": "2026-05-14",
            "account": [account],
            "month": month,
            "mode": "advanced",
            "tab": "details",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_each_account_shows_its_ind_and_ud_as_cards_of_their_rows(
    client: TestClient,
) -> None:
    # January's current rows: +25,000.00 salary, -3,000.00 transfer to savings
    # and -842.50 groceries; the transfer counts toward Ud.
    page = _details(client, "2026-01")

    assert (
        page.disclosures.get(f"activity-in-{CURRENT}-card"),
        page.disclosures.get(f"activity-out-{CURRENT}-card"),
    ) == (
        Disclosure(
            open=False,
            summary="Ind +25.000,00 kr.",
            rows=[("14.01.2026", "SALARY", "Indtægt", "+25.000,00 kr.")],
        ),
        Disclosure(
            open=False,
            summary="Ud \N{MINUS SIGN}3.842,50 kr.",
            rows=[
                ("28.01.2026", "GROCERIES", "Udgift", "\N{MINUS SIGN}842,50 kr."),
                (
                    "20.01.2026",
                    "TRANSFER",
                    "Overførsel, parret med Joint savings den 20.01.2026",
                    "\N{MINUS SIGN}3.000,00 kr.",
                ),
            ],
        ),
    )


def test_a_quiet_month_says_so_in_each_card(client: TestClient) -> None:
    # report-contract.md, "March, joint-savings only: a confirmed quiet month".
    page = _details(client, "2026-03", SAVINGS)

    assert (
        page.disclosures.get(f"activity-in-{SAVINGS}-card"),
        page.disclosures.get(f"activity-out-{SAVINGS}-card"),
    ) == (
        Disclosure(
            open=False, summary="Ind 0,00 kr.", rows=[("Ingen penge ind i måneden.",)]
        ),
        Disclosure(
            open=False, summary="Ud 0,00 kr.", rows=[("Ingen penge ud i måneden.",)]
        ),
    )
