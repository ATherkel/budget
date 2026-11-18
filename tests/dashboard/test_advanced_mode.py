# Copyright 2026 Therkel
"""The Enkel and Avanceret display contract."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(create_app(profile, clock=lambda: PUBLICATION.known_at))
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


def test_fresh_visit_has_an_accessible_mode_control_and_amounts_default(
    client: TestClient,
) -> None:
    html = client.get("/").text
    page = read(html)

    assert (
        page.attributes("mode-control").get("role"),
        page.checked("mode"),
        page.hidden("comparison"),
        page.text_of("comparison-choice"),
        "Avanceret" in page.visible(),
        0 <= html.find('id="mode-control"') < html.find('class="account-fieldset"'),
    ) == ("group", {"simple"}, "amounts", "Beløb", True, True)


def test_advanced_details_show_dated_balances_separately_from_month_snapshot(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            "publication": "1",
            "reference_date": "2026-05-14",
            "account": "joint-current",
            "month": "2026-04",
            "mode": "advanced",
            "active_mode": "advanced",
            "tab": "details",
        },
        headers={"HX-Request": "true"},
    )
    page = read(response.text)

    assert (
        page.attributes("report").get("data-tab"),
        page.text_of("activity-dated-balance-joint-current"),
        page.text_of("activity-earlier-observation-joint-current"),
        page.text_of("activity-monthly-snapshot-joint-current"),
        page.text_of("activity-evidence-joint-current"),
    ) == (
        "details",
        "52.087,50 kr. den 24.04.2026",
        "35.587,50 kr. den 20.03.2026",
        ("Månedssnapshot: Åbning 35.587,50 kr.; lukning 52.087,50 kr.; fuldt dækket."),
        "Gennem 08.05.2026",
    )


def test_kontrol_shows_observed_counts_and_reconciliation_without_upgrading_coverage(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            "publication": "1",
            "reference_date": "2026-05-14",
            "account": ["joint-current", "joint-savings"],
            "month": "2026-03",
            "mode": "advanced",
            "active_mode": "advanced",
            "tab": "checks",
        },
        headers={"HX-Request": "true"},
    )
    page = read(response.text)

    assert (
        page.text_of("diagnostics-unclassified"),
        page.text_of("diagnostics-adjustments"),
        page.text_of("diagnostics-reconciliation-joint-current-residual"),
        page.text_of("diagnostics-reconciliation-joint-current-opening-gap"),
        page.text_of("diagnostics-reconciliation-joint-current-coverage"),
    ) == (
        "Ukategoriseret: ind 0,00 kr.; ud \N{MINUS SIGN}450,00 kr.; 1 postering.",
        "Reguleringer: ind 0,00 kr.; ud 0,00 kr.; 0 posteringer.",
        "Beregnet afvigelse: 0,00 kr.",
        "Åbningsforskel mod forrige lukning: \N{MINUS SIGN}500,00 kr.",
        "Dækning: delvist dækket.",
    )


def test_targeted_kontrol_link_keeps_the_originating_simple_view(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            "publication": "1",
            "reference_date": "2026-05-14",
            "account": ["joint-current", "joint-savings"],
            "month": "2026-03",
            "mode": "simple",
            "active_mode": "simple",
            "tab": "overview",
        },
        headers={"HX-Request": "true"},
    )
    simple = read(response.text)
    target = simple.attributes("coverage-explanation")["href"]
    query = parse_qs(urlsplit(target).query)
    origin = (
        "/?publication=1&reference_date=2026-05-14"
        "&account=joint-current&account=joint-savings&month=2026-03"
        "&mode=simple&tab=overview&comparison=amounts"
    )

    checks = read(client.get(target).text)

    assert (
        query["mode"],
        query["tab"],
        query.get("return_to"),
        checks.attributes("report").get("data-mode"),
        checks.attributes("report").get("data-tab"),
        checks.attributes("return-from-control").get("href"),
    ) == (
        ["advanced"],
        ["checks"],
        [origin],
        "advanced",
        "checks",
        origin,
    )
