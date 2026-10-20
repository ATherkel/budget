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

from budget.analytics import HouseholdReports, NothingPublishedError, ReportContext
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
    def overview(request: Request) -> Response:
        if not logged_in(request):
            return _send_to_login(request)
        # Every visit renews the login for another 30 days from now.
        return start_session(HTMLResponse(render_overview()))

    @app.get("/report")
    def report(
        request: Request,
        publication: int,
        reference_date: date,
        month: str,
        account: Annotated[list[str], Query()],
    ) -> Response:
        if not logged_in(request):
            return _send_to_login(request)
        # The pinned context, exactly as the page sent it: never re-resolved.
        context = ReportContext(
            publication_id=publication,
            account_ids=frozenset(account),
            month=display.parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(profile, read_only=True) as store:
            answered = HouseholdReports(store).monthly_overview(context).context
        fragment = _TEMPLATES.get_template("report.html").render(
            publication_id=answered.publication_id,
            reference_date=answered.reference_date.isoformat(),
            accounts=" ".join(sorted(answered.account_ids)),
            month=display.month_value(answered.month),
        )
        return start_session(HTMLResponse(fragment))

    def render_overview() -> str:
        """Render a fresh visit: the current publication, today, every account."""
        with GoldStore(profile, read_only=True) as store:
            reports = HouseholdReports(store)
            try:
                publication = reports.current_publication()
            except NothingPublishedError:
                return ""
            reference_date = copenhagen_date(clock())
            options = reports.selection_options(
                publication.publication_id, reference_date
            )
        months = display.months_between(options.first_month, options.last_month)
        return _TEMPLATES.get_template("overview.html").render(
            publication_id=publication.publication_id,
            reference_date=reference_date.isoformat(),
            accounts=options.accounts,
            selected_accounts={account.account_id for account in options.accounts},
            months=[
                (display.month_value(month), display.month_label(month))
                for month in months
            ],
            selected_month=display.month_value(ReportingMonth.of(reference_date)),
        )

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
