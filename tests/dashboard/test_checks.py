# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the selection's trust diagnostics.

The dashboard is driven in-process over the synthetic worked example.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult, ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import Page, read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

KONTROL = {
    "publication": "1",
    "reference_date": "2026-05-14",
    "account": [CURRENT, SAVINGS],
    "month": "2026-03",
    "mode": "advanced",
    "tab": "checks",
}


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303
    return client


def kontrol(client: TestClient, **changes: str) -> Page:
    """Return the Kontrol fragment for the worked example, with `changes`."""
    return read(
        client.get(
            "/report",
            params={**KONTROL, **changes},
            headers={"HX-Request": "true"},
        ).text
    )


def test_avanceret_tab_bar_links_kontrol_and_marks_it_current_there(
    client: TestClient,
) -> None:
    overview = kontrol(client, tab="overview")
    checks = kontrol(client)
    link = parse_qs(urlsplit(overview.attributes("tab-checks").get("href", "")).query)

    assert (
        overview.text_of("tab-checks"),
        overview.attributes("tab-checks").get("aria-current"),
        link.get("tab"),
        link.get("account"),
        link.get("month"),
        checks.attributes("tab-checks").get("aria-current"),
        checks.attributes("tab-overview").get("aria-current"),
    ) == ("Kontrol", None, ["checks"], [CURRENT, SAVINGS], ["2026-03"], "page", None)


def test_kontrol_shows_the_selections_coverage(client: TestClient) -> None:
    # March lacks part of Joint current; April is fully covered for both.
    assert (
        kontrol(client).text_of("checks-coverage"),
        kontrol(client, month="2026-04").text_of("checks-coverage"),
    ) == ("Dækning: delvist dækket.", "Dækning: fuldt dækket.")


def test_kontrol_lists_each_incomplete_account_month(client: TestClient) -> None:
    # March lacks part of Joint current only; April lacks nothing.
    assert (
        kontrol(client).text_of("checks-incomplete-months"),
        kontrol(client, month="2026-04").text_of("checks-incomplete-months"),
    ) == (
        "Joint current, marts 2026: delvist dækket.",
        "Ingen valgte kontomåneder mangler dækning.",
    )


def test_kontrol_names_each_reason_the_figures_are_provisional(
    profile: Profile,
    client: TestClient,
) -> None:
    # Publication 2 leaves Joint current's April late bookings unsettled.
    april = ReportingMonth(2026, 4)
    unsettled = tuple(
        replace(snapshot, late_bookings_settled=False)
        if snapshot.account_id == CURRENT and snapshot.month == april
        else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                replace(RECORDS, monthly_balances=unsettled),
            ),
            RECIPE,
            CONFIGURATION,
        )

    assert (
        kontrol(client, month="2026-05").text_of("checks-provisional"),
        kontrol(client, publication="2", month="2026-04").text_of("checks-provisional"),
        kontrol(client, month="2026-04").text_of("checks-provisional"),
    ) == (
        (
            "Foreløbigt: maj 2026 er indeværende måned, så der kan stadig komme "
            "posteringer. Sene bogføringer kan stadig komme fra Joint current og "
            "Joint savings."
        ),
        "Foreløbigt: Sene bogføringer kan stadig komme fra Joint current.",
        None,
    )


def test_kontrol_shows_each_accounts_evidence_through_and_unknown_is_never_a_date(
    profile: Profile,
    client: TestClient,
) -> None:
    # Publication 2 knows no Evidence through for Joint savings.
    accounts = tuple(
        replace(account, evidence_through=None)
        if account.account_id == SAVINGS
        else account
        for account in RECORDS.accounts
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                replace(RECORDS, accounts=accounts),
            ),
            RECIPE,
            CONFIGURATION,
        )
    page = kontrol(client, publication="2")

    assert (
        page.text_of(f"checks-evidence-{CURRENT}"),
        page.text_of(f"checks-evidence-{SAVINGS}"),
    ) == (
        # Worded as Detaljer words it.
        "Joint current: Gennem 08.05.2026",
        "Joint savings: Ingen importeret data",
    )


