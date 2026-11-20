# Copyright 2026 Therkel
"""The Enkel and Avanceret report navigation contract."""

from dataclasses import replace
from datetime import UTC, date, datetime
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

REFERENCE_DATE = "2026-05-14"
PINNED = {
    "publication": "1",
    "reference_date": REFERENCE_DATE,
    "account": [CURRENT, SAVINGS],
    "month": "2026-03",
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
        create_app(
            profile,
            clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC),
        ),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303
    return client


def test_fresh_visit_offers_only_the_working_modes_and_defaults_to_enkel_belob(
    client: TestClient,
) -> None:
    html = client.get("/").text
    page = read(html)

    assert (
        page.attributes("mode-control").get("role"),
        page.checked("mode"),
        page.hidden("tab"),
        page.hidden("comparison"),
        page.text_of("comparison-choice"),
        "Detaljer" in page.visible(),
        "Kontrol" in page.visible(),
        html.find('id="month"') < html.find('id="mode-control"'),
        html.find('id="mode-control"') < html.find('class="account-fieldset"'),
    ) == (
        "group",
        {"simple"},
        "overview",
        "amounts",
        "Beløb",
        False,
        False,
        True,
        True,
    )


def test_details_render_dated_balances_snapshots_and_public_transfer_evidence(
    client: TestClient,
) -> None:
    page = read(
        client.get(
            "/report",
            params={
                **PINNED,
                "account": [CURRENT],
                "month": "2026-01",
                "mode": "advanced",
                "tab": "details",
            },
            headers={"HX-Request": "true"},
        ).text
    )

    assert (
        page.attributes("report").get("data-mode"),
        page.attributes("report").get("data-tab"),
        page.attributes("tab-details").get("aria-current"),
        page.text_of("activity-evidence-joint-current"),
        page.text_of("activity-dated-balance-joint-current"),
        page.text_of("activity-monthly-snapshot-joint-current"),
        "Overførsel, parret med Joint savings" in page.visible(),
        page.attributes("income"),
    ) == (
        "advanced",
        "details",
        "page",
        "Gennem 08.05.2026",
        "21.557,50 kr. den 28.01.2026",
        ("Månedssnapshot: Åbning 400,00 kr.; lukning 21.557,50 kr.; delvist dækket."),
        True,
        {},
    )


def test_details_keep_a_null_dated_balance_separate_from_unknown_snapshot_value(
    profile: Profile,
    client: TestClient,
) -> None:
    january = next(
        transaction
        for transaction in RECORDS.transactions
        if transaction.transaction_id == "current-03"
    )
    earlier = next(
        transaction
        for transaction in RECORDS.transactions
        if transaction.transaction_id == "current-04"
    )
    latest = replace(
        earlier,
        transaction_id="current-null",
        transaction_date=date(2026, 2, 3),
        account_sequence=12,
        balance_after=None,
        balance_check="missing_balance",
    )
    february = ReportingMonth(2026, 2)
    snapshots = tuple(
        replace(snapshot, closing_balance=None)
        if snapshot.account_id == CURRENT and snapshot.month == february
        else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    records = replace(
        RECORDS,
        transactions=(january, earlier, latest),
        category_allocations=tuple(
            allocation
            for allocation in RECORDS.category_allocations
            if allocation.transaction_id in {"current-03", "current-04"}
        ),
        monthly_balances=snapshots,
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                records,
            ),
            RECIPE,
            CONFIGURATION,
        )

    page = read(
        client.get(
            "/report",
            params={
                **PINNED,
                "publication": "2",
                "account": [CURRENT],
                "month": "2026-02",
                "mode": "advanced",
                "tab": "details",
            },
            headers={"HX-Request": "true"},
        ).text
    )

    assert (
        page.text_of("activity-dated-balance-joint-current"),
        page.text_of("activity-monthly-snapshot-joint-current"),
        page.text_of("activity-earlier-observation-joint-current"),
    ) == (
        "Ukendt den 03.02.2026",
        (
            "Månedssnapshot: Åbning 21.557,50 kr.; lukning Ingen data endnu; "
            "delvist dækket."
        ),
        "21.557,50 kr. den 28.01.2026",
    )


