# Copyright 2026 Therkel
"""Safe return as a feature: the explanation page links back where the reader was.

The dashboard is driven in-process.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from budget.dashboard import create_app
from budget.dashboard.features import Feature
from budget.dashboard.features.errors import ERRORS
from budget.dashboard.features.explanation import EXPLANATION
from budget.dashboard.features.login import LOGIN
from budget.dashboard.features.safe_return import SAFE_RETURN
from budget.dashboard.features.view_state import VIEW_STATE
from budget.gold import GoldResult
from budget.gold.store import GoldStore
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.gold.publishing import CONFIGURATION, RECIPE
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

NOW = datetime(2026, 5, 14, 10, tzinfo=UTC)
PINNED = {
    "publication": "1",
    "reference_date": "2026-05-14",
    "account": [CURRENT, SAVINGS],
    "month": "2026-03",
}
CATEGORY_PAGE = (
    "/category?publication=1&reference_date=2026-05-14"
    f"&account={CURRENT}&account={SAVINGS}&month=2026-03"
    "&mode=simple&tab=overview&comparison=amounts&category=groceries&scope=month"
)


def _client(tmp_path: Path, features: Sequence[Feature]) -> TestClient:
    profile = dashboard_profile(tmp_path)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
    client = TestClient(
        create_app(profile, clock=lambda: NOW, features=(LOGIN, *features)),
        follow_redirects=False,
    )
    client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    return client


def _back_link(client: TestClient, return_to: str) -> str:
    response = client.get("/explanation", params={**PINNED, "return_to": return_to})
    return read(response.text).attributes("back-to-report")["href"]


def test_the_explanation_page_links_back_to_the_page_the_reader_came_from(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, (ERRORS, VIEW_STATE, EXPLANATION, SAFE_RETURN))

    assert _back_link(client, CATEGORY_PAGE) == CATEGORY_PAGE
