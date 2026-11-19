# Copyright 2026 Therkel
"""The narrowed Enkel and Avanceret overview contract."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.gold import GoldResult
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


def test_advanced_mode_keeps_superseded_and_unavailable_publication_behavior(
    profile: Profile,
    client: TestClient,
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
        unavailable.text_of("report"),
        unavailable.attributes("current-figures").get("href"),
    ) == (
        True,
        "/",
        "advanced",
        "Disse tal findes ikke længere. Vis de nyeste tal",
        "/",
    )
