# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel, model_validator

from budget.analytics import (
    AccountActivity,
    DetailScope,
    DetailSubject,
    Diagnostics,
    HouseholdReports,
    InvalidSelectionError,
    MonthlyOverview,
    NothingPublishedError,
    PublicationUnavailableError,
    ReportContext,
    SpendingDetail,
)
from budget.dashboard import display, session
from budget.dashboard.display import copenhagen_date
from budget.dashboard.passphrase import (
    CredentialSnapshot,
    read_credentials,
    require_passphrase,
    set_passphrase,
)
from budget.dashboard.throttle import LoginThrottle
from budget.gold import ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile

__all__ = ["create_app", "set_passphrase"]

SESSION_COOKIE = "session"
DEFAULT_MODE: Literal["simple"] = "simple"
DEFAULT_TAB: Literal["overview"] = "overview"
DEFAULT_COMPARISON: Literal["amounts"] = "amounts"

type DashboardMode = Literal["simple", "advanced"]
type AdvancedTab = Literal["overview", "details", "checks"]
type ComparisonMode = Literal["amounts"]


@dataclass(frozen=True)
class ViewState:
    """Presentation state carried beside the pinned report context."""

    mode: DashboardMode = "simple"
    tab: AdvancedTab = "overview"
    comparison: ComparisonMode = "amounts"


DEFAULT_VIEW = ViewState()


@dataclass(frozen=True)
class PinnedAddress:
    """The report pin and selection carried by a dashboard address."""

    publication_id: int
    reference_date: date
    accounts: tuple[str, ...]
    month: str


@dataclass(frozen=True)
class OverviewRequest:
    """A complete overview-page request, fresh or pinned."""

    pin: tuple[int, date] | None
    accounts: tuple[str, ...] | None
    month: str | None
    view: ViewState
    return_to: str | None


@dataclass(frozen=True)
class ReportRequest:
    """A report-fragment request and its current presentation state."""

    pin: tuple[int, date]
    accounts: tuple[str, ...]
    month: str
    view: ViewState
    active_mode: DashboardMode
    return_to: str | None


_STATIC = Path(__file__).parent / "static"

_TEMPLATES = Environment(
    loader=PackageLoader("budget.dashboard"),
    autoescape=select_autoescape(),
)
_TEMPLATES.filters["amount"] = display.amount
_TEMPLATES.filters["signed_amount"] = display.signed_amount
_TEMPLATES.filters["danish_list"] = display.danish_list


@dataclass(frozen=True)
class DetailRequest:
    """What a detail address asks for, beside the pinned publication and date."""

    accounts: tuple[str, ...]
    month: str
    subject: DetailSubject
    scope: DetailScope
    mode: DashboardMode
    tab: AdvancedTab
    comparison: ComparisonMode


class OverviewAddress(BaseModel):
    """Query parameters of a fresh or restored overview."""

    publication: int | None = None
    reference_date: date | None = None
    month: str | None = None
    account: list[str] = []
    mode: DashboardMode = "simple"
    tab: AdvancedTab = "overview"
    comparison: ComparisonMode = "amounts"
    return_to: str | None = None

    def asked(self) -> OverviewRequest:
        """Return the page request without resolving a fresh pin."""
        return OverviewRequest(
            pin=(
                None
                if self.publication is None or self.reference_date is None
                else (self.publication, self.reference_date)
            ),
            accounts=(
                None
                if self.publication is None or self.reference_date is None
                else tuple(self.account)
            ),
            month=self.month,
            view=ViewState(self.mode, self.tab, self.comparison),
            return_to=self.return_to,
        )


