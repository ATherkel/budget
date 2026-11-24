# Copyright 2026 Therkel
"""Dashboard features: a feature folder plugs in with one line in `create_app`.

A sample feature in `sample_feature/` stands in for a real one; the dashboard
is driven in-process.
"""

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import budget.dashboard.features
from budget.dashboard import FEATURES, create_app
from budget.dashboard.features import Feature
from tests.dashboard.households import HOUSEHOLD_PHRASE, dashboard_profile
from tests.dashboard.pages import read
from tests.dashboard.sample_feature import SAMPLE

NOW = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
STYLESHEET = re.compile(r'<link rel="stylesheet" href="([^"]+)">')
FEATURES_FOLDER = Path(budget.dashboard.features.__file__).parent


def logged_in(tmp_path: Path, features: tuple[Feature, ...]) -> TestClient:
    """Return a logged-in client of a dashboard with `features` registered."""
    app = create_app(dashboard_profile(tmp_path), clock=lambda: NOW, features=features)
    client = TestClient(app, follow_redirects=False)
    login = client.post("/login", data={"passphrase": HOUSEHOLD_PHRASE})
    assert login.status_code == 303, "the household passphrase did not log in"
    return client


def test_a_registered_feature_serves_its_page(tmp_path: Path) -> None:
    client = logged_in(tmp_path, (SAMPLE,))

    response = client.get("/sample")

    assert (response.status_code, read(response.text).text_of("sample-heading")) == (
        200,
        "Sample feature",
    )


def test_a_feature_left_out_serves_no_page_and_links_no_stylesheet(
    tmp_path: Path,
) -> None:
    client = logged_in(tmp_path, ())

    assert (
        client.get("/sample").status_code,
        any(
            "sample.css" in sheet
            for sheet in STYLESHEET.findall(client.get("/login").text)
        ),
    ) == (404, False)


def test_two_features_in_folders_of_one_name_are_refused(tmp_path: Path) -> None:
    # Both would answer to `sample_feature/` templates and stylesheet addresses.
    namesake = tmp_path / "elsewhere" / "sample_feature"
    namesake.mkdir(parents=True)
    twin = Feature(folder=namesake, register=lambda _dashboard: None)

    with pytest.raises(ValueError, match="sample_feature"):
        create_app(
            dashboard_profile(tmp_path), clock=lambda: NOW, features=(SAMPLE, twin)
        )


def test_a_feature_folder_serves_its_stylesheets_and_no_other_file(
    tmp_path: Path,
) -> None:
    # The folder also holds the feature's Python and templates.
    client = logged_in(tmp_path, (SAMPLE,))

    served = {
        name: client.get(f"/static/sample_feature/{name}").status_code
        for name in ("sample.css", "page.html", "__init__.py")
    }

    assert served == {"sample.css": 200, "page.html": 404, "__init__.py": 404}


def misplaced(features: Sequence[Feature]) -> list[str]:
    """Return each feature whose folder isn't its own package in `features/`."""
    return [
        str(feature.folder)
        for feature in features
        if feature.folder.parent != FEATURES_FOLDER
        or not (feature.folder / "__init__.py").is_file()
    ]


def test_a_feature_outside_the_features_folder_is_reported() -> None:
    # The sample lives under tests/, so it stands in for a stray feature.
    assert misplaced((SAMPLE,)) == [str(SAMPLE.folder)]


def test_every_registered_feature_is_its_own_package_in_the_features_folder() -> None:
    assert misplaced(FEATURES) == []


def test_every_page_links_a_registered_features_stylesheet_by_its_content(
    tmp_path: Path,
) -> None:
    # The feature's page and a page the feature never touched share base.html.
    client = logged_in(tmp_path, (SAMPLE,))
    sheet = (SAMPLE.folder / "sample.css").read_bytes()
    address = (
        f"/static/sample_feature/sample.css?v={hashlib.sha256(sheet).hexdigest()[:12]}"
    )

    linked = {
        path: address in STYLESHEET.findall(client.get(path).text)
        for path in ("/sample", "/login")
    }

    assert (linked, client.get(address).content) == (
        {"/sample": True, "/login": True},
        sheet,
    )
