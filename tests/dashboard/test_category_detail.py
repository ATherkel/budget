# Copyright 2026 Therkel
"""Category and group detail: the entries behind an overview figure.

Expected values are the "Spending detail" worked examples in
`report-contract.md`, over the synthetic worked-example publication; the
dashboard is driven in-process.
"""

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

# The worked examples' reference date: May is the current month.
REFERENCE_DATE = "2026-05-14"

PINNED = (
    f"publication=1&reference_date={REFERENCE_DATE}"
    f"&account={CURRENT}&account={SAVINGS}"
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    profile: Profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: datetime(2026, 5, 14, 10, tzinfo=UTC)),
        follow_redirects=False,
    )
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def report(client: TestClient, month: str) -> Page:
    """Return the overview's report fragment for both accounts in `month`."""
    response = client.get(
        "/report",
        params={
            "publication": str(PUBLICATION.publication_id),
            "reference_date": REFERENCE_DATE,
            "account": [CURRENT, SAVINGS],
            "month": month,
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return read(response.text)


def test_each_overview_category_links_to_its_detail_in_the_same_pinned_context(
    client: TestClient,
) -> None:
    # February lists Rent and Groceries; each opens its own month detail
    # under the page's pin and selection.
    february = report(client, "2026-02")

    assert (
        february.attributes("category-link-groceries").get("href"),
        february.attributes("category-link-rent").get("href"),
    ) == (
        f"/category?{PINNED}&month=2026-02&category=groceries&scope=month",
        f"/category?{PINNED}&month=2026-02&category=rent&scope=month",
    )
