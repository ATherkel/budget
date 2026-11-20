# Copyright 2026 Therkel
"""Kontrol rendering and its navigation into and out of the report."""

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

REFERENCE_DATE = "2026-05-14"
PINNED = {
    "publication": str(PUBLICATION.publication_id),
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
    assert (
        client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE}).status_code == 303
    )
    return client


def _report(client: TestClient, **changes: str) -> Page:
    response = client.get(
        "/report",
        params={**PINNED, "mode": "advanced", "tab": "checks", **changes},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def _origin(
    mode: str = "simple",
    tab: str = "overview",
    accounts: tuple[str, ...] = (CURRENT, SAVINGS),
    month: str = "2026-03",
) -> str:
    query = (
        f"publication={PUBLICATION.publication_id}&reference_date={REFERENCE_DATE}"
        + "".join(f"&account={account}" for account in accounts)
        + f"&month={month}&mode={mode}&tab={tab}&comparison=amounts"
    )
    return f"/?{query}"


def test_kontrol_renders_diagnostics_without_upgrading_partial_coverage(
    client: TestClient,
) -> None:
    page = _report(client)

    assert (
        page.attributes("report").get("data-tab"),
        page.attributes("tab-checks").get("aria-current"),
        page.text_of("diagnostics-coverage"),
        page.text_of("diagnostics-incomplete-months"),
        page.text_of("diagnostics-evidence"),
        page.text_of("diagnostics-unclassified"),
        page.text_of("diagnostics-adjustments"),
        page.text_of("diagnostics-reconciliation-joint-current-residual"),
        page.text_of("diagnostics-reconciliation-joint-current-opening-gap"),
        page.text_of("diagnostics-reconciliation-joint-current-coverage"),
        "Tallene er afstemt" in page.visible(),
    ) == (
        "checks",
        "page",
        "Dækning: delvist dækket.",
        "Joint current, marts 2026: delvist dækket.",
        "Joint current: Gennem 08.05.2026 Joint savings: Gennem 08.05.2026",
        ("Ukategoriseret: ind 0,00 kr.; ud \N{MINUS SIGN}450,00 kr.; 1 postering."),
        "Reguleringer: ind 0,00 kr.; ud 0,00 kr.; 0 posteringer.",
        "Beregnet afvigelse: 0,00 kr.",
        "Åbningsforskel mod forrige lukning: \N{MINUS SIGN}500,00 kr.",
        "Dækning: delvist dækket.",
        False,
    )


def test_kontrol_names_selected_transfer_legs_and_their_public_pairing(
    client: TestClient,
) -> None:
    page = _report(client, month="2026-01")

    assert page.text_of("diagnostics-transfer-summary") == (
        "Overførsler: ind +3.000,00 kr.; ud \N{MINUS SIGN}3.000,00 kr.; "
        "2 valgte ben; 2 parrede; 0 ensidige."
    )


def test_kontrol_keeps_missing_balance_endpoints_unknown(
    profile: Profile,
    client: TestClient,
) -> None:
    march = next(
        snapshot
        for snapshot in RECORDS.monthly_balances
        if snapshot.account_id == CURRENT and snapshot.month == ReportingMonth(2026, 3)
    )
    balances = tuple(
        replace(snapshot, opening_balance=None) if snapshot == march else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                replace(RECORDS, monthly_balances=balances),
            ),
            RECIPE,
            CONFIGURATION,
        )

    page = _report(client, publication="2")
    coverage = page.text_of("diagnostics-reconciliation-joint-current-coverage")

    assert (
        page.text_of("diagnostics-reconciliation-joint-current-residual"),
        page.text_of("diagnostics-reconciliation-joint-current-opening-gap"),
        coverage,
        "0,00 kr."
        in (page.text_of("diagnostics-reconciliation-joint-current-residual") or ""),
    ) == (
        "Beregnet afvigelse: Ukendt.",
        "Åbningsforskel mod forrige lukning: Ukendt.",
        "Dækning: delvist dækket.",
        False,
    )


