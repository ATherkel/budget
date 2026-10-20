# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, PackageLoader, select_autoescape

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    NothingPublishedError,
    ReportContext,
)
from budget.dashboard import display, session
from budget.dashboard.display import copenhagen_date
from budget.dashboard.passphrase import (
    passphrase_matches,
    session_key,
    set_passphrase,
)
from budget.dashboard.throttle import LoginThrottle
from budget.gold import ReportingMonth
from budget.gold.store import GoldStore
from budget.profiles import Profile

__all__ = ["create_app", "set_passphrase"]

SESSION_COOKIE = "session"

_TEMPLATES = Environment(
    loader=PackageLoader("budget.dashboard"),
    autoescape=select_autoescape(),
)

_LOGIN_PAGE = """<!doctype html>
<html lang="da">
<meta charset="utf-8">
<title>Log ind</title>
{message}
<form method="post" action="/login">
<label>Adgangsfrase <input type="password" name="passphrase" autofocus></label>
<button>Log ind</button>
</form>
</html>
"""


def _send_to_login(request: Request) -> Response:
    """Send a reader who is not logged in to the login page.

    A page is redirected. An htmx fragment gets 401 and `HX-Redirect`, so htmx
    moves the whole page to login rather than painting it into a panel.
    """
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


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
                return ""
            pin = (publication_id, copenhagen_date(clock()))
        publication_id, reference_date = pin
        options = reports.selection_options(publication_id, reference_date)
    months = display.months_between(options.first_month, options.last_month)
    return _TEMPLATES.get_template("overview.html").render(
        publication_id=publication_id,
        reference_date=reference_date.isoformat(),
        accounts=options.accounts,
        selected_accounts=(
            {account.account_id for account in options.accounts}
            if fresh
            else set(accounts or ())
        ),
        months=[
            (display.month_value(month), display.month_label(month)) for month in months
        ],
        selected_month=month or display.month_value(ReportingMonth.of(reference_date)),
    )


def _render_report(profile: Profile, context: ReportContext) -> str:
    """Render the report fragment `context` asks for, or why it cannot be shown."""
    try:
        with GoldStore(profile, read_only=True) as store:
            overview_report = HouseholdReports(store).monthly_overview(context)
    except InvalidSelectionError as error:
        # A failure is shown, and echoes no context the page could render.
        return _TEMPLATES.get_template("invalid_selection.html").render(
            problems=display.selection_problems(error)
        )
    answered = overview_report.context
    return _TEMPLATES.get_template("report.html").render(
        is_current=overview_report.publication.is_current,
        publication_id=answered.publication_id,
        reference_date=answered.reference_date.isoformat(),
        accounts=" ".join(sorted(answered.account_ids)),
        month=display.month_value(answered.month),
    )


def create_app(profile: Profile, *, clock: Callable[[], datetime]) -> FastAPI:
    """Build the dashboard for `profile`, telling time with `clock`."""
    app = FastAPI()
    throttle = LoginThrottle()

    def start_session(response: Response) -> Response:
        """Set a session cookie lasting `LOGIN_LIFETIME` from now."""
        response.set_cookie(
            SESSION_COOKIE,
            session.issue(session_key(profile), clock()),
            httponly=True,
            samesite="strict",
        )
        return response

    def logged_in(request: Request) -> bool:
        cookie = request.cookies.get(SESSION_COOKIE)
        return cookie is not None and session.is_valid(
            session_key(profile), cookie, clock()
        )

    @app.get("/")
    def overview(
        request: Request,
        publication: int | None = None,
        reference_date: date | None = None,
        month: str | None = None,
        account: Annotated[list[str] | None, Query()] = None,
    ) -> Response:
        if not logged_in(request):
            return _send_to_login(request)
        pin = (
            None
            if publication is None or reference_date is None
            else (publication, reference_date)
        )
        # Every visit renews the login for another 30 days from now.
        page = _render_overview(profile, clock, pin, account, month)
        return start_session(HTMLResponse(page))

    @app.get("/report")
    def report(
        request: Request,
        publication: int,
        reference_date: date,
        month: str,
        account: Annotated[list[str] | None, Query()] = None,
    ) -> Response:
        if not logged_in(request):
            return _send_to_login(request)
        if not account:
            # An empty selection is a prompt, never a report of nothing.
            prompt = _TEMPLATES.get_template("no_accounts.html").render()
            return start_session(HTMLResponse(prompt))
        # The pinned context, exactly as the page sent it: never re-resolved.
        context = ReportContext(
            publication_id=publication,
            account_ids=frozenset(account),
            month=display.parse_month(month),
            reference_date=reference_date,
        )
        return start_session(HTMLResponse(_render_report(profile, context)))

    @app.post("/login")
    def login(passphrase: Annotated[str, Form()]) -> Response:
        now = clock()
        wait = throttle.seconds_locked(now)
        if wait:
            notice = (
                '<p role="alert">For mange forkerte forsøg. '
                f"Prøv igen om {wait} sekunder.</p>"
            )
            return HTMLResponse(
                _LOGIN_PAGE.format(message=notice),
                status_code=429,
                headers={"Retry-After": str(wait)},
            )
        if not passphrase_matches(profile, passphrase):
            throttle.failed(now)
            refusal = '<p role="alert">Adgangsfrasen er forkert.</p>'
            return HTMLResponse(_LOGIN_PAGE.format(message=refusal))
        throttle.succeeded()
        return start_session(RedirectResponse("/", status_code=303))

    @app.post("/logout")
    def logout() -> Response:
        # This browser only; `set-passphrase` logs out every device.
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
        return response

    return app