def test_kontrol_lists_each_accounts_reconciliation_components(
    client: TestClient,
) -> None:
    # The worked example's March, as the report contract states it.
    page = kontrol(client)

    assert (
        page.text_of(f"checks-reconciliation-{CURRENT}-components"),
        page.text_of(f"checks-reconciliation-{SAVINGS}-components"),
    ) == (
        (
            "Åbning: 37.037,50 kr. "
            "Indtægter minus udgifter: \N{MINUS SIGN}1.000,00 kr. "
            "Overførsler: 0,00 kr. "
            "Ukategoriseret ind: 0,00 kr. "
            "Ukategoriseret ud: \N{MINUS SIGN}450,00 kr. "
            "Regulering ind: 0,00 kr. "
            "Regulering ud: 0,00 kr. "
            "Lukning: 35.587,50 kr."
        ),
        (
            "Åbning: 53.000,00 kr. "
            "Indtægter minus udgifter: 0,00 kr. "
            "Overførsler: 0,00 kr. "
            "Ukategoriseret ind: 0,00 kr. "
            "Ukategoriseret ud: 0,00 kr. "
            "Regulering ind: 0,00 kr. "
            "Regulering ud: 0,00 kr. "
            "Lukning: 53.000,00 kr."
        ),
    )


def test_changing_account_or_month_inside_kontrol_stays_on_kontrol(
    client: TestClient,
) -> None:
    changed = client.get(
        "/report",
        params={
            **KONTROL,
            "account": [CURRENT],
            "month": "2026-04",
            "active_mode": "advanced",
        },
        headers={"HX-Request": "true"},
    )
    fragment = read(changed.text)
    pushed = changed.headers["hx-push-url"]
    restored = read(client.get(pushed).text)

    assert (
        fragment.attributes("report").get("data-tab"),
        fragment.hidden("tab"),
        parse_qs(urlsplit(pushed).query),
        restored.attributes("report").get("data-tab"),
        restored.hidden("tab"),
    ) == (
        "checks",
        "checks",
        {
            "publication": ["1"],
            "reference_date": ["2026-05-14"],
            "account": [CURRENT],
            "month": ["2026-04"],
            "mode": ["advanced"],
            "tab": ["checks"],
            "comparison": ["amounts"],
        },
        "checks",
        "checks",
    )


def test_an_ordinary_kontrol_to_enkel_form_lands_on_enkel_overview(
    client: TestClient,
) -> None:
    # R1: the form sends Kontrol's tab with the new mode.
    response = client.get(
        "/report",
        params={**KONTROL, "mode": "simple", "active_mode": "advanced"},
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)

    assert (
        response.status_code,
        fragment.attributes("report").get("data-mode"),
        fragment.attributes("report").get("data-tab"),
        fragment.hidden("tab"),
        parse_qs(urlsplit(response.headers["hx-push-url"]).query)["tab"],
    ) == (200, "simple", "overview", "overview", ["overview"])


def test_kontrol_cleared_then_enkel_then_avanceret_reselects_into_overblik(
    client: TestClient,
) -> None:
    # R4: each step submits the hidden state the previous response left.
    def submit(
        mode: str, accounts: list[str], previous: Page
    ) -> tuple[Page, dict[str, list[str]]]:
        response = client.get(
            "/report",
            params={
                **KONTROL,
                "account": accounts,
                "mode": mode,
                "active_mode": previous.hidden("active_mode"),
                "tab": previous.hidden("tab"),
            },
            headers={"HX-Request": "true"},
        )
        pushed = parse_qs(urlsplit(response.headers["hx-push-url"]).query)
        return read(response.text), pushed

    start = kontrol(client, active_mode="advanced")
    cleared, _ = submit("advanced", [], start)
    enkel, _ = submit("simple", [], cleared)
    avanceret, _ = submit("advanced", [], enkel)
    report, pushed = submit("advanced", [CURRENT], avanceret)

    assert (
        report.attributes("report").get("data-mode"),
        report.attributes("report").get("data-tab"),
        report.hidden("active_mode"),
        report.hidden("tab"),
        pushed["mode"],
        pushed["tab"],
    ) == ("advanced", "overview", "advanced", "overview", ["advanced"], ["overview"])
