# Copyright 2026 Therkel
"""Safe return as a feature: the explanation page links back where the reader was.

The dashboard is driven in-process.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget.dashboard import FEATURES, create_app
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
# Where the back link went before safe return: the overview of the same view.
OVERVIEW_PAGE = (
    "/?publication=1&reference_date=2026-05-14"
    f"&account={CURRENT}&account={SAVINGS}&month=2026-03"
    "&mode=simple&tab=overview&comparison=amounts"
)
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
        create_app(profile, clock=lambda: NOW, features=features),
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
    client = _client(tmp_path, (LOGIN, ERRORS, VIEW_STATE, EXPLANATION, SAFE_RETURN))

    assert _back_link(client, CATEGORY_PAGE) == CATEGORY_PAGE


def test_the_dashboard_links_the_explanation_page_back_where_the_reader_was(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, FEATURES)

    assert _back_link(client, CATEGORY_PAGE) == CATEGORY_PAGE


@pytest.mark.parametrize(
    "return_to",
    [
        "https://example.invalid/",
        "//example.invalid/",
        "/\\example.invalid/",
        # Browsers drop the tab and read what is left as `//example.invalid/`.
        "/\t/example.invalid/",
        "javascript:alert(1)",
        "/login",
        "category",
    ],
)
def test_the_explanation_page_never_links_back_off_the_dashboards_own_pages(
    tmp_path: Path,
    return_to: str,
) -> None:
    client = _client(tmp_path, (LOGIN, ERRORS, VIEW_STATE, EXPLANATION, SAFE_RETURN))

    assert _back_link(client, return_to) == OVERVIEW_PAGE


def test_without_the_safe_return_feature_the_explanation_page_links_to_the_overview(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, (LOGIN, ERRORS, VIEW_STATE, EXPLANATION))

    assert _back_link(client, CATEGORY_PAGE) == OVERVIEW_PAGE