def test_details_show_current_and_unsettled_closed_provisional_warnings(
    profile: Profile,
    client: TestClient,
) -> None:
    current = read(
        client.get(
            "/report",
            params={
                **PINNED,
                "account": [CURRENT],
                "month": "2026-05",
                "mode": "advanced",
                "tab": "details",
            },
            headers={"HX-Request": "true"},
        ).text
    )

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
    closed = read(
        client.get(
            "/report",
            params={
                **PINNED,
                "publication": "2",
                "account": [CURRENT],
                "month": "2026-04",
                "mode": "advanced",
                "tab": "details",
            },
            headers={"HX-Request": "true"},
        ).text
    )

    assert (
        current.text_of("provisional-label"),
        closed.text_of("provisional-label"),
        parse_qs(urlsplit(current.attributes("provisional-explanation")["href"]).query)[
            "tab"
        ],
        parse_qs(urlsplit(closed.attributes("provisional-explanation")["href"]).query)[
            "tab"
        ],
    ) == (
        "Foreløbige tal",
        "Foreløbige tal",
        ["details"],
        ["details"],
    )


def test_details_basic_explanation_returns_to_the_same_pinned_tab(
    client: TestClient,
) -> None:
    details = read(
        client.get(
            "/report",
            params={
                **PINNED,
                "month": "2026-03",
                "mode": "advanced",
                "tab": "details",
            },
            headers={"HX-Request": "true"},
        ).text
    )
    explanation_url = details.attributes("coverage-explanation")["href"]
    explanation = read(client.get(explanation_url).text)
    back_url = explanation.attributes("back-to-report")["href"]
    restored = read(client.get(back_url).text)

    assert (
        parse_qs(urlsplit(explanation_url).query)["tab"],
        parse_qs(urlsplit(back_url).query)["tab"],
        parse_qs(urlsplit(back_url).query)["account"],
        restored.attributes("report").get("data-tab"),
        restored.hidden("tab"),
    ) == (
        ["details"],
        ["details"],
        [CURRENT, SAVINGS],
        "details",
        "details",
    )


def test_full_get_and_htmx_agree_on_the_normalized_pinned_mode(
    client: TestClient,
) -> None:
    pinned = {
        **PINNED,
        "month": "2026-04",
        "mode": "advanced",
        "tab": "not-a-tab",
        "comparison": "not-a-comparison",
    }
    page = read(client.get("/", params=pinned).text)
    response = client.get(
        "/report",
        params={**pinned, "active_mode": "simple"},
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)
    expected = (
        "/?publication=1&reference_date=2026-05-14"
        f"&account={CURRENT}&account={SAVINGS}&month=2026-04"
        "&mode=advanced&tab=overview&comparison=amounts"
    )

    assert (
        page.checked("mode"),
        page.hidden("tab"),
        page.hidden("comparison"),
        page.attributes("overview").get("data-canonical-url"),
        response.status_code,
        response.headers.get("hx-push-url"),
        fragment.attributes("report").get("data-mode"),
        fragment.attributes("report").get("data-tab"),
        fragment.hidden("active_mode"),
        fragment.hidden("tab"),
    ) == (
        {"advanced"},
        "overview",
        "amounts",
        expected,
        200,
        expected,
        "advanced",
        "overview",
        "advanced",
        "overview",
    )


def test_explicit_details_to_enkel_switch_lands_on_overview_and_preserves_pin(
    client: TestClient,
) -> None:
    params = {
        **PINNED,
        "account": [CURRENT],
        "month": "2026-04",
        "active_mode": "advanced",
        "mode": "simple",
        "tab": "details",
    }
    page = read(client.get("/", params=params).text)
    response = client.get(
        "/report",
        params=params,
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)
    expected = (
        "/?publication=1&reference_date=2026-05-14"
        f"&account={CURRENT}&month=2026-04"
        "&mode=simple&tab=overview&comparison=amounts"
    )

    assert (
        page.checked("mode"),
        page.hidden("tab"),
        page.attributes("report").get("data-tab"),
        page.attributes("overview").get("data-canonical-url"),
        fragment.hidden("active_mode"),
        fragment.hidden("tab"),
        fragment.attributes("report").get("data-tab"),
        response.headers.get("hx-push-url"),
    ) == (
        {"simple"},
        "overview",
        "overview",
        expected,
        "simple",
        "overview",
        "overview",
        expected,
    )


