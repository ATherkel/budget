# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

import hashlib
from collections.abc import Callable, Collection, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Self
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    PrefixLoader,
    select_autoescape,
)
from pydantic import BaseModel, model_validator

from budget.analytics import (
    AccountActivity,
    DetailScope,
    DetailSubject,
    HouseholdReports,
    InvalidSelectionError,
    MonthlyOverview,
    PublicationUnavailableError,
    ReportContext,
    SpendingDetail,
)
from budget.dashboard import session
from budget.dashboard.addresses import PinnedAddress, ReportRequest, pinned_url
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.months import (
    danish_date,
    month_label,
    month_value,
    parse_month,
    period_label,
)
from budget.dashboard.display.text import (
    account_names,
    balance_observation,
    coverage_gap,
    coverage_label,
    coverage_link_label,
    coverage_note,
    danish_list,
    evidence_line,
    incomplete_by_account,
    incomplete_months,
    monthly_snapshot_line,
    selection_problems,
    transaction_kind,
)
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.overview import overview_feature
from budget.dashboard.features.view_state import (
    DEFAULT_VIEW,
    VIEW_STATE,
    ViewState,
    parse_view_state,
    view_mode,
    view_state_controls,
)
from budget.dashboard.passphrase import (
    CredentialSnapshot,
    read_credentials,
    require_passphrase,
    set_passphrase,
)
from budget.dashboard.throttle import LoginThrottle
from budget.gold.store import GoldStore
from budget.profiles import Profile

__all__ = ["create_app", "set_passphrase"]

SESSION_COOKIE = "session"

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
    templates.filters["monthly_snapshot_line"] = monthly_snapshot_line
    templates.filters["transaction_kind"] = transaction_kind
    _add_global(templates.globals, "coverage_note", coverage_note)
    addresses = [
        address for feature in features for address in _feature_stylesheets(feature)
    ]
    _add_global(templates.globals, "feature_stylesheets", addresses)
    return templates


@dataclass(frozen=True)
class DetailRequest:
    """What a detail address asks for, beside the pinned publication and date."""

    accounts: tuple[str, ...]
    month: str
    subject: DetailSubject
    scope: DetailScope
    view: ViewState


class PinnedQuery(BaseModel):
    """Required query parameters shared by pinned report pages."""

    publication: int
    reference_date: date
    month: str
    account: list[str] = []
    mode: str = "simple"
    tab: str = "overview"
    comparison: str = "amounts"

    def pin(self) -> tuple[int, date]:
        """Return this address's publication and reference date."""
        return (self.publication, self.reference_date)


class ReportAddress(PinnedQuery):
    """The query string of one in-place report request and its prior mode."""

    active_mode: str | None = None

    def asked(self) -> ReportRequest:
        """Return the report request and the presentation state it came from."""
        view = parse_view_state(self.mode, self.tab, self.comparison)
        return ReportRequest(
            pin=self.pin(),
            accounts=tuple(self.account),
            month=self.month,
            view=view,
            active_mode=(
                view.mode if self.active_mode is None else view_mode(self.active_mode)
            ),
        )


class DetailAddress(BaseModel):
    """The query string of a detail page: the pin, the selection and the subject."""

    publication: int
    reference_date: date
    month: str
    account: list[str] = []
    category: str | None = None
    group: str | None = None
    scope: DetailScope = "month"
    mode: str = "simple"
    tab: str = "overview"
    comparison: str = "amounts"

    @model_validator(mode="after")
    def _names_one_subject(self) -> Self:
        """Refuse an address naming no subject, or both a Category and a group."""
        if (self.category is None) == (self.group is None):
            message = "name exactly one of category and group"
            raise ValueError(message)
        return self

    def asked(self) -> DetailRequest:
        """Return what the address asks for beside its pin."""
        subject = (
            DetailSubject("category", self.category)
            if self.category is not None
            else DetailSubject("group", self.group or "")
        )
        return DetailRequest(
            tuple(self.account),
            self.month,
            subject,
            self.scope,
            parse_view_state(self.mode, self.tab, self.comparison),
        )


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


