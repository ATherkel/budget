# Copyright 2026 Therkel
"""Enkel's monthly actuals: the report's figures, Categories and trust notes.

Expected values are the worked examples in `report-contract.md`, over the
synthetic worked-example publication; the dashboard is driven in-process.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Page, read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

# The worked examples' reference date: May is the current month.
REFERENCE_DATE = "2026-05-14"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def report(
    client: TestClient,
    month: str,
    accounts: tuple[str, ...] = (CURRENT, SAVINGS),
    reference_date: str = REFERENCE_DATE,
) -> Page:
    """Return the report fragment the page's form asks for."""
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": reference_date,
            "account": list(accounts),
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_the_report_shows_income_expenses_and_money_left_in_danish_kroner(
    client: TestClient,
) -> None:
    # February: income 25,000.00, expenses 9,020.00, net cash flow 15,980.00.
    february = report(client, "2026-02")

    assert (
        february.text_of("income"),
        february.text_of("expenses"),
        february.text_of("money-left"),
    ) == ("25.000,00 kr.", "9.020,00 kr.", "15.980,00 kr.")


def test_every_category_is_listed_in_the_order_the_report_gives(
    client: TestClient,
) -> None:
    # February: rent 8,500.00, then groceries 520.00 (640.00 less a 120.00 Refund).
    february = report(client, "2026-02")

    assert february.text_of("categories") == "Rent 8.500,00 kr. Groceries 520,00 kr."


def test_money_left_below_zero_carries_a_minus_sign(client: TestClient) -> None:
    # March: income 0.00 and expenses 1,000.00 leave -1,000.00, written with
    # the minus sign the report contract writes, not a hyphen.
    march = report(client, "2026-03")

    assert march.text_of("money-left") == "\N{MINUS SIGN}1.000,00 kr."


def test_a_partial_report_names_its_incomplete_accounts_and_links_the_explanation(
    client: TestClient,
) -> None:
    # February is partial: Joint current's month has a balance break. The link
    # keeps the page's pinned context and selection.
    february = report(client, "2026-02")

    assert (
        "Joint current" in (february.text_of("coverage-note") or ""),
        "Joint savings" in (february.text_of("coverage-note") or ""),
        february.attributes("coverage-explanation").get("href"),
    ) == (
        True,
        False,
        (
            "/explanation?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-02"
        ),
    )


def test_only_a_month_that_may_still_change_is_labelled_provisional(
    client: TestClient,
) -> None:
    # May is the reference date's month; February is closed and settled.
    may, february = report(client, "2026-05"), report(client, "2026-02")

    assert (
        may.text_of("provisional-label"),
        february.text_of("provisional-label"),
    ) == ("Foreløbige tal", None)


def test_unclassified_money_is_noted_quietly_without_its_amounts(
    client: TestClient,
) -> None:
    # March has one Unclassified transaction of -450.00; February has none.
    # The amounts and the count belong to Kontrol, never to Enkel.
    march, february = report(client, "2026-03"), report(client, "2026-02")

    assert (
        march.text_of("unclassified-note") is not None,
        "450" in march.visible(),
        march.attributes("unclassified-explanation").get("href"),
        february.text_of("unclassified-note"),
    ) == (
        True,
        False,
        (
            "/explanation?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-03"
        ),
        None,
    )


def explanation(client: TestClient, month: str) -> Page:
    """Return the explanation page a report's link opens, both accounts selected."""
    response = client.get(
        "/explanation",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": REFERENCE_DATE,
            "account": [CURRENT, SAVINGS],
            "month": month,
        },
    )
    assert response.status_code == 200
    return read(response.text)


def test_the_explanation_names_the_incomplete_and_unsettled_months_of_the_pinned_report(
    client: TestClient,
) -> None:
    # May is the current month, both accounts' May rows are partial and their
    # late bookings unsettled. The page keeps the pin and shows no amounts.
    may = explanation(client, "2026-05")
    coverage = may.text_of("explanation-coverage") or ""
    provisional = may.text_of("explanation-provisional") or ""

    assert (
        "Joint current" in coverage and "Joint savings" in coverage,
        "maj 2026" in coverage,
        "indeværende måned" in provisional,
        "Joint current" in provisional and "Joint savings" in provisional,
        "kr." in may.visible(),
        may.attributes("back-to-report").get("href"),
    ) == (
        True,
        True,
        True,
        True,
        False,
        (
            "/?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-05"
        ),
    )


def test_the_explanation_says_whether_the_report_has_unclassified_money(
    client: TestClient,
) -> None:
    # March has Unclassified money and February has none; neither shows its
    # amounts or count, which belong to Kontrol.
    march, february = explanation(client, "2026-03"), explanation(client, "2026-02")

    assert (
        march.text_of("explanation-unclassified") is not None,
        "450" in march.visible(),
        february.text_of("explanation-unclassified"),
    ) == (True, False, None)


def test_a_month_without_data_shows_its_figures_as_unknown_never_as_zero(
    client: TestClient,
) -> None:
    # June on 3 June: selectable, but no account has evidence for it yet.
    june = report(client, "2026-06", reference_date="2026-06-03")

    assert (
        june.text_of("income"),
        june.text_of("expenses"),
        june.text_of("money-left"),
        "0,00" in june.visible(),
    ) == ("Ingen data endnu", "Ingen data endnu", "Ingen data endnu", False)


def test_a_confirmed_quiet_month_shows_zero_without_a_trust_note(
    client: TestClient,
) -> None:
    # March, Joint savings only: coverage complete and nothing happened, so
    # zero is a known zero and no note is owed.
    quiet = report(client, "2026-03", accounts=(SAVINGS,))

    assert (
        quiet.text_of("income"),
        quiet.text_of("expenses"),
        quiet.text_of("money-left"),
        quiet.text_of("coverage-note"),
        quiet.text_of("unclassified-note"),
    ) == ("0,00 kr.", "0,00 kr.", "0,00 kr.", None, None)


def test_a_report_without_data_names_its_accounts_and_links_the_explanation(
    client: TestClient,
) -> None:
    # June on 3 June: neither account has evidence yet.
    june = report(client, "2026-06", reference_date="2026-06-03")
    note = june.text_of("coverage-note") or ""

    assert (
        "Joint current" in note and "Joint savings" in note,
        june.attributes("coverage-explanation").get("href"),
    ) == (
        True,
        (
            "/explanation?publication=1&reference_date=2026-06-03"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-06"
        ),
    )
