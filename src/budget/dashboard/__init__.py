# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable, Collection
from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader, select_autoescape

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    NothingPublishedError,
    PublicationUnavailableError,
    ReportContext,
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

_STATIC = Path(__file__).parent / "static"

_TEMPLATES = Environment(
    loader=PackageLoader("budget.dashboard"),
    autoescape=select_autoescape(),
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
    publication_id: int,
    reference_date: date,
    accounts: Collection[str],
    month: str,
) -> str:
    """Return the complete page address for one pinned selection."""
    return "/?" + urlencode(
        [
            ("publication", publication_id),
            ("reference_date", reference_date.isoformat()),
            *(("account", account) for account in sorted(accounts)),
            ("month", month),
        ]
    )


def _render_overview(
    profile: Profile,
    clock: Callable[[], datetime],
    pin: tuple[int, date] | None,
    accounts: list[str] | None,
    month: str | None,
) -> str:
    """Render the overview page.

    A pinned page keeps its publication, reference date and selection. A fresh
    visit resolves the current publication and today's Copenhagen date, with
    every account and this month selected.
    """
    # A pinned address without accounts is an empty selection, not a fresh visit.
    fresh = pin is None
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
        else set(accounts or ())
    )
    selected_month = month or display.month_value(ReportingMonth.of(reference_date))
    # The page carries its own report, so back, forward and a page without
    # scripts show what the selection's report says.
    report = (
        _render_report(profile, pin, selected_accounts, selected_month)
        if selected_accounts
        else None
    )
    canonical_url = _pinned_url(
        publication_id, reference_date, selected_accounts, selected_month
    )
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


def _render_report(
    profile: Profile,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> str:
    """Render the report fragment a selection asks for, or why it cannot be shown.

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
            overview_report = HouseholdReports(store).monthly_overview(context)
    except InvalidSelectionError as error:
        # A failure is shown, and echoes no context the page could render.
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    except PublicationUnavailableError:
        return _TEMPLATES.get_template("unavailable.html").render()
    answered = overview_report.context
    return _TEMPLATES.get_template("report.html").render(
        is_current=overview_report.publication.is_current,
        publication_id=answered.publication_id,
        reference_date=answered.reference_date.isoformat(),
        accounts=" ".join(sorted(answered.account_ids)),
        month=display.month_value(answered.month),
        month_label=display.month_label(answered.month),
    )


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

    @app.get("/")
    def overview(
        request: Request,
        publication: int | None = None,
        reference_date: date | None = None,
        month: str | None = None,
        account: Annotated[list[str] | None, Query()] = None,
    ) -> Response:
        authenticated_as = _logged_in(request, profile, clock)
        if authenticated_as is None:
            return _send_to_login(request)
        pin = (
            None
            if publication is None or reference_date is None
            else (publication, reference_date)
        )
        # Every visit renews the login for another 30 days from now.
        page = _render_overview(profile, clock, pin, account, month)
        return start_session(HTMLResponse(page), authenticated_as)

    @app.get("/report")
    def report(
        request: Request,
        publication: int,
        reference_date: date,
        month: str,
        account: Annotated[list[str] | None, Query()] = None,
    ) -> Response:
        authenticated_as = _logged_in(request, profile, clock)
        if authenticated_as is None:
            return _send_to_login(request)
        page = _pinned_url(publication, reference_date, account or (), month)
        if not account:
            # An empty selection is a prompt, never a report of nothing.
            prompt = _TEMPLATES.get_template("no_accounts.html").render()
            return start_session(
                HTMLResponse(prompt, headers={"HX-Push-Url": page}),
                authenticated_as,
            )
        # The address becomes this selection's own page, so back and forward
        # reopen each selection the reader made.
        fragment = HTMLResponse(
            _render_report(profile, (publication, reference_date), account, month),
            headers={"HX-Push-Url": page},
        )
        return start_session(fragment, authenticated_as)

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