def _refuse_login(
    templates: Environment,
    credentials: CredentialSnapshot,
    throttle: LoginThrottle,
    now: datetime,
    passphrase: str,
) -> Response | None:
    """Return why a login made at `now` is refused, or None when it succeeds.

    The caller holds `throttle.guard`, so the outcome is recorded before the
    next login is checked.
    """
    wait = throttle.seconds_locked(now)
    if wait:
        notice = f"For mange forkerte forsøg. Prøv igen om {wait} sekunder."
        return HTMLResponse(
            templates.get_template("login.html").render(message=notice),
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    # An empty form is not a guess, so it is refused without being counted.
    blank = not passphrase.strip()
    if blank or not credentials.matches(passphrase):
        if not blank:
            throttle.failed(now)
        return HTMLResponse(
            templates.get_template("login.html").render(
                message="Adgangskoden er forkert."
            )
        )
    throttle.succeeded()
    return None


def _read_overview(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> MonthlyOverview | str:
    """Return the overview a selection asks for, or a fragment saying why not.

    The pinned context is used exactly as the page sent it: never re-resolved.
    """
    publication_id, reference_date = pin
    try:
        selected_month = parse_month(month)
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=selected_month,
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).monthly_overview(context)
    except InvalidSelectionError as error:
        # A failure is shown, and echoes no context the page could render.
        return dashboard.templates.get_template("invalid_selection.html").render(
            problems=selection_problems(error)
        )
    except PublicationUnavailableError:
        return dashboard.templates.get_template("unavailable.html").render()


def _read_activity(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> AccountActivity | str:
    """Return account activity for a pinned selection, or a failure fragment."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).account_activity(context)
    except InvalidSelectionError as error:
        return dashboard.templates.get_template("invalid_selection.html").render(
            problems=selection_problems(error)
        )
    except PublicationUnavailableError:
        return dashboard.templates.get_template("unavailable.html").render()


def _answered_url(
    overview_report: MonthlyOverview,
    path: str,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the address of `path` for the context `overview_report` answers."""
    answered = overview_report.context
    return pinned_url(
        PinnedAddress(
            answered.publication_id,
            answered.reference_date,
            tuple(answered.account_ids),
            month_value(answered.month),
        ),
        path,
        view=view,
    )


def _detail_url(
    answered: ReportContext,
    kind: str,
    subject_id: str,
    scope: str = "month",
    *,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the address of one subject's detail under the pinned `answered`."""
    page = pinned_url(
        PinnedAddress(
            answered.publication_id,
            answered.reference_date,
            tuple(answered.account_ids),
            month_value(answered.month),
        ),
        "/category",
        view=view,
    )
    return f"{page}&" + urlencode([(kind, subject_id), ("scope", scope)])


def _read_detail(
    dashboard: Dashboard,
    pin: tuple[int, date],
    request: DetailRequest,
) -> SpendingDetail | str:
    """Return the detail `request` asks for, or a fragment saying why not."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(request.accounts),
            month=parse_month(request.month),
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).spending_detail(
                context, request.subject, request.scope
            )
    except InvalidSelectionError as error:
        return dashboard.templates.get_template("invalid_selection.html").render(
            problems=selection_problems(error)
        )
    except PublicationUnavailableError:
        return dashboard.templates.get_template("unavailable.html").render()


def _render_detail(
    dashboard: Dashboard,
    pin: tuple[int, date],
    request: DetailRequest,
) -> str:
    """Render the detail page of one subject under one pinned selection."""
    detail_report = _read_detail(dashboard, pin, request)
    if isinstance(detail_report, str):
        return dashboard.templates.get_template("category.html").render(
            failure=detail_report, title="Udgifter"
        )
    answered = detail_report.context
    subject = detail_report.subject
    period = period_label(detail_report.first_month, detail_report.last_month)
    return dashboard.templates.get_template("category.html").render(
        detail=detail_report,
        title=f"{detail_report.name}, {period}",
        scope_urls={
            scope: _detail_url(
                answered,
                subject.kind,
                subject.id,
                scope,
                view=request.view,
            )
            for scope in ("month", "year_to_date")
        },
        group_url=_detail_url(
            answered,
            "group",
            detail_report.group_id,
            detail_report.scope,
            view=request.view,
        ),
        incomplete=incomplete_by_account(detail_report.coverage),
        overview_url=pinned_url(
            PinnedAddress(
                answered.publication_id,
                answered.reference_date,
                tuple(answered.account_ids),
                month_value(answered.month),
            ),
            view=request.view,
        ),
    )


def _render_report(
    dashboard: Dashboard,
    requested: ReportRequest,
) -> str:
    """Render the report fragment a selection asks for, or why it cannot be shown."""
    overview_report = _read_overview(
        dashboard,
        requested.pin,
        requested.accounts,
        requested.month,
    )
    if isinstance(overview_report, str):
        return overview_report
    answered = overview_report.context
    activity = (
        _read_activity(
            dashboard,
            requested.pin,
            requested.accounts,
            requested.month,
        )
        if requested.view.mode == "advanced" and requested.view.tab == "details"
        else None
    )
    if isinstance(activity, str):
        return activity
    tab_urls = {
        destination: pinned_url(
            PinnedAddress(
                answered.publication_id,
                answered.reference_date,
                tuple(answered.account_ids),
                month_value(answered.month),
            ),
            view=ViewState(
                "advanced",
                destination,
                requested.view.comparison,
            ),
        )
        for destination in ("overview", "details")
    }
    return dashboard.templates.get_template("report.html").render(
        is_current=overview_report.publication.is_current,
        publication_id=answered.publication_id,
        reference_date=answered.reference_date.isoformat(),
        accounts=" ".join(sorted(answered.account_ids)),
        month=month_value(answered.month),
        month_label=month_label(answered.month),
        overview=overview_report,
        incomplete=[
            account_month.display_name
            for account_month in incomplete_months(overview_report.coverage)
        ],
        activity=activity,
        mode=requested.view.mode,
        tab=requested.view.tab,
        comparison=requested.view.comparison,
        tab_urls=tab_urls,
        explanation_url=_answered_url(
            overview_report,
            "/explanation",
            requested.view,
        ),
        detail_urls={
            category.category_id: _detail_url(
                answered,
                "category",
                category.category_id,
                view=requested.view,
            )
            for category in overview_report.categories
        },
    )


def _render_explanation(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
    view: ViewState,
) -> str:
    """Render the explanation page of one pinned report's trust notes."""
    overview_report = _read_overview(dashboard, pin, accounts, month)
    page = dashboard.templates.get_template("explanation.html")
    if isinstance(overview_report, str):
        return page.render(failure=overview_report)
    return page.render(
        overview=overview_report,
        incomplete_months=incomplete_months(overview_report.coverage),
        month_label=month_label(overview_report.context.month),
        report_url=_answered_url(overview_report, "/", view),
    )


def _report_response(
    dashboard: Dashboard,
    requested: ReportRequest,
) -> Response:
    """Return the report fragment for one selection, or the empty-selection prompt.

    The address becomes this selection's own page, so back and forward reopen
    each selection the reader made.
    """
    view = parse_view_state(
        requested.view.mode,
        requested.view.tab,
        requested.view.comparison,
    )
    if view.mode != requested.active_mode:
        view = ViewState(view.mode, "overview", view.comparison)
    page = pinned_url(
        PinnedAddress(*requested.pin, requested.accounts, requested.month),
        view=view,
    )
    state = view_state_controls(dashboard.templates, view)
    if not requested.accounts:
        # An empty selection is a prompt, never a report of nothing.
        prompt = dashboard.templates.get_template("no_accounts.html").render()
        return HTMLResponse(prompt + state, headers={"HX-Push-Url": page})
    fragment = _render_report(
        dashboard,
        ReportRequest(
            requested.pin,
            requested.accounts,
            requested.month,
            view,
            view.mode,
        ),
    )
    return HTMLResponse(fragment + state, headers={"HX-Push-Url": page})


# The features the dashboard serves, one line each; one left out is off.
FEATURES: tuple[Feature, ...] = (VIEW_STATE, overview_feature(_render_report))


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
    throttle = LoginThrottle()
    templates = _templates(features)

    @app.exception_handler(RequestValidationError)
    def malformed_address(request: Request, _error: RequestValidationError) -> Response:
        """Explain a malformed address in Danish, never as FastAPI's JSON.

        htmx swaps only a 2xx, so the fragment answers 200 while the page is a 400.
        """
        if request.url.path == "/report":
            fragment = templates.get_template("invalid_address.html").render()
            return HTMLResponse(fragment)
        page = templates.get_template("invalid_address_page.html").render()
        return HTMLResponse(page, status_code=400)

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

    dashboard = Dashboard(profile, clock, templates, app, for_reader)
    for feature in features:
        feature.register(dashboard)

    @app.get("/report")
    def report(
        request: Request,
        address: Annotated[ReportAddress, Query()],
    ) -> Response:
        return for_reader(
            request,
            lambda: _report_response(dashboard, address.asked()),
        )

    @app.get("/explanation")
    def explanation(
        request: Request,
        address: Annotated[PinnedQuery, Query()],
    ) -> Response:
        return for_reader(
            request,
            lambda: HTMLResponse(
                _render_explanation(
                    dashboard,
                    address.pin(),
                    address.account,
                    address.month,
                    parse_view_state(address.mode, address.tab, address.comparison),
                )
            ),
        )

    @app.get("/category")
    def category_detail(
        request: Request, address: Annotated[DetailAddress, Query()]
    ) -> Response:
        return for_reader(
            request,
            lambda: HTMLResponse(
                _render_detail(
                    dashboard,
                    (address.publication, address.reference_date),
                    address.asked(),
                )
            ),
        )

    @app.get("/login")
    def login_page() -> Response:
        return HTMLResponse(templates.get_template("login.html").render(message=""))

    @app.post("/login")
    def login(passphrase: Annotated[str, Form()] = "") -> Response:
        # One login at a time, from the lock check to recording the outcome.
        with throttle.guard:
            credentials = read_credentials(profile)
            refused = _refuse_login(
                templates, credentials, throttle, clock(), passphrase
            )
        if refused is not None:
            return refused
        return start_session(RedirectResponse("/", status_code=303), credentials)

    @app.post("/logout")
    def logout() -> Response:
        # This browser only; `set-passphrase` logs out every device.
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
        return response

    return app
