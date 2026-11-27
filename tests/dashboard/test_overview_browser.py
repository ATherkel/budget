# Copyright 2026 Therkel
"""Real-browser dashboard behavior that HTTP response assertions cannot prove."""

import os
import re
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Locator, Page, Route, expect, sync_playwright

from budget.dashboard import create_app
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from budget.profiles import Profile
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS

NOW = datetime(2026, 5, 31, 22, 30, tzinfo=UTC)


@dataclass(frozen=True)
class BrowserDashboard:
    """A live dashboard and the synthetic profile behind it."""

    url: str
    profile: Profile


@pytest.fixture
def dashboard(tmp_path: Path) -> Iterator[BrowserDashboard]:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        for publication_id in (1, 2):
            published = replace(PUBLICATION, publication_id=publication_id)
            store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)

    socket_number = socket.socket()
    socket_number.bind(("127.0.0.1", 0))
    port = int(socket_number.getsockname()[1])
    socket_number.close()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(profile, clock=lambda: NOW),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        pytest.fail("the synthetic dashboard server did not start")
    try:
        yield BrowserDashboard(f"http://127.0.0.1:{port}", profile)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            pytest.fail("the synthetic dashboard server did not stop")


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        chrome = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            yield chrome
        finally:
            chrome.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    screen = context.new_page()
    try:
        yield screen
    finally:
        context.close()


def log_in(page: Page, dashboard: BrowserDashboard) -> None:
    """Log in through the real form and wait for the overview."""
    page.goto(f"{dashboard.url}/login")
    page.get_by_label("Adgangskode").fill(HOUSEHOLD_PHRASE)
    page.get_by_role("button", name="Log ind").click()
    expect(page.get_by_role("heading", name="Oversigt")).to_be_visible()
    page.wait_for_function("window.htmx !== undefined")
    page.wait_for_function(
        "location.pathname === '/' && location.search.includes('publication=')"
    )


def test_back_after_a_new_publication_restores_the_initially_opened_build(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    expect(page.locator('input[name="publication"]')).to_have_value("2")

    savings = page.get_by_role("checkbox", name="Joint savings")
    savings.uncheck()
    page.wait_for_function(
        "location.search.includes('publication=2')"
        " && location.search.includes('account=joint-current')"
        " && !location.search.includes('account=joint-savings')"
    )
    with GoldStore(dashboard.profile) as store:
        published = replace(PUBLICATION, publication_id=3)
        store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)

    page.go_back()
    expect(page.locator('input[name="publication"]')).to_have_value("2")


def _choose_view(page: Page, mode: str, tab: str) -> None:
    if mode == "advanced":
        advanced = page.get_by_role("radio", name="Avanceret")
        advanced.focus()
        page.keyboard.press("Space")
        if tab == "details":
            page.get_by_role("link", name="Detaljer").click()
    expect(page.locator("#report")).to_have_attribute("data-mode", mode)
    expect(page.locator("#report")).to_have_attribute("data-tab", tab)


@pytest.mark.parametrize(
    ("mode", "tab"),
    [
        ("simple", "overview"),
        ("advanced", "details"),
    ],
)
def test_empty_selection_survives_reload_back_and_forward(
    page: Page,
    dashboard: BrowserDashboard,
    mode: str,
    tab: str,
) -> None:
    log_in(page, dashboard)
    _choose_view(page, mode, tab)
    current = page.get_by_role("checkbox", name="Joint current")
    savings = page.get_by_role("checkbox", name="Joint savings")
    current.uncheck()
    savings.uncheck()
    page.wait_for_function("!location.search.includes('account=')")
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")

    page.reload()
    expect(current).not_to_be_checked()
    expect(savings).not_to_be_checked()
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page).to_have_url(
        re.compile(
            r"/\?publication=2&reference_date=2026-06-01&month=2026-06"
            rf"&mode={mode}&tab={tab}&comparison=amounts$"
        )
    )

    current.check()
    page.wait_for_function("location.search.includes('account=joint-current')")
    expect(current).to_be_checked()

    page.go_back()
    expect(current).not_to_be_checked()
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page).to_have_url(
        re.compile(
            r"/\?publication=2&reference_date=2026-06-01&month=2026-06"
            rf"&mode={mode}&tab={tab}&comparison=amounts$"
        )
    )

    page.go_forward()
    expect(current).to_be_checked()
    expect(savings).not_to_be_checked()


