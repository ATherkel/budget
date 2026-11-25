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
            "Startsaldo: 37.037,50 kr. "
            "Indtægter minus udgifter: \N{MINUS SIGN}1.000,00 kr. "
            "Overførsler: 0,00 kr. "
            "Ukategoriseret ind: 0,00 kr. "
            "Ukategoriseret ud: \N{MINUS SIGN}450,00 kr. "
            "Regulering ind: 0,00 kr. "
            "Regulering ud: 0,00 kr. "
            "Slutsaldo: 35.587,50 kr."
        ),
        (
            "Startsaldo: 53.000,00 kr. "
            "Indtægter minus udgifter: 0,00 kr. "
            "Overførsler: 0,00 kr. "
            "Ukategoriseret ind: 0,00 kr. "
            "Ukategoriseret ud: 0,00 kr. "
            "Regulering ind: 0,00 kr. "
            "Regulering ud: 0,00 kr. "
            "Slutsaldo: 53.000,00 kr."
        ),
    )


def test_kontrol_reads_a_missing_reconciliation_component_as_unknown_not_zero(
    client: TestClient,
) -> None:
    # May has no monthly snapshot yet, so its balances are missing.
    assert kontrol(client, month="2026-05").text_of(
        f"checks-reconciliation-{CURRENT}-components"
    ) == (
        "Startsaldo: Ukendt "
        "Indtægter minus udgifter: 0,00 kr. "
        "Overførsler: 0,00 kr. "
        "Ukategoriseret ind: 0,00 kr. "
        "Ukategoriseret ud: 0,00 kr. "
        "Regulering ind: 0,00 kr. "
        "Regulering ud: 0,00 kr. "
        "Slutsaldo: Ukendt"
    )


def test_kontrol_shows_each_accounts_internal_residual_and_opening_gap(
    client: TestClient,
) -> None:
    # March opens 500 below February's close; May has no balances to compare.
    assert (
        kontrol(client).text_of(f"checks-reconciliation-{CURRENT}-residuals"),
        kontrol(client, month="2026-05").text_of(
            f"checks-reconciliation-{CURRENT}-residuals"
        ),
    ) == (
        (
            "Intern forskel: 0,00 kr. "
            "Slutsaldo forrige måned: 37.537,50 kr. "
            "Åbningsforskel: \N{MINUS SIGN}500,00 kr."
        ),
        (
            "Intern forskel: Ukendt "
            "Slutsaldo forrige måned: 52.087,50 kr. "
            "Åbningsforskel: Ukendt"
        ),
    )


def test_kontrol_says_a_zero_difference_does_not_prove_the_data_complete(
    client: TestClient,
) -> None:
    # Joint current's March difference is 0,00 kr., yet March is only partial.
    assert kontrol(client).text_of("checks-reconciliation-note") == (
        "En forskel på 0,00 kr. beviser ikke, at alle posteringer er "
        "importeret: saldiene kan bygge på de samme ufuldstændige posteringer."
    )


def test_kontrol_heads_each_reconciliation_with_its_own_unupgraded_coverage(
    client: TestClient,
) -> None:
    # Joint current's March difference is 0,00 kr. but stays partly covered.
    page = kontrol(client)

    assert (
        page.text_of(f"checks-reconciliation-{CURRENT}-title"),
        page.text_of(f"checks-reconciliation-{SAVINGS}-title"),
    ) == (
        "Joint current, marts 2026: delvist dækket",
        "Joint savings, marts 2026: fuldt dækket",
    )


def test_kontrol_lists_a_nonzero_opening_gap_first_linking_to_its_account(
    client: TestClient,
) -> None:
    # Only Joint current's March opening gap is nonzero; April has none.
    page = kontrol(client)
    line = "Joint current: Åbningsforskel \N{MINUS SIGN}500,00 kr. (se Detaljer)"
    link = parse_qs(
        urlsplit(
            page.attributes(f"checks-residual-{CURRENT}-opening-gap").get("href", "")
        ).query
    )

    assert (
        page.text_of("checks-residuals"),
        0 <= page.visible().find(line) < page.visible().find("Dækning:"),
        link.get("account"),
        link.get("month"),
        link.get("mode"),
        link.get("tab"),
        kontrol(client, month="2026-04").text_of("checks-residuals"),
    ) == (line, True, [CURRENT], ["2026-03"], ["advanced"], ["details"], None)


def test_a_nonzero_residuals_link_opens_the_full_detaljer_page_for_its_account(
    client: TestClient,
) -> None:
    # A plain link must land on a whole page, not the report fragment.
    href = kontrol(client).attributes(f"checks-residual-{CURRENT}-opening-gap")["href"]
    landed = client.get(href)
    page = read(landed.text)

    assert (
        landed.status_code,
        "<html" in landed.text,
        page.attributes("tab-details").get("aria-current"),
        page.checked("account"),
    ) == (200, True, "page", {CURRENT})


def test_kontrol_leaves_an_unknown_residual_out_of_the_top_list(
    client: TestClient,
) -> None:
    # May's residuals are unknown, which is neither zero nor a known gap.
    assert kontrol(client, month="2026-05").text_of("checks-residuals") is None


def test_kontrol_heads_the_residual_list_and_the_reconciliation_section(
    client: TestClient,
) -> None:
    # Heading navigation: month, then each section, then accounts below it.
    html = client.get("/report", params=KONTROL, headers={"HX-Request": "true"}).text
    page = read(html)

    assert (
        page.text_of("checks-residuals-title"),
        page.attributes("checks-residuals").get("aria-labelledby"),
        page.text_of("checks-reconciliation-title"),
        f'<h5 id="checks-reconciliation-{CURRENT}-title"' in html,
    ) == ("Forskelle at undersøge", "checks-residuals-title", "Afstemning", True)


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


def test_kontrol_shows_observed_money_and_counts_separately(client: TestClient) -> None:
    page = kontrol(client)

    assert (
        page.text_of("checks-unclassified"),
        page.text_of("checks-adjustments"),
        page.text_of("checks-transfers"),
    ) == (
        (
            "Ukategoriseret Ind: 0,00 kr. Ud: \N{MINUS SIGN}450,00 kr. "
            "Observerede transaktioner på de valgte konti: 1"
        ),
        (
            "Reguleringer Ind: 0,00 kr. Ud: 0,00 kr. "
            "Observerede transaktioner på de valgte konti: 0"
        ),
        (
            "Overførsler Ind: 0,00 kr. Ud: 0,00 kr. "
            "Observerede transaktioner på de valgte konti: 0"
        ),
    )
