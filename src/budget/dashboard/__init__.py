# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget.dashboard import session
from budget.dashboard.passphrase import (
    passphrase_matches,
    session_key,
    set_passphrase,
)
from budget.profiles import Profile

__all__ = ["create_app", "set_passphrase"]

SESSION_COOKIE = "session"

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

    def start_session(response: Response) -> Response:
        """Set a session cookie lasting `LOGIN_LIFETIME` from now."""
        response.set_cookie(
            SESSION_COOKIE,
            session.issue(session_key(profile), clock()),
            httponly=True,
            samesite="strict",
        )
        return response

    @app.get("/")
    def overview(request: Request) -> Response:
        cookie = request.cookies.get(SESSION_COOKIE)
        if cookie is None or not session.is_valid(
            session_key(profile), cookie, clock()
        ):
            return _send_to_login(request)
        # Every visit renews the login for another 30 days from now.
        return start_session(HTMLResponse(""))

    @app.post("/login")
    def login(passphrase: Annotated[str, Form()]) -> Response:
        if not passphrase_matches(profile, passphrase):
            refusal = '<p role="alert">Adgangsfrasen er forkert.</p>'
            return HTMLResponse(_LOGIN_PAGE.format(message=refusal))
        return start_session(RedirectResponse("/", status_code=303))

    return app