def test_kontrol_without_evidence_does_not_turn_observations_into_zero(
    client: TestClient,
) -> None:
    page = _report(
        client,
        month="2026-06",
        reference_date="2026-06-03",
    )

    assert (
        page.text_of("diagnostics-coverage"),
        page.text_of("diagnostics-unclassified"),
        page.text_of("diagnostics-adjustments"),
        page.text_of("diagnostics-transfer-summary"),
        page.text_of("diagnostics-reconciliation-joint-current-residual"),
        page.text_of("diagnostics-reconciliation-joint-current-opening-gap"),
    ) == (
        "Dækning: ingen data.",
        "Ukategoriseret: ukendt.",
        "Reguleringer: ukendt.",
        "Overførsler: ukendt.",
        "Beregnet afvigelse: Ukendt.",
        "Åbningsforskel mod forrige lukning: Ukendt.",
    )


def test_kontrol_explains_current_and_unsettled_closed_months(
    profile: Profile,
    client: TestClient,
) -> None:
    current = _report(client, month="2026-05")
    april = ReportingMonth(2026, 4)
    balances = tuple(
        replace(snapshot, late_bookings_settled=False)
        if snapshot.account_id == CURRENT and snapshot.month == april
        else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    with GoldStore(profile) as store:
        store.publish(
            GoldResult(
                replace(PUBLICATION, publication_id=2),
                replace(RECORDS, monthly_balances=balances),
            ),
            RECIPE,
            CONFIGURATION,
        )
    unsettled = _report(client, publication="2", month="2026-04")

    assert (
        current.text_of("diagnostics-provisional"),
        unsettled.text_of("diagnostics-provisional"),
    ) == (
        (
            "Foreløbigt: maj 2026 er indeværende måned, så der kan "
            "stadig komme posteringer. Sene bogføringer kan stadig komme fra "
            "Joint current og Joint savings."
        ),
        ("Foreløbigt: Sene bogføringer kan stadig komme fra Joint current."),
    )


def test_trust_notes_offer_basic_explanation_and_distinct_targeted_kontrol(
    client: TestClient,
) -> None:
    report = read(
        client.get(
            "/report",
            params={**PINNED, "mode": "simple"},
            headers={"HX-Request": "true"},
        ).text
    )
    basic_url = report.attributes("coverage-explanation")["href"]
    targeted_url = report.attributes("coverage-control")["href"]
    basic = read(client.get(basic_url).text)
    targeted = read(client.get(targeted_url).text)

    assert (
        urlsplit(basic_url).path,
        basic.text_of("explanation-coverage"),
        report.attributes("coverage-control").get("class"),
        parse_qs(urlsplit(targeted_url).query)["mode"],
        parse_qs(urlsplit(targeted_url).query)["tab"],
        parse_qs(urlsplit(targeted_url).query)["return_to"],
        targeted.attributes("report").get("data-tab"),
        targeted.attributes("return-from-control").get("href"),
    ) == (
        "/explanation",
        "Joint current, marts 2026: kun en del af måneden er dækket.",
        "control-link",
        ["advanced"],
        ["checks"],
        [_origin()],
        "checks",
        _origin(),
    )


def test_enkel_keeps_ind_out_without_diagnostic_counts_or_reconciliation(
    client: TestClient,
) -> None:
    page = read(
        client.get(
            "/report",
            params={**PINNED, "mode": "simple"},
            headers={"HX-Request": "true"},
        ).text
    )

    assert (
        page.text_of("unclassified-in"),
        page.text_of("unclassified-out"),
        page.attributes("diagnostics-unclassified"),
        page.attributes("tab-checks"),
        page.attributes("diagnostics-reconciliation-joint-current-residual"),
        page.attributes("diagnostics-adjustments"),
    ) == ("0,00 kr.", "\N{MINUS SIGN}450,00 kr.", {}, {}, {}, {})


@pytest.mark.parametrize(
    "return_to",
    [
        "https://example.invalid/",
        "//example.invalid/",
        r"/\example.invalid/",
        "/%5Cexample.invalid/",
        "/%2F%2Fexample.invalid/",
        "/not-a-dashboard",
        "/category?" + _origin()[2:],
        (
            "/?publication=1&reference_date=2026-05-14&account=x&month=2026-03"
            "&mode=simple&tab=overview&comparison=amounts&extra=1"
        ),
        "/?publication=1\r\nreference_date=2026-05-14",
        (
            "/?publication=1&reference_date=2026-05-14"
            "&account=joint%0Dcurrent&month=2026-03"
            "&mode=simple&tab=overview&comparison=amounts"
        ),
    ],
)
def test_unsafe_return_destinations_fall_back_to_the_pinned_overview(
    client: TestClient,
    return_to: str,
) -> None:
    page = read(
        client.get(
            "/",
            params={
                **PINNED,
                "mode": "advanced",
                "tab": "checks",
                "return_to": return_to,
            },
        ).text
    )

    assert (
        page.attributes("report").get("data-tab"),
        page.attributes("return-from-control").get("href"),
    ) == ("checks", _origin())


def test_htmx_unsafe_return_destination_is_replaced_before_push(
    client: TestClient,
) -> None:
    response = client.get(
        "/report",
        params={
            **PINNED,
            "mode": "advanced",
            "active_mode": "advanced",
            "tab": "checks",
            "return_to": "https://example.invalid/",
        },
        headers={"HX-Request": "true"},
    )
    page = read(response.text)
    pushed = parse_qs(urlsplit(response.headers["hx-push-url"]).query)

    assert (
        "example.invalid" in response.headers["hx-push-url"],
        page.attributes("return-from-control").get("href"),
        page.hidden("return_to"),
        pushed["return_to"],
    ) == (False, _origin(), _origin(), [_origin()])


def test_checks_keeps_a_valid_detail_origin_and_basic_explanation_return(
    client: TestClient,
) -> None:
    origin = _origin("advanced", "details", (CURRENT,), "2026-04")
    checks = read(
        client.get(
            "/",
            params={
                **PINNED,
                "account": [CURRENT],
                "month": "2026-04",
                "mode": "advanced",
                "tab": "checks",
                "return_to": origin,
            },
        ).text
    )
    explanation_url = checks.attributes("checks-basic-explanation")["href"]
    explanation = read(client.get(explanation_url).text)
    back_url = explanation.attributes("back-to-report")["href"]
    back_query = parse_qs(urlsplit(back_url).query)

    assert (
        checks.attributes("return-from-control").get("href"),
        parse_qs(urlsplit(explanation_url).query)["tab"],
        parse_qs(urlsplit(explanation_url).query)["return_to"],
        back_query["tab"],
        back_query["return_to"],
    ) == (
        origin,
        ["checks"],
        [origin],
        ["checks"],
        [origin],
    )


def test_checks_preserves_a_valid_category_detail_origin(
    client: TestClient,
) -> None:
    origin = (
        _origin("advanced", "overview", (CURRENT, SAVINGS), "2026-04").replace(
            "/?", "/category?", 1
        )
        + "&category=rent&scope=year_to_date"
    )
    page = read(
        client.get(
            "/",
            params={
                **PINNED,
                "month": "2026-04",
                "mode": "advanced",
                "tab": "checks",
                "return_to": origin,
            },
        ).text
    )

    assert page.attributes("return-from-control").get("href") == origin


@pytest.mark.parametrize(
    ("shortcut", "accounts"),
    [
        ("accounts-all", [CURRENT, SAVINGS]),
        ("accounts-none", []),
        ("only-joint-current", [CURRENT]),
    ],
)
def test_no_script_account_shortcuts_keep_a_targeted_return_origin(
    client: TestClient,
    shortcut: str,
    accounts: list[str],
) -> None:
    origin = _origin()
    page = read(
        client.get(
            "/",
            params={
                **PINNED,
                "mode": "advanced",
                "tab": "checks",
                "return_to": origin,
            },
        ).text
    )
    shortcut_url = page.attributes(shortcut)["href"]
    followed = read(client.get(shortcut_url).text)
    query = parse_qs(urlsplit(shortcut_url).query)

    assert (
        query.get("account", []),
        query["tab"],
        query["return_to"],
        followed.hidden("return_to"),
    ) == (
        accounts,
        ["checks"],
        [origin],
        origin,
    )


@pytest.mark.parametrize(
    ("mode", "tab"),
    [("simple", "overview"), ("advanced", "details")],
)
def test_basic_explanation_round_trip_keeps_targeted_origin(
    client: TestClient,
    mode: str,
    tab: str,
) -> None:
    origin = _origin(mode, tab)
    origin_page = read(client.get(origin).text)
    target_url = origin_page.attributes("coverage-control")["href"]
    checks = read(client.get(target_url).text)
    explanation_url = checks.attributes("checks-basic-explanation")["href"]
    explanation = read(client.get(explanation_url).text)
    back_url = explanation.attributes("back-to-report")["href"]
    checks_again = read(client.get(back_url).text)
    return_url = checks_again.attributes("return-from-control")["href"]
    returned = read(client.get(return_url).text)

    assert (
        parse_qs(urlsplit(explanation_url).query)["return_to"],
        parse_qs(urlsplit(back_url).query)["return_to"],
        return_url,
        returned.attributes("report").get("data-mode"),
        returned.attributes("report").get("data-tab"),
    ) == (
        [origin],
        [origin],
        origin,
        mode,
        tab,
    )


@pytest.mark.parametrize(
    "return_to",
    [
        "https://example.invalid/",
        "/%5Cexample.invalid/",
        (
            "/?publication=1&reference_date=2026-05-14"
            "&account=joint%0Dcurrent&month=2026-03"
            "&mode=simple&tab=overview&comparison=amounts"
        ),
    ],
)
def test_explanation_replaces_a_hostile_return_with_one_safe_origin(
    client: TestClient,
    return_to: str,
) -> None:
    explanation = read(
        client.get(
            "/explanation",
            params={
                **PINNED,
                "mode": "advanced",
                "tab": "checks",
                "return_to": return_to,
            },
        ).text
    )
    back_url = explanation.attributes("back-to-report")["href"]
    back_query = parse_qs(urlsplit(back_url).query)
    checks = read(client.get(back_url).text)
    origin = checks.attributes("return-from-control")["href"]
    origin_query = parse_qs(urlsplit(origin).query)

    assert (
        back_query["return_to"],
        origin,
        "return_to" in origin_query,
    ) == ([_origin()], _origin(), False)


def test_valid_explanation_origin_does_not_create_a_nested_return_chain(
    client: TestClient,
) -> None:
    origin = _origin("advanced", "details")
    explanation = read(
        client.get(
            "/explanation",
            params={
                **PINNED,
                "mode": "advanced",
                "tab": "checks",
                "return_to": origin,
            },
        ).text
    )
    back_url = explanation.attributes("back-to-report")["href"]
    checks = read(client.get(back_url).text)
    returned_origin = checks.attributes("return-from-control")["href"]

    assert returned_origin == origin
    assert "return_to" not in parse_qs(urlsplit(returned_origin).query)


def test_checks_keeps_the_tab_when_accounts_or_month_change(
    client: TestClient,
) -> None:
    origin = _origin("simple")
    response = client.get(
        "/report",
        params={
            **PINNED,
            "account": [CURRENT],
            "month": "2026-04",
            "mode": "advanced",
            "active_mode": "advanced",
            "tab": "checks",
            "return_to": origin,
        },
        headers={"HX-Request": "true"},
    )
    page = read(response.text)
    pushed = parse_qs(urlsplit(response.headers["hx-push-url"]).query)

    assert (
        page.attributes("report").get("data-tab"),
        page.hidden("tab"),
        page.hidden("return_to"),
        pushed["tab"],
        pushed["return_to"],
        pushed["account"],
        pushed["month"],
    ) == (
        "checks",
        "checks",
        origin,
        ["checks"],
        [origin],
        [CURRENT],
        ["2026-04"],
    )


@pytest.mark.parametrize("request_source", ["ordinary", "htmx"])
def test_kontrol_to_enkel_switch_returns_to_overview(
    client: TestClient,
    request_source: str,
) -> None:
    params = {
        **PINNED,
        "mode": "simple",
        "active_mode": "advanced",
        "tab": "checks",
    }
    if request_source == "ordinary":
        page = read(client.get("/", params=params).text)
        observed = (
            page.attributes("report").get("data-mode"),
            page.attributes("report").get("data-tab"),
            page.hidden("tab"),
        )
    else:
        response = client.get(
            "/report",
            params=params,
            headers={"HX-Request": "true"},
        )
        page = read(response.text)
        observed = (
            page.attributes("report").get("data-mode"),
            page.attributes("report").get("data-tab"),
            page.hidden("tab"),
        )

    assert observed == ("simple", "overview", "overview")
