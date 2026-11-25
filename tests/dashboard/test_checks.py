# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the selection's trust diagnostics.

The dashboard is driven in-process over the synthetic worked example.
"""

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


def kontrol(client: TestClient, **changes: object) -> Page:
    """Return the Kontrol fragment for the worked example, with `changes`."""
    return read(
        client.get(
            "/report",
            params={**KONTROL, **changes},
            headers={"HX-Request": "true"},
        ).text
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