def test_only_ticks_only_its_account_and_updates_the_report_in_place(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    # Start with savings unticked, so "kun" has to tick it as well.
    page.get_by_label("Joint savings").uncheck()
    page.wait_for_function("!location.search.includes('account=joint-savings')")
    # A full page load would forget this mark.
    page.evaluate("window.stillThisPage = true")

    page.locator("#only-joint-savings").click()

    expect(page.locator("#report")).to_have_attribute("data-accounts", "joint-savings")
    expect(page.get_by_label("Joint current")).not_to_be_checked()
    expect(page.get_by_label("Joint savings")).to_be_checked()
    expect(page).to_have_url(
        re.compile(
            r"/\?publication=2&reference_date=2026-06-01"
            r"&account=joint-savings&month=2026-06"
            r"&mode=simple&tab=overview&comparison=amounts$"
        )
    )
    assert page.evaluate("window.stillThisPage === true"), "the page was reloaded"


def test_none_and_all_change_every_box_in_place_and_move_the_address(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    # A full page load would forget this mark.
    page.evaluate("window.stillThisPage = true")

    page.locator("#accounts-none").click()
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page.get_by_label("Joint current")).not_to_be_checked()
    expect(page.get_by_label("Joint savings")).not_to_be_checked()
    expect(page).to_have_url(
        re.compile(
            r"/\?publication=2&reference_date=2026-06-01&month=2026-06"
            r"&mode=simple&tab=overview&comparison=amounts$"
        )
    )

    page.locator("#accounts-all").click()
    expect(page.locator("#report")).to_have_attribute(
        "data-accounts", "joint-current joint-savings"
    )
    expect(page.get_by_label("Joint current")).to_be_checked()
    expect(page.get_by_label("Joint savings")).to_be_checked()
    expect(page).to_have_url(
        re.compile(
            r"/\?publication=2&reference_date=2026-06-01"
            r"&account=joint-current&account=joint-savings&month=2026-06"
            r"&mode=simple&tab=overview&comparison=amounts$"
        )
    )
    assert page.evaluate("window.stillThisPage === true"), "the page was reloaded"


def test_a_shortcut_opened_in_a_new_tab_leaves_this_page_as_it_was(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)

    with page.context.expect_page(timeout=5000) as opened:
        page.locator("#only-joint-savings").click(modifiers=["Control"])

    expect(opened.value).to_have_url(re.compile(r"&account=joint-savings&month="))
    expect(page.get_by_label("Joint current")).to_be_checked()
    expect(page.get_by_label("Joint savings")).to_be_checked()


def test_a_shortcut_names_the_month_shown_after_the_month_changes(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)

    page.get_by_label("Måned", exact=True).select_option("2026-05")
    page.wait_for_function("location.search.includes('month=2026-05')")

    for shortcut in ("#only-joint-savings", "#accounts-all", "#accounts-none"):
        expect(page.locator(shortcut)).to_have_attribute(
            "href", re.compile(r"&month=2026-05&")
        )


def test_a_shortcut_keeps_the_mode_chosen_on_the_page(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)

    page.get_by_label("Avanceret", exact=True).check()
    page.wait_for_function("location.search.includes('mode=advanced')")

    for shortcut in ("#only-joint-savings", "#accounts-all", "#accounts-none"):
        expect(page.locator(shortcut)).to_have_attribute(
            "href", re.compile(r"&mode=advanced&")
        )


def test_active_request_failure_is_visible_accessible_and_retryable(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.route("**/report?*", lambda route: route.abort("failed"))

    page.get_by_label("Joint savings").uncheck()

    alert = page.get_by_role("alert")
    expect(alert).to_be_visible()
    expect(alert).to_contain_text("Rapporten kunne ikke hentes.")
    expect(alert).to_contain_text("De viste tal er ikke opdateret.")
    expect(page.get_by_role("button", name="Prøv igen")).to_be_visible()

    page.unroute("**/report?*")
    page.get_by_role("button", name="Prøv igen").click()
    expect(page.get_by_role("alert")).to_have_count(0)
    expect(page.locator("#report-region #report")).to_have_count(1)


@pytest.mark.parametrize(
    ("mode", "tab"),
    [
        ("simple", "overview"),
        ("advanced", "overview"),
        ("advanced", "details"),
    ],
)
def test_a_superseded_failure_cannot_replace_a_newer_successful_report(
    page: Page,
    dashboard: BrowserDashboard,
    mode: str,
    tab: str,
) -> None:
    log_in(page, dashboard)
    _choose_view(page, mode, tab)
    pending = []
    old_request_handled = False

    def hold_old_report(route: Route) -> None:
        url = route.request.url
        if "month=2026-06" in url:
            pending.append(route)
        else:
            route.continue_()

    page.route("**/report?*", hold_old_report)
    page.evaluate(
        """() => {
          for (const id of ['race-old', 'race-new']) {
            const source = document.createElement('button');
            source.id = id;
            source.type = 'button';
            document.body.append(source);
          }
        }"""
    )
    try:
        old_url = (
            "/report?publication=2&reference_date=2026-06-01"
            f"&account=joint-current&month=2026-06&mode={mode}&tab={tab}"
        )
        page.evaluate(
            """(url) => {
              htmx.ajax(
                'GET',
                url,
                {
                  source: document.querySelector('#race-old'),
                  target: '#report-region',
                  swap: 'innerHTML'
                }
              );
            }""",
            old_url,
        )
        page.wait_for_timeout(100)
        assert len(pending) == 1, "the first report request was not held"

        new_url = (
            "/report?publication=2&reference_date=2026-06-01"
            f"&account=joint-current&month=2026-05&mode={mode}&tab={tab}"
        )
        page.evaluate(
            """(url) => {
              htmx.ajax(
                'GET',
                url,
                {
                  source: document.querySelector('#race-new'),
                  target: '#report-region',
                  swap: 'innerHTML'
                }
              );
            }""",
            new_url,
        )
        page.wait_for_function("location.search.includes('month=2026-05')")
        expect(page.locator("#report")).to_have_attribute("data-month", "2026-05")

        pending[0].abort("failed")
        old_request_handled = True
        page.wait_for_timeout(250)

        expect(page.get_by_role("alert")).to_have_count(0)
        expect(page.locator("#report")).to_have_attribute("data-month", "2026-05")
        expect(page.locator("#report")).to_have_attribute("data-mode", mode)
        expect(page.locator("#report")).to_have_attribute("data-tab", tab)
        expect(page.locator('input[name="tab"]')).to_have_value(tab)
        expect(page).to_have_url(
            re.compile(rf".*month=2026-05&mode={mode}&tab={tab}&comparison=amounts")
        )
    finally:
        if pending and not old_request_handled:
            pending[0].abort("failed")
        page.unroute("**/report?*")


def test_login_and_account_selection_work_from_the_keyboard(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    page.goto(f"{dashboard.url}/login")
    passphrase = page.get_by_label("Adgangskode")
    expect(passphrase).to_be_focused()
    page.keyboard.type(HOUSEHOLD_PHRASE)
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Log ind")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="Oversigt")).to_be_visible()

    current = page.get_by_label("Joint current")
    current.focus()
    page.keyboard.press("Space")
    expect(current).not_to_be_checked()
    page.wait_for_function(
        "location.search.includes('account=joint-savings')"
        " && !location.search.includes('account=joint-current')"
    )

    # Each account's "kun" link follows its box in the tab order.
    page.keyboard.press("Tab")
    expect(page.locator("#only-joint-current")).to_be_focused()
    page.keyboard.press("Tab")
    savings = page.get_by_label("Joint savings")
    expect(savings).to_be_focused()
    page.keyboard.press("Space")
    expect(savings).not_to_be_checked()
    expect(page.get_by_role("heading", name="Ingen konti valgt")).to_be_visible()


def test_shared_shell_is_usable_at_desktop_and_phone_widths(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    footer = page.locator(".site-footer")
    expect(footer).to_contain_text("Beskyttet adgang")
    expect(footer).not_to_contain_text("Kun på denne maskine")
    selection = page.locator(".selection-panel")
    report = page.locator(".report-panel")
    selection_box = selection.bounding_box()
    report_box = report.bounding_box()
    assert selection_box is not None
    assert report_box is not None
    assert selection_box["x"] < report_box["x"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    screenshot_dir = os.environ.get("PR310_SCREENSHOT_DIR")
    destination = None if screenshot_dir is None else Path(screenshot_dir)
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=destination / "dashboard-desktop.png", full_page=True)

    page.set_viewport_size({"width": 390, "height": 844})
    selection_box = selection.bounding_box()
    report_box = report.bounding_box()
    assert selection_box is not None
    assert report_box is not None
    assert selection_box["y"] < report_box["y"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(page.get_by_role("heading", name="Oversigt")).to_be_visible()
    expect(page.get_by_role("button", name="Vis rapport")).to_be_visible()

    if destination is not None:
        page.screenshot(path=destination / "dashboard-phone.png", full_page=True)


def test_the_unclassified_bucket_stays_readable_at_phone_width(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.set_viewport_size({"width": 390, "height": 844})
    bucket = page.locator("#unclassified")
    expect(bucket).to_contain_text("Ukategoriseret")
    bucket_box = bucket.bounding_box()
    assert bucket_box is not None
    for value_id, label in (("unclassified-in", "Ind"), ("unclassified-out", "Ud")):
        value = page.locator(f"#{value_id}")
        expect(value).to_be_visible()
        # The direction is named in words next to the value, never by colour.
        expect(value.locator("xpath=..")).to_contain_text(label)
        box = value.bounding_box()
        assert box is not None
        assert bucket_box["x"] <= box["x"]
        assert box["x"] + box["width"] <= bucket_box["x"] + bucket_box["width"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_a_category_detail_opens_and_closes_by_keyboard_and_through_history(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.get_by_label("Måned", exact=True).select_option("2026-04")
    page.wait_for_function("location.search.includes('month=2026-04')")

    rent = page.get_by_role("link", name="Rent")
    rent.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="Rent, april 2026")).to_be_visible()

    page.go_back()
    expect(page.get_by_role("heading", name="Oversigt")).to_be_visible()
    expect(page.get_by_label("Måned", exact=True)).to_have_value("2026-04")
    expect(page.get_by_role("link", name="Rent")).to_be_visible()

    page.go_forward()
    expect(page.get_by_role("heading", name="Rent, april 2026")).to_be_visible()
    back = page.get_by_role("link", name="Tilbage til oversigten")
    back.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_label("Måned", exact=True)).to_have_value("2026-04")


def test_a_category_detail_is_readable_at_phone_width(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(
        f"{dashboard.url}/category?publication=2&reference_date=2026-05-31"
        "&account=joint-current&account=joint-savings&month=2026-04"
        "&group=housing&scope=year_to_date"
    )

    expect(
        page.get_by_role("heading", name="Housing, januar\N{EN DASH}april 2026")
    ).to_be_visible()
    expect(page.locator("#detail-rows")).to_contain_text("Utilities")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_advanced_mode_is_keyboard_accessible_and_survives_history(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.get_by_label("Måned", exact=True).select_option("2026-04")
    page.wait_for_function("location.search.includes('month=2026-04')")

    advanced = page.get_by_role("radio", name="Avanceret")
    advanced.focus()
    page.keyboard.press("Space")
    expect(advanced).to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-mode", "advanced")
    expect(page.locator("#report")).to_have_attribute("data-tab", "overview")
    expect(page.get_by_role("link", name="Detaljer")).to_have_count(1)
    expect(page.get_by_role("link", name="Kontrol")).to_have_count(1)
    expect(page).to_have_url(
        re.compile(r".*month=2026-04&mode=advanced&tab=overview.*")
    )
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("group", name="Visning")).to_be_visible()
    expect(page.get_by_label("Måned", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    rent = page.get_by_role("link", name="Rent")
    rent.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="Rent, april 2026")).to_be_visible()
    expect(page).to_have_url(re.compile(r".*mode=advanced&tab=overview.*"))

    page.go_back()
    expect(page.get_by_label("Måned", exact=True)).to_have_value("2026-04")
    expect(page.get_by_role("radio", name="Avanceret")).to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-mode", "advanced")
    assert "25.000" not in str(page.evaluate("history.state"))

    page.go_forward()
    expect(page.get_by_role("heading", name="Rent, april 2026")).to_be_visible()
    back = page.get_by_role("link", name="Tilbage til oversigten")
    back.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("radio", name="Avanceret")).to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-mode", "advanced")


def _open_details_at_month(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.get_by_label("Måned", exact=True).select_option("2026-03")
    page.wait_for_function("location.search.includes('month=2026-03')")

    advanced = page.get_by_role("radio", name="Avanceret")
    advanced.focus()
    page.keyboard.press("Space")
    expect(page.locator("#report")).to_have_attribute("data-tab", "overview")

    details = page.get_by_role("link", name="Detaljer")
    expect(details).to_be_visible()
    details.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")
    expect(page.get_by_role("heading", name="Kontodetaljer")).to_be_visible()
    expect(page).to_have_url(re.compile(r".*mode=advanced&tab=details.*"))


def _explanation_returns_to_current_account_details(
    page: Page,
    current: Locator,
    savings: Locator,
) -> None:
    explanation = page.get_by_role("link", name="Hvorfor tallene er ufuldstændige")
    explanation.focus()
    page.keyboard.press("Enter")
    back = page.get_by_role("link", name="Tilbage til oversigten")
    expect(back).to_be_visible()
    back.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")
    expect(current).to_be_checked()
    expect(savings).not_to_be_checked()


def test_details_tab_keeps_selection_through_history_and_resets_after_mode_switch(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    _open_details_at_month(page, dashboard)

    page.get_by_label("Måned", exact=True).select_option("2026-04")
    page.wait_for_function("location.search.includes('month=2026-04')")
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")
    page.get_by_label("Måned", exact=True).select_option("2026-03")
    page.wait_for_function("location.search.includes('month=2026-03')")
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")

    advanced = page.get_by_role("radio", name="Avanceret")
    current = page.get_by_role("checkbox", name="Joint current")
    savings = page.get_by_role("checkbox", name="Joint savings")
    savings.uncheck()
    page.wait_for_function(
        "location.search.includes('account=joint-current')"
        " && !location.search.includes('account=joint-savings')"
        " && location.search.includes('tab=details')"
    )
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")

    page.go_back()
    expect(savings).to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")
    page.go_forward()
    expect(savings).not_to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-tab", "details")

    _explanation_returns_to_current_account_details(page, current, savings)

    current.uncheck()
    page.wait_for_function("!location.search.includes('account=')")
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page.locator('input[name="tab"]')).to_have_value("details")

    simple = page.get_by_role("radio", name="Enkel")
    simple.focus()
    page.keyboard.press("Space")
    expect(page).to_have_url(re.compile(r".*mode=simple&tab=overview.*"))
    expect(page.locator('input[name="tab"]')).to_have_value("overview")

    advanced.focus()
    page.keyboard.press("Space")
    expect(page).to_have_url(re.compile(r".*mode=advanced&tab=overview.*"))
    expect(page.locator('input[name="tab"]')).to_have_value("overview")

    current.check()
    page.wait_for_function("location.search.includes('account=joint-current')")
    expect(page.locator("#report")).to_have_attribute("data-tab", "overview")
    expect(page.locator('input[name="active_mode"]')).to_have_value("advanced")
    expect(page.locator('input[name="tab"]')).to_have_value("overview")

    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("link", name="Detaljer").click()
    expect(page.get_by_role("heading", name="Kontodetaljer")).to_be_visible()
    expect(page.get_by_role("link", name="Detaljer")).to_have_attribute(
        "aria-current", "page"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_empty_switches_and_basic_explanation_restore_the_pinned_advanced_view(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.get_by_label("Måned", exact=True).select_option("2026-03")
    page.wait_for_function("location.search.includes('month=2026-03')")
    advanced = page.get_by_role("radio", name="Avanceret")
    advanced.focus()
    page.keyboard.press("Space")
    expect(advanced).to_be_checked()

    explanation = page.get_by_role("link", name="Hvorfor tallene er ufuldstændige")
    explanation.focus()
    page.keyboard.press("Enter")
    expect(
        page.get_by_role("heading", name="Om tallene for marts 2026")
    ).to_be_visible()
    page.go_back()
    expect(advanced).to_be_checked()
    expect(page.get_by_label("Måned", exact=True)).to_have_value("2026-03")

    page.get_by_label("Joint current").uncheck()
    page.get_by_label("Joint savings").uncheck()
    page.wait_for_function("!location.search.includes('account=')")
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")

    simple = page.get_by_role("radio", name="Enkel")
    simple.focus()
    page.keyboard.press("Space")
    expect(simple).to_be_checked()
    expect(page).to_have_url(re.compile(r".*month=2026-03&mode=simple&tab=overview.*"))

    advanced.focus()
    page.keyboard.press("Space")
    expect(advanced).to_be_checked()
    expect(page).to_have_url(
        re.compile(r".*month=2026-03&mode=advanced&tab=overview.*")
    )

    page.get_by_label("Joint current").check()
    page.wait_for_function("location.search.includes('account=joint-current')")
    expect(page.get_by_role("radio", name="Avanceret")).to_be_checked()
    expect(page.locator("#report")).to_have_attribute("data-mode", "advanced")
    expect(page.locator("#report")).to_have_attribute("data-tab", "overview")


def test_kontrol_and_its_waterfall_are_readable_at_phone_width(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(
        f"{dashboard.url}/?publication=2&reference_date=2026-05-31"
        "&account=joint-current&account=joint-savings&month=2026-03"
        "&mode=advanced&tab=checks"
    )
    page.get_by_text("Beregning for Joint current").click()

    expect(page.locator("#checks-verdict-joint-current")).to_have_text("Data mangler")
    expect(page.locator("#checks-waterfall-joint-current")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
