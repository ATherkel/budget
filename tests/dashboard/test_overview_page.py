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
from tests.dashboard.pages import read
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