class ReportAddress(BaseModel):
    """Query parameters of one in-place report request."""

    publication: int
    reference_date: date
    month: str
    account: list[str] = []
    mode: DashboardMode = "simple"
    active_mode: DashboardMode = "simple"
    tab: AdvancedTab = "overview"
    comparison: ComparisonMode = "amounts"
    return_to: str | None = None

    def asked(self) -> ReportRequest:
        """Return the report request and its previous presentation state."""
        return ReportRequest(
            pin=(self.publication, self.reference_date),
            accounts=tuple(self.account),
            month=self.month,
            view=ViewState(self.mode, self.tab, self.comparison),
            active_mode=self.active_mode,
            return_to=self.return_to,
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
    mode: DashboardMode = "simple"
    tab: AdvancedTab = "overview"
    comparison: ComparisonMode = "amounts"

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
            self.mode,
            self.tab,
            self.comparison,
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


def _pinned_url(
    address: PinnedAddress,
    path: str = "/",
    *,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the complete address of `path` for one pinned selection."""
    return f"{path}?" + urlencode(
        [
            ("publication", address.publication_id),
            ("reference_date", address.reference_date.isoformat()),
            *(("account", account) for account in sorted(address.accounts)),
            ("month", address.month),
            ("mode", view.mode),
            ("tab", view.tab),
            ("comparison", view.comparison),
        ]
    )


def _mode(value: str) -> DashboardMode:
    """Return a supported mode, with a fresh or malformed address using Enkel."""
    return "advanced" if value == "advanced" else "simple"


def _tab(value: str) -> AdvancedTab:
    """Return a supported advanced tab, defaulting to Overblik."""
    if value == "details":
        return "details"
    return "checks" if value == "checks" else "overview"


def _safe_return_to(value: str | None) -> str | None:
    """Return an internal path for a return link, or no link for other text."""
    if value is None or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _render_overview(
    profile: Profile,
    clock: Callable[[], datetime],
    requested: OverviewRequest,
) -> str:
    """Render the overview page.

    A pinned page keeps its publication, reference date and selection. A fresh
    visit resolves the current publication and today's Copenhagen date, with
    every account and this month selected.
    """
    # A pinned address without accounts is an empty selection, not a fresh visit.
    fresh = requested.pin is None
    pin = requested.pin
    with GoldStore(profile, read_only=True) as store:
        reports = HouseholdReports(store)
        if pin is None:
            try:
                publication_id = reports.current_publication().publication_id
            except NothingPublishedError:
                return _TEMPLATES.get_template("nothing_published.html").render()
            pin = (publication_id, copenhagen_date(clock()))
        publication_id, reference_date = pin
        try:
            options = reports.selection_options(publication_id, reference_date)
        except PublicationUnavailableError:
            # Offered, never substituted: the reader chooses the current figures.
            return _TEMPLATES.get_template("unavailable_page.html").render()
    months = display.months_between(options.first_month, options.last_month)
    selected_accounts = (
        {account.account_id for account in options.accounts}
        if fresh
        else set(requested.accounts or ())
    )
    selected_month = requested.month or display.month_value(
        ReportingMonth.of(reference_date)
    )
    # The page carries its own report, so back, forward and a page without
    # scripts show what the selection's report says.
    report = (
        _render_report(
            profile,
            ReportRequest(
                pin=pin,
                accounts=tuple(selected_accounts),
                month=selected_month,
                view=requested.view,
                active_mode=requested.view.mode,
                return_to=requested.return_to,
            ),
        )
        if selected_accounts
        else None
    )
    canonical_url = _pinned_url(
        PinnedAddress(
            publication_id,
            reference_date,
            tuple(selected_accounts),
            selected_month,
        ),
        view=requested.view,
    )
    return_to = _safe_return_to(requested.return_to)
    if return_to is not None:
        canonical_url += "&" + urlencode({"return_to": return_to})
    return _TEMPLATES.get_template("overview.html").render(
        publication_id=publication_id,
        reference_date=reference_date.isoformat(),
        canonical_url=canonical_url,
        accounts=options.accounts,
        selected_accounts=selected_accounts,
        months=[
            (display.month_value(month), display.month_label(month)) for month in months
        ],
        selected_month=selected_month,
        report=report,
        mode=requested.view.mode,
        tab=requested.view.tab,
        comparison=requested.view.comparison,
        return_to=return_to,
    )


def _refuse_login(
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
            _TEMPLATES.get_template("login.html").render(message=notice),
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    # An empty form is not a guess, so it is refused without being counted.
    blank = not passphrase.strip()
    if blank or not credentials.matches(passphrase):
        if not blank:
            throttle.failed(now)
        return HTMLResponse(
            _TEMPLATES.get_template("login.html").render(
                message="Adgangskoden er forkert."
            )
        )
    throttle.succeeded()
    return None


def _read_overview(
    profile: Profile,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> MonthlyOverview | str:
    """Return the overview a selection asks for, or a fragment saying why not.

    The pinned context is used exactly as the page sent it: never re-resolved.
    """
    publication_id, reference_date = pin
    try:
        selected_month = display.parse_month(month)
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=selected_month,
            reference_date=reference_date,
        )
        with GoldStore(profile, read_only=True) as store:
            return HouseholdReports(store).monthly_overview(context)
    except InvalidSelectionError as error:
        # A failure is shown, and echoes no context the page could render.
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    except PublicationUnavailableError:
        return _TEMPLATES.get_template("unavailable.html").render()


def _read_activity(
    profile: Profile,
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
            month=display.parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(profile, read_only=True) as store:
            return HouseholdReports(store).account_activity(context)
    except InvalidSelectionError as error:
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    except PublicationUnavailableError:
        return _TEMPLATES.get_template("unavailable.html").render()


def _read_diagnostics(
    profile: Profile,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> Diagnostics | str:
    """Return Kontrol diagnostics for a pinned selection, or a failure fragment."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=display.parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(profile, read_only=True) as store:
            return HouseholdReports(store).diagnostics(context)
    except InvalidSelectionError as error:
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    except PublicationUnavailableError:
        return _TEMPLATES.get_template("unavailable.html").render()


def _answered_url(
    overview_report: MonthlyOverview,
    path: str,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the address of `path` for the context `overview_report` answers."""
    answered = overview_report.context
    return _pinned_url(
        PinnedAddress(
            answered.publication_id,
            answered.reference_date,
            tuple(answered.account_ids),
            display.month_value(answered.month),
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
    page = _pinned_url(
        PinnedAddress(
            answered.publication_id,
            answered.reference_date,
            tuple(answered.account_ids),
            display.month_value(answered.month),
        ),
        "/category",
        view=view,
    )
    return f"{page}&" + urlencode([(kind, subject_id), ("scope", scope)])


def _read_detail(
    profile: Profile,
    pin: tuple[int, date],
    request: DetailRequest,
) -> SpendingDetail | str:
    """Return the detail `request` asks for, or a fragment saying why not."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(request.accounts),
            month=display.parse_month(request.month),
            reference_date=reference_date,
        )
        with GoldStore(profile, read_only=True) as store:
            return HouseholdReports(store).spending_detail(
                context, request.subject, request.scope
            )
    except InvalidSelectionError as error:
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    except PublicationUnavailableError:
        return _TEMPLATES.get_template("unavailable.html").render()


def _render_detail(
    profile: Profile,
    pin: tuple[int, date],
    request: DetailRequest,
) -> str:
    """Render the detail page of one subject under one pinned selection."""
    detail_report = _read_detail(profile, pin, request)
    if isinstance(detail_report, str):
        return _TEMPLATES.get_template("category.html").render(
            failure=detail_report, title="Udgifter"
        )
    answered = detail_report.context
    subject = detail_report.subject
    period = display.period_label(detail_report.first_month, detail_report.last_month)
    return _TEMPLATES.get_template("category.html").render(
        detail=detail_report,
        title=f"{detail_report.name}, {period}",
        scope_urls={
            scope: _detail_url(
                answered,
                subject.kind,
                subject.id,
                scope,
                view=ViewState(request.mode, request.tab, request.comparison),
            )
            for scope in ("month", "year_to_date")
        },
        group_url=_detail_url(
            answered,
            "group",
            detail_report.group_id,
            detail_report.scope,
            view=ViewState(request.mode, request.tab, request.comparison),
        ),
        incomplete=display.incomplete_by_account(detail_report.coverage),
        overview_url=_pinned_url(
            PinnedAddress(
                answered.publication_id,
                answered.reference_date,
                tuple(answered.account_ids),
                display.month_value(answered.month),
            ),
            view=ViewState(request.mode, request.tab, request.comparison),
        ),
    )


def _render_report(
    profile: Profile,
    requested: ReportRequest,
) -> str:
    """Render the report fragment a selection asks for, or why it cannot be shown."""
    overview_report = _read_overview(
        profile,
        requested.pin,
        requested.accounts,
        requested.month,
    )
    if isinstance(overview_report, str):
        return overview_report
    answered = overview_report.context
    active_mode = requested.view.mode
    active_tab = requested.view.tab
    activity = (
        _read_activity(
            profile,
            requested.pin,
            requested.accounts,
            requested.month,
        )
        if active_mode == "advanced" and active_tab == "details"
        else None
    )
    diagnostics = (
        _read_diagnostics(
            profile,
            requested.pin,
            requested.accounts,
            requested.month,
        )
        if active_mode == "advanced" and active_tab == "checks"
        else None
    )
    if isinstance(activity, str):
        return activity
    if isinstance(diagnostics, str):
        return diagnostics
    origin_url = _answered_url(overview_report, "/", requested.view)
    control_url = _pinned_url(
        PinnedAddress(
            answered.publication_id,
            answered.reference_date,
            tuple(answered.account_ids),
            display.month_value(answered.month),
        ),
        view=ViewState("advanced", "checks", requested.view.comparison),
    )
    control_url += "&" + urlencode({"return_to": origin_url})
    return _TEMPLATES.get_template("report.html").render(
        is_current=overview_report.publication.is_current,
        publication_id=answered.publication_id,
        reference_date=answered.reference_date.isoformat(),
        accounts=" ".join(sorted(answered.account_ids)),
        month=display.month_value(answered.month),
        month_label=display.month_label(answered.month),
        overview=overview_report,
        activity=activity,
        diagnostics=diagnostics,
        mode=active_mode,
        tab=active_tab,
        comparison=requested.view.comparison,
        return_to=_safe_return_to(requested.return_to),
        tab_urls={
            destination: _pinned_url(
                PinnedAddress(
                    answered.publication_id,
                    answered.reference_date,
                    tuple(answered.account_ids),
                    display.month_value(answered.month),
                ),
                view=ViewState(
                    "advanced",
                    _tab(destination),
                    requested.view.comparison,
                ),
            )
            for destination in ("overview", "details", "checks")
        },
        explanation_url=control_url,
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
    profile: Profile,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> str:
    """Render the explanation page of one pinned report's trust notes."""
    overview_report = _read_overview(profile, pin, accounts, month)
    if isinstance(overview_report, str):
        return _TEMPLATES.get_template("explanation.html").render(
            failure=overview_report
        )
    return _TEMPLATES.get_template("explanation.html").render(
        overview=overview_report,
        month_label=display.month_label(overview_report.context.month),
        report_url=_answered_url(overview_report, "/"),
    )


def _report_response(
    profile: Profile,
    requested: ReportRequest,
) -> Response:
    """Return the report fragment for one selection, or the empty-selection prompt.

    The address becomes this selection's own page, so back and forward reopen
    each selection the reader made.
    """
    destination_mode = requested.view.mode
    destination_tab = (
        DEFAULT_TAB if destination_mode != requested.active_mode else requested.view.tab
    )
    page = _pinned_url(
        PinnedAddress(
            *requested.pin,
            requested.accounts,
            requested.month,
        ),
        view=ViewState(
            destination_mode,
            destination_tab,
            requested.view.comparison,
        ),
    )
    return_to = (
        _safe_return_to(requested.return_to)
        if destination_mode == "advanced" and destination_tab == "checks"
        else None
    )
    if return_to is not None:
        page += "&" + urlencode({"return_to": return_to})
    if not requested.accounts:
        # An empty selection is a prompt, never a report of nothing.
        prompt = _TEMPLATES.get_template("no_accounts.html").render()
        return HTMLResponse(prompt, headers={"HX-Push-Url": page})
    fragment = _render_report(
        profile,
        ReportRequest(
            pin=requested.pin,
            accounts=requested.accounts,
            month=requested.month,
            view=ViewState(
                destination_mode,
                destination_tab,
                requested.view.comparison,
            ),
            active_mode=destination_mode,
            return_to=return_to,
        ),
    )
    return HTMLResponse(fragment, headers={"HX-Push-Url": page})


def create_app(profile: Profile, *, clock: Callable[[], datetime]) -> FastAPI:
    """Build the dashboard for `profile`, telling time with `clock`.

    Raises `PassphraseNotSetError` when no passphrase guards it, and
    `StoreNotFoundError` when the profile's Gold store does not exist, so a
    dashboard that is unguarded or cannot report refuses to start.
    """
    require_passphrase(profile)
    GoldStore(profile, read_only=True).close()
    app = FastAPI()
    # The htmx script ships in the package: nothing is fetched from the internet.
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    throttle = LoginThrottle()

    @app.exception_handler(RequestValidationError)
    def malformed_address(request: Request, _error: RequestValidationError) -> Response:
        """Explain a malformed address in Danish, never as FastAPI's JSON.

        htmx swaps only a 2xx, so the fragment answers 200 while the page is a 400.
        """
        if request.url.path == "/report":
            fragment = _TEMPLATES.get_template("invalid_address.html").render()
            return HTMLResponse(fragment)
        page = _TEMPLATES.get_template("invalid_address_page.html").render()
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

    @app.get("/")
    def overview(
        request: Request,
        address: Annotated[OverviewAddress, Query()],
    ) -> Response:
        return for_reader(
            request,
            lambda: HTMLResponse(_render_overview(profile, clock, address.asked())),
        )

    @app.get("/report")
    def report(
        request: Request,
        address: Annotated[ReportAddress, Query()],
    ) -> Response:
        return for_reader(
            request,
            lambda: _report_response(profile, address.asked()),
        )

    @app.get("/explanation")
    def explanation(
        request: Request,
        publication: int,
        reference_date: date,
        month: str,
        account: Annotated[list[str] | None, Query()] = None,
    ) -> Response:
        return for_reader(
            request,
            lambda: HTMLResponse(
                _render_explanation(
                    profile, (publication, reference_date), account or (), month
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
                    profile,
                    (address.publication, address.reference_date),
                    address.asked(),
                )
            ),
        )

    @app.get("/login")
    def login_page() -> Response:
        return HTMLResponse(_TEMPLATES.get_template("login.html").render(message=""))

    @app.post("/login")
    def login(passphrase: Annotated[str, Form()] = "") -> Response:
        # One login at a time, from the lock check to recording the outcome.
        with throttle.guard:
            credentials = read_credentials(profile)
            refused = _refuse_login(credentials, throttle, clock(), passphrase)
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
