# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

import hashlib
from collections.abc import Callable, MutableMapping, Sequence
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    PrefixLoader,
    select_autoescape,
)

from budget.dashboard import session
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.months import danish_date
from budget.dashboard.display.text import (
    account_names,
    balance_observation,
    coverage_gap,
    coverage_label,
    coverage_link_label,
    coverage_note,
    danish_list,
    evidence_line,
    incomplete_months,
    monthly_snapshot_line,
    provisional_reasons,
    transaction_kind,
)
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.category import CATEGORY
from budget.dashboard.features.checks import CHECKS
from budget.dashboard.features.errors import ERRORS
from budget.dashboard.features.explanation import EXPLANATION
from budget.dashboard.features.login import LOGIN
from budget.dashboard.features.overview import overview_feature
from budget.dashboard.features.report import REPORT, render_report
from budget.dashboard.features.view_state import VIEW_STATE
from budget.dashboard.passphrase import (
    CredentialSnapshot,
    read_credentials,
    require_passphrase,
    set_passphrase,
)
from budget.dashboard.session import SESSION_COOKIE
from budget.gold.store import GoldStore
from budget.profiles import Profile

__all__ = ["create_app", "set_passphrase"]

_STATIC = Path(__file__).parent / "static"


@cache
def _static_digest(path: Path) -> str:
    """Return the start of the file at `path`'s SHA-256, read once per process.

    An edited file therefore gets its new address after a restart.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _static_url(name: str) -> str:
    """Return the address of static file `name`, named by its content.

    A browser that cached an older file under a bare address could keep
    running it after a deploy.
    """
    return f"/static/{name}?v={_static_digest(_STATIC / name)}"


def _feature_stylesheets(feature: Feature) -> dict[str, Path]:
    """Return the address of each stylesheet in `feature`'s folder, and its file.

    Each is named by its content, as `_static_url` names a shared one.
    """
    return {
        f"/static/{feature.folder.name}/{sheet.name}?v={_static_digest(sheet)}": sheet
        for sheet in sorted(feature.folder.glob("*.css"))
    }


def _serving(sheet: Path) -> Callable[[], Response]:
    """Return a route that answers with the stylesheet `sheet` and nothing else."""

    def stylesheet() -> Response:
        return FileResponse(sheet, media_type="text/css")

    return stylesheet


def _serve_stylesheets(app: FastAPI, features: Sequence[Feature]) -> None:
    """Serve each stylesheet of `features` at its address, and no other file."""
    for feature in features:
        for address, sheet in _feature_stylesheets(feature).items():
            app.add_api_route(
                address.partition("?")[0], _serving(sheet), include_in_schema=False
            )


def _add_global(namespace: MutableMapping[str, Any], name: str, value: object) -> None:
    """Add `value` to the names every template sees, as `name`.

    Jinja leaves `Environment.globals` unannotated, so a type checker infers
    it from the builtins it starts with; any value may join them.
    """
    namespace[name] = value


def _templates(features: Sequence[Feature]) -> Environment:
    """Return the templates one dashboard renders its pages from.

    A feature's own templates are named after its folder, as `<folder>/<file>`,
    so two features in folders of one name raise `ValueError`.
    """
    own = {
        feature.folder.name: FileSystemLoader(feature.folder) for feature in features
    }
    if len(own) < len(features):
        names = sorted(feature.folder.name for feature in features)
        message = f"two features share a folder name: {', '.join(names)}"
        raise ValueError(message)
    templates = Environment(
        loader=ChoiceLoader([PackageLoader("budget.dashboard"), PrefixLoader(own)]),
        autoescape=select_autoescape(),
    )
    templates.filters["amount"] = amount
    templates.filters["static_url"] = _static_url
    templates.filters["signed_amount"] = signed_amount
    templates.filters["danish_list"] = danish_list
    templates.filters["danish_date"] = danish_date
    templates.filters["account_names"] = account_names
    templates.filters["balance_observation"] = balance_observation
    templates.filters["coverage_gap"] = coverage_gap
    templates.filters["coverage_label"] = coverage_label
    templates.filters["coverage_link_label"] = coverage_link_label
    templates.filters["evidence_line"] = evidence_line
    templates.filters["incomplete_months"] = incomplete_months
    templates.filters["monthly_snapshot_line"] = monthly_snapshot_line
    templates.filters["provisional_reasons"] = provisional_reasons
    templates.filters["transaction_kind"] = transaction_kind
    _add_global(templates.globals, "coverage_note", coverage_note)
    addresses = [
        address for feature in features for address in _feature_stylesheets(feature)
    ]
    _add_global(templates.globals, "feature_stylesheets", addresses)
    return templates


def _send_to_login(request: Request) -> Response:
    """Send a reader who is not logged in to the login page.

    A page is redirected. An htmx fragment gets 401 and `HX-Redirect`, so htmx
    moves the whole page to login rather than painting it into a panel.
    """
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


def _logged_in(
    request: Request,
    profile: Profile,
    clock: Callable[[], datetime],
) -> CredentialSnapshot | None:
    """Return the credential that authorized `request`, if any."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie is None:
        return None
    credentials = read_credentials(profile)
    return (
        credentials
        if session.is_valid(credentials.session_key, cookie, clock())
        else None
    )


# The features the dashboard serves, one line each; one left out is off.
FEATURES: tuple[Feature, ...] = (
    ERRORS,
    LOGIN,
    VIEW_STATE,
    overview_feature(render_report),
    REPORT,
    CATEGORY,
    EXPLANATION,
    CHECKS,
)


def create_app(
    profile: Profile,
    *,
    clock: Callable[[], datetime],
    features: Sequence[Feature] = FEATURES,
) -> FastAPI:
    """Build the dashboard for `profile`, telling time with `clock`.

    Raises `PassphraseNotSetError` when no passphrase guards it, and
    `StoreNotFoundError` when the profile's Gold store does not exist, so a
    dashboard that is unguarded or cannot report refuses to start.
    """
    require_passphrase(profile)
    GoldStore(profile, read_only=True).close()
    app = FastAPI()
    # Ahead of the shared files, which would otherwise answer these addresses.
    _serve_stylesheets(app, features)
    # The htmx script ships in the package: nothing is fetched from the internet.
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    templates = _templates(features)

    def start_session(response: Response, credentials: CredentialSnapshot) -> Response:
        """Set a session cookie lasting `LOGIN_LIFETIME` from now.

        Every logged-in response passes here, so none of them may be cached:
        each carries the household's figures or choices.
        """
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            SESSION_COOKIE,
            session.issue(credentials.session_key, clock()),
            # Relative, so the browser keeps it across restarts for as long as
            # the signed expiry inside it allows.
            max_age=int(session.LOGIN_LIFETIME.total_seconds()),
            httponly=True,
            samesite="strict",
        )
        return response

    def for_reader(request: Request, respond: Callable[[], Response]) -> Response:
        """Answer a logged-in reader with `respond()`; send anyone else to log in."""
        authenticated_as = _logged_in(request, profile, clock)
        if authenticated_as is None:
            return _send_to_login(request)
        # Every visit renews the login for another 30 days from now.
        return start_session(respond(), authenticated_as)

    dashboard = Dashboard(profile, clock, templates, app, for_reader, start_session)
    for feature in features:
        feature.register(dashboard)

    return app
