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
from playwright.sync_api import Browser, Page, Route, expect, sync_playwright

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

    page.get_by_label("Joint savings").uncheck()
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


def test_empty_selection_survives_reload_back_and_forward(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
    page.get_by_label("Joint current").uncheck()
    page.get_by_label("Joint savings").uncheck()
    page.wait_for_function("!location.search.includes('account=')")
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")

    page.reload()
    expect(page.get_by_label("Joint current")).not_to_be_checked()
    expect(page.get_by_label("Joint savings")).not_to_be_checked()
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page).to_have_url(
        re.compile(r"/\?publication=2&reference_date=2026-06-01&month=2026-06$")
    )

    page.get_by_label("Joint current").check()
    page.wait_for_function("location.search.includes('account=joint-current')")
    expect(page.get_by_label("Joint current")).to_be_checked()

    page.go_back()
    expect(page.get_by_label("Joint current")).not_to_be_checked()
    expect(page.locator("#report-region")).to_contain_text("Vælg mindst én konto.")
    expect(page).to_have_url(
        re.compile(r"/\?publication=2&reference_date=2026-06-01&month=2026-06$")
    )

    page.go_forward()
    expect(page.get_by_label("Joint current")).to_be_checked()
    expect(page.get_by_label("Joint savings")).not_to_be_checked()


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


def test_a_superseded_failure_cannot_replace_a_newer_successful_report(
    page: Page,
    dashboard: BrowserDashboard,
) -> None:
    log_in(page, dashboard)
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
        page.evaluate(
            """() => {
              htmx.ajax(
                'GET',
                '/report?publication=2&reference_date=2026-06-01&account=joint-current&month=2026-06',
                {
                  source: document.querySelector('#race-old'),
                  target: '#report-region',
                  swap: 'innerHTML'
                }
              );
            }"""
        )
        page.wait_for_timeout(100)
        assert len(pending) == 1, "the first report request was not held"

        page.evaluate(
            """() => {
              htmx.ajax(
                'GET',
                '/report?publication=2&reference_date=2026-06-01&account=joint-current&month=2026-05',
                {
                  source: document.querySelector('#race-new'),
                  target: '#report-region',
                  swap: 'innerHTML'
                }
              );
            }"""
        )
        page.wait_for_function("location.search.includes('month=2026-05')")
        expect(page.locator("#report")).to_have_attribute("data-month", "2026-05")

        pending[0].abort("failed")
        old_request_handled = True
        page.wait_for_timeout(250)

        expect(page.get_by_role("alert")).to_have_count(0)
        expect(page.locator("#report")).to_have_attribute("data-month", "2026-05")
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