def test_unavailable_details_response_keeps_the_requested_presentation_state(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            **PINNED,
            "publication": "999",
            "active_mode": "advanced",
            "mode": "advanced",
            "tab": "details",
        },
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)

    assert (
        fragment.text_of("report"),
        fragment.hidden("active_mode"),
        fragment.hidden("tab"),
        parse_qs(urlsplit(response.headers["hx-push-url"]).query)["tab"],
    ) == (
        "Disse tal findes ikke længere. Vis de nyeste tal",
        "advanced",
        "details",
        ["details"],
    )


def test_invalid_mode_and_tab_are_normalized_on_page_and_fragment(
    client: TestClient,
) -> None:
    invalid = {
        **PINNED,
        "mode": "expert",
        "tab": "details",
        "comparison": "percent",
    }
    page = read(client.get("/", params=invalid).text)
    fragment = read(
        client.get(
            "/report",
            params={**invalid, "active_mode": "advanced"},
            headers={"HX-Request": "true"},
        ).text
    )

    assert (
        page.checked("mode"),
        page.hidden("tab"),
        page.hidden("comparison"),
        fragment.attributes("report").get("data-mode"),
        fragment.attributes("report").get("data-tab"),
        fragment.hidden("active_mode"),
        fragment.hidden("tab"),
    ) == (
        {"simple"},
        "overview",
        "amounts",
        "simple",
        "overview",
        "simple",
        "overview",
    )


def test_invalid_and_unavailable_fragments_still_sync_advanced_presentation_state(
    client: TestClient,
) -> None:
    invalid_response = client.get(
        "/report",
        params={**PINNED, "month": "2026-07", "mode": "advanced"},
        headers={"HX-Request": "true"},
    )
    unavailable_response = client.get(
        "/report",
        params={**PINNED, "publication": "999", "mode": "advanced"},
        headers={"HX-Request": "true"},
    )
    invalid = read(invalid_response.text)
    unavailable = read(unavailable_response.text)

    assert (
        "Den valgte måned ligger uden for de måneder, der kan vælges."
        in invalid.visible(),
        "25.000,00 kr." in invalid.visible(),
        invalid.attributes("report").get("data-mode"),
        invalid.hidden("active_mode"),
        invalid.hidden("tab"),
        invalid.hidden("comparison"),
        unavailable.text_of("report"),
        "25.000,00 kr." in unavailable.visible(),
        unavailable.attributes("report").get("data-mode"),
        unavailable.hidden("active_mode"),
        unavailable.hidden("tab"),
        unavailable.hidden("comparison"),
        invalid_response.headers.get("hx-push-url"),
        unavailable_response.headers.get("hx-push-url"),
    ) == (
        True,
        False,
        None,
        "advanced",
        "overview",
        "amounts",
        "Disse tal findes ikke længere. Vis de nyeste tal",
        False,
        None,
        "advanced",
        "overview",
        "amounts",
        (
            "/?publication=1&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-07"
            "&mode=advanced&tab=overview&comparison=amounts"
        ),
        (
            "/?publication=999&reference_date=2026-05-14"
            f"&account={CURRENT}&account={SAVINGS}&month=2026-03"
            "&mode=advanced&tab=overview&comparison=amounts"
        ),
    )


