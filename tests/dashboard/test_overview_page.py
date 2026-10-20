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

from budget.dashboard import create_app, set_passphrase
from budget.gold import GoldResult
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.dashboard.pages import Page, read
from tests.gold.test_store import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

HOUSEHOLD_PHRASE = "correct horse battery staple"
# 00:30 on 1 June in Copenhagen, still 31 May in UTC.
JUST_AFTER_MIDNIGHT = datetime(2026, 5, 31, 22, 30, tzinfo=UTC)


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    profile = replace(
        make_test_profile(tmp_path),
        passphrase_file=tmp_path / "dashboard-passphrase",
    )
    migrate_gold(profile)
    set_passphrase(profile, HOUSEHOLD_PHRASE)
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
