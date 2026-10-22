# Copyright 2026 Therkel
"""The overview page: one pinned report context, resolved once per visit.

The rules are `report-contract.md` "ReportContext" and "Navigation and
Selection Transitions". The household's Gold holds the synthetic worked
example, published twice; the dashboard is driven in-process.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

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

# 00:30 on 1 June in Copenhagen, still 31 May in UTC.
JUST_AFTER_MIDNIGHT = datetime(2026, 5, 31, 22, 30, tzinfo=UTC)


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        for publication_id in (1, 2):
            published = replace(PUBLICATION, publication_id=publication_id)
            store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)
    return profile


@pytest.fixture
def client(profile: Profile) -> TestClient:
    client = TestClient(
        create_app(profile, clock=lambda: JUST_AFTER_MIDNIGHT), follow_redirects=False
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def test_the_overview_offers_a_way_to_log_out(client: TestClient) -> None:
    # On a shared device a reader must be able to end a 30-day login.
    page = read(client.get("/").text)
    logout = page.attributes("logout")

    assert (
        logout.get("method", "").lower(),
        logout.get("action"),
        page.text_of("logout"),
    ) == ("post", "/logout", "Log ud")


def test_a_fresh_visit_pins_the_current_publication_every_account_and_this_month(
    client: TestClient,
) -> None:
    page = read(client.get("/").text)

    # The month the form submits, labelled in Danish.
    assert (
        page.selected("month"),
        page.checked("account"),
        page.hidden("publication"),
        page.hidden("reference_date"),
    ) == ([("2026-06", "juni 2026")], {CURRENT, SAVINGS}, "2", "2026-06-01")


def test_a_report_fragment_repeats_the_context_it_answers(client: TestClient) -> None:
    # The page drops a fragment whose context is not the reader's selection now.
    # The pin is neither the current publication nor the clock's day, so only
    # a fragment that keeps the pin can repeat it; accounts come back sorted.
    response = client.get(
        "/report",
        params={
            "publication": "1",
            "reference_date": "2026-05-14",
            "account": [SAVINGS, CURRENT],
            "month": "2026-04",
        },
        headers={"HX-Request": "true"},
    )

    echoed = read(response.text).attributes("report")
    assert (
        response.status_code,
        echoed.get("data-publication"),
        echoed.get("data-reference-date"),
        echoed.get("data-accounts"),
        echoed.get("data-month"),
    ) == (200, "1", "2026-05-14", f"{CURRENT} {SAVINGS}", "2026-04")


def test_a_report_of_a_superseded_publication_offers_the_newer_figures(
    client: TestClient,
) -> None:
    def fragment(publication: str) -> Page:
        response = client.get(
            "/report",
            params={
                "publication": publication,
                "reference_date": "2026-06-01",
                "account": [CURRENT],
                "month": "2026-04",
            },
            headers={"HX-Request": "true"},
        )
        return read(response.text)

    # Publication 2 is current; a page pinned to 1 keeps reading 1, and says so.
    superseded, current = fragment("1"), fragment("2")

    # The reload is a named link, so a screen reader can say where it goes.
    assert (
        "Der findes nyere tal." in superseded.visible(),
        superseded.attributes("newer-figures").get("href"),
        superseded.text_of("newer-figures"),
        "Der findes nyere tal." in current.visible(),
        current.attributes("newer-figures"),
    ) == (True, "/", "Hent de nyeste tal", False, {})


def test_a_page_opened_with_a_pinned_selection_keeps_it(client: TestClient) -> None:
    # The page's own form submits here, and back or forward reopens it: the pin
    # and the selection come from the address, never from the clock or Gold.
    page = read(
        client.get(
            "/",
            params={
                "publication": "1",
                "reference_date": "2026-05-14",
                "account": [SAVINGS],
                "month": "2026-04",
            },
        ).text
    )

    # The months on offer end at the pinned date's month, not today's.
    assert (
        page.hidden("publication"),
        page.hidden("reference_date"),
        page.checked("account"),
        page.selected("month"),
        page.offered("month")[-1],
    ) == ("1", "2026-05-14", {SAVINGS}, [("2026-04", "april 2026")], "2026-05")


def test_an_invalid_selection_is_explained_naming_every_rule_it_breaks(
    client: TestClient,
) -> None:
    # July lies after the pinned date's month, the last one that can be chosen,
    # and the second account is not in the publication.
    response = client.get(
        "/report",
        params={
            "publication": "2",
            "reference_date": "2026-06-01",
            "account": [CURRENT, "closed-current"],
            "month": "2026-07",
        },
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)

    # A failure is shown, never a report: it echoes no context to render.
    assert (
        response.status_code,
        "Den valgte måned ligger uden for de måneder, der kan vælges."
        in fragment.visible(),
        "Kontoen closed-current findes ikke i disse tal." in fragment.visible(),
        fragment.attributes("report").get("data-month"),
    ) == (200, True, True, None)


def test_an_empty_account_selection_is_a_prompt_not_a_report(
    client: TestClient,
) -> None:
    # A form whose account boxes are all unticked sends no `account` at all.
    response = client.get(
        "/report",
        params={
            "publication": "2",
            "reference_date": "2026-06-01",
            "month": "2026-05",
        },
        headers={"HX-Request": "true"},
    )
    fragment = read(response.text)

    assert (
        response.status_code,
        fragment.text_of("report"),
        fragment.attributes("report").get("data-month"),
    ) == (200, "Vælg mindst én konto.", None)


def test_a_page_opened_with_no_accounts_selected_keeps_them_unticked(
    client: TestClient,
) -> None:
    # A pinned address with no `account` is an empty selection, not a fresh
    # visit: the boxes stay unticked and the reader is asked to choose.
    page = read(
        client.get(
            "/",
            params={
                "publication": "2",
                "reference_date": "2026-06-01",
                "month": "2026-05",
            },
        ).text
    )

    # Every account is still offered, so the reader can choose again.
    assert (
        page.choices("account"),
        page.checked("account"),
        page.text_of("report"),
    ) == ({CURRENT, SAVINGS}, set(), "Vælg mindst én konto.")


def test_with_nothing_published_the_page_says_so_instead_of_reporting(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(dashboard_profile(tmp_path), clock=lambda: JUST_AFTER_MIDNIGHT),
        follow_redirects=False,
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})

    response = client.get("/")
    page = read(response.text)

    # Absence is said in words, never shown as an empty or zero report.
    assert (
        response.status_code,
        page.text_of("report"),
        page.choices("account"),
    ) == (200, "Der er endnu ingen tal at vise.", set())


def test_a_pin_to_a_deleted_publication_offers_the_current_one_explicitly(
    client: TestClient, profile: Profile
) -> None:
    # A third build makes 3 current and keeps 2; publication 1's result is gone.
    with GoldStore(profile) as store:
        third = replace(PUBLICATION, publication_id=3)
        store.publish(GoldResult(third, RECORDS), RECIPE, CONFIGURATION)
    pin = {
        "publication": "1",
        "reference_date": "2026-05-14",
        "account": [CURRENT],
        "month": "2026-04",
    }
    # Back or forward to the old page, and a fragment it asks for.
    restored = read(client.get("/", params=pin).text)
    fragment = read(
        client.get("/report", params=pin, headers={"HX-Request": "true"}).text
    )

    # Never the current figures in its place: the reader chooses to go there.
    expected = ("Disse tal findes ikke længere. Vis de nyeste tal", "/")
    assert [
        (page.text_of("report"), page.attributes("current-figures").get("href"))
        for page in (restored, fragment)
    ] == [expected, expected]


def test_household_figures_are_never_kept_in_a_cache(client: TestClient) -> None:
    pin = {
        "publication": "2",
        "reference_date": "2026-06-01",
        "account": [CURRENT],
        "month": "2026-05",
    }
    htmx = {"HX-Request": "true"}
    page = client.get("/")
    fragment = client.get("/report", params=pin, headers=htmx)
    refusal = client.get("/report", params={**pin, "month": "2026-07"}, headers=htmx)

    # A shared or back-button cache would keep private figures after logout,
    # and a refusal still names the household's accounts and choices.
    assert [
        response.headers.get("cache-control") for response in (page, fragment, refusal)
    ] == ["no-store"] * 3


def test_a_page_shows_the_report_for_its_own_selection(client: TestClient) -> None:
    # Back or forward reopens a page; it must say what its report says,
    # without waiting for a script to fetch the region.
    pin = {
        "publication": "1",
        "reference_date": "2026-05-14",
        "account": [CURRENT],
        "month": "2026-04",
    }
    superseded = read(client.get("/", params=pin).text)
    out_of_range = read(client.get("/", params={**pin, "month": "2026-07"}).text)

    assert (
        "Der findes nyere tal." in (superseded.text_of("report") or ""),
        "Den valgte måned ligger uden for de måneder, der kan vælges."
        in (out_of_range.text_of("report") or ""),
    ) == (True, True)


def test_a_month_that_is_not_a_month_is_explained_not_an_error(
    client: TestClient,
) -> None:
    # A hand-edited or truncated address names no month that can be chosen.
    explained = []
    for month in ("2026-13", "maj"):
        response = client.get(
            "/report",
            params={
                "publication": "2",
                "reference_date": "2026-06-01",
                "account": [CURRENT],
                "month": month,
            },
            headers={"HX-Request": "true"},
        )
        explained.append(
            (
                response.status_code,
                "Den valgte måned ligger uden for de måneder, der kan vælges."
                in response.text,
            )
        )

    assert explained == [(200, True), (200, True)]


def test_a_report_fetched_in_place_moves_the_address_to_its_own_page(
    client: TestClient,
) -> None:
    # Back and forward then reopen the page for each selection the reader made.
    response = client.get(
        "/report",
        params={
            "publication": "2",
            "reference_date": "2026-06-01",
            "account": [SAVINGS, CURRENT],
            "month": "2026-05",
        },
        headers={"HX-Request": "true"},
    )

    assert response.headers.get("hx-push-url") == (
        "/?publication=2&reference_date=2026-06-01"
        f"&account={CURRENT}&account={SAVINGS}&month=2026-05"
    )


def test_text_from_the_address_is_shown_as_text_never_run_as_markup(
    client: TestClient,
) -> None:
    # A crafted link names an account that is really markup, once as an
    # element and once breaking out of an attribute.
    crafted = (
        '"><script id="injected">alert(1)</script>',
        '" id="injected" onmouseover="alert(1)',
    )
    pages = []
    for account in crafted:
        response = client.get(
            "/report",
            params={
                "publication": "2",
                "reference_date": "2026-06-01",
                "account": [account],
                "month": "2026-05",
            },
            headers={"HX-Request": "true"},
        )
        fragment = read(response.text)
        pages.append(
            (
                fragment.attributes("injected"),
                f"Kontoen {account} findes ikke i disse tal." in fragment.visible(),
            )
        )

    assert pages == [({}, True), ({}, True)]


@pytest.mark.parametrize(
    "params",
    [
        {"publication": "abc", "reference_date": "2026-06-01", "month": "2026-05"},
        {"publication": "2", "reference_date": "not-a-date", "month": "2026-05"},
        {"publication": "2", "reference_date": "2026-13-45", "month": "2026-05"},
    ],
)
def test_a_malformed_address_is_explained_in_danish_not_as_json(
    client: TestClient, params: dict[str, str]
) -> None:
    # htmx swaps only a 2xx, so the fragment answers 200; the page is a 400.
    fragment = client.get(
        "/report",
        params={**params, "account": [CURRENT]},
        headers={"HX-Request": "true"},
    )
    page = client.get("/", params=params)

    assert (
        fragment.status_code,
        fragment.headers["content-type"].split(";")[0],
        "Adressen er ikke gyldig." in read(fragment.text).visible(),
        read(fragment.text).attributes("report").get("role"),
        page.status_code,
        page.headers["content-type"].split(";")[0],
        "Adressen er ikke gyldig." in read(page.text).visible(),
        read(page.text).attributes("current-figures").get("href"),
    ) == (200, "text/html", True, None, 400, "text/html", True, "/")


def test_the_report_is_swapped_inside_one_persistent_live_region(
    client: TestClient,
) -> None:
    # A screen reader announces changes to a live region that was already on the
    # page; one swapped in with its content is often missed. So the form swaps
    # the inside of a wrapper that stays, and a fragment has no live role of
    # its own to announce twice.
    page = read(client.get("/").text)
    region = page.attributes("report-region")
    form = page.attributes("selection")
    fragment = client.get(
        "/report",
        params={"publication": "2", "reference_date": "2026-06-01", "month": "2026-05"},
        headers={"HX-Request": "true"},
    )

    assert (
        region.get("aria-live"),
        form.get("hx-get"),
        form.get("hx-target"),
        form.get("hx-swap"),
        "report" in page.elements,
        read(fragment.text).attributes("report").get("role"),
    ) == ("polite", "/report", "#report-region", "innerHTML", True, None)


def test_the_overview_loads_htmx_and_its_form_asks_for_the_report(
    client: TestClient,
) -> None:
    # Without the script the form still reloads the page, so a missing script
    # or a form wired to the wrong address would go unnoticed.
    html = client.get("/").text
    form = read(html).attributes("selection")

    assert (
        '<script src="/static/htmx.min.js"' in html,
        client.get("/static/htmx.min.js").status_code,
        form.get("hx-get"),
        form.get("hx-target"),
    ) == (True, 200, "/report", "#report-region")