def test_switching_while_empty_syncs_state_and_reselecting_keeps_advanced_overview(
    client: TestClient,
) -> None:
    empty = {
        **PINNED,
        "mode": "advanced",
        "active_mode": "simple",
    }
    empty["account"] = []
    prompt_response = client.get(
        "/report",
        params=empty,
        headers={"HX-Request": "true"},
    )
    prompt = read(prompt_response.text)
    expected_empty = (
        "/?publication=1&reference_date=2026-05-14&month=2026-03"
        "&mode=advanced&tab=overview&comparison=amounts"
    )

    reselection = client.get(
        "/report",
        params={
            **empty,
            "account": [CURRENT],
            "active_mode": "advanced",
        },
        headers={"HX-Request": "true"},
    )
    report = read(reselection.text)

    assert (
        prompt_response.status_code,
        prompt.text_of("report"),
        prompt.attributes("report"),
        prompt.hidden("active_mode"),
        prompt.hidden("tab"),
        prompt_response.headers.get("hx-push-url"),
        reselection.status_code,
        report.attributes("report").get("data-mode"),
        report.attributes("report").get("data-tab"),
        report.attributes("report").get("data-accounts"),
        report.attributes("report").get("data-month"),
    ) == (
        200,
        "Vælg mindst én konto.",
        {"id": "report"},
        "advanced",
        "overview",
        expected_empty,
        200,
        "advanced",
        "overview",
        CURRENT,
        "2026-03",
    )


def test_category_and_basic_explanation_returns_keep_advanced_pinned_state(
    client: TestClient,
) -> None:
    report = read(
        client.get(
            "/report",
            params={**PINNED, "month": "2026-04", "mode": "advanced"},
            headers={"HX-Request": "true"},
        ).text
    )
    category_url = report.attributes("category-link-rent")["href"]
    category = read(client.get(category_url).text)
    category_back = category.attributes("back-to-overview")["href"]
    restored = read(client.get(category_back).text)

    explanation_report = read(
        client.get(
            "/report",
            params={**PINNED, "mode": "advanced"},
            headers={"HX-Request": "true"},
        ).text
    )
    explanation_url = explanation_report.attributes("coverage-explanation")["href"]
    explanation = read(client.get(explanation_url).text)
    explanation_back = explanation.attributes("back-to-report")["href"]

    expected_mode = ["advanced"]
    expected_tab = ["overview"]
    expected_accounts = [CURRENT, SAVINGS]
    assert (
        parse_qs(urlsplit(category_url).query)["mode"],
        parse_qs(urlsplit(category_url).query)["tab"],
        parse_qs(urlsplit(category_url).query)["comparison"],
        parse_qs(urlsplit(category_url).query)["account"],
        parse_qs(urlsplit(category_back).query)["mode"],
        parse_qs(urlsplit(category_back).query)["month"],
        restored.checked("mode"),
        restored.attributes("report").get("data-mode"),
        parse_qs(urlsplit(explanation_url).query)["mode"],
        parse_qs(urlsplit(explanation_back).query)["mode"],
        parse_qs(urlsplit(explanation_back).query)["account"],
    ) == (
        expected_mode,
        expected_tab,
        ["amounts"],
        expected_accounts,
        expected_mode,
        ["2026-04"],
        {"advanced"},
        "advanced",
        expected_mode,
        expected_mode,
        expected_accounts,
    )


@pytest.mark.parametrize("tab", ["overview", "details"])
def test_advanced_mode_keeps_superseded_and_unavailable_publication_behavior(
    profile: Profile,
    client: TestClient,
    tab: str,
) -> None:
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                RECORDS,
            ),
            RECIPE,
            CONFIGURATION,
        )

    def fragment(publication: str) -> Page:
        return read(
            client.get(
                "/report",
                params={
                    **PINNED,
                    "publication": publication,
                    "mode": "advanced",
                    "tab": tab,
                },
                headers={"HX-Request": "true"},
            ).text
        )

    superseded = fragment("1")
    unavailable = fragment("999")

    assert (
        "Der findes nyere tal." in superseded.visible(),
        superseded.attributes("newer-figures").get("href"),
        superseded.attributes("report").get("data-mode"),
        superseded.attributes("report").get("data-tab"),
        superseded.hidden("tab"),
        unavailable.text_of("report"),
        unavailable.attributes("current-figures").get("href"),
        unavailable.hidden("tab"),
    ) == (
        True,
        "/",
        "advanced",
        tab,
        tab,
        "Disse tal findes ikke længere. Vis de nyeste tal",
        "/",
        tab,
    )
