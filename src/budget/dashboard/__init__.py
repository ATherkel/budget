# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget.dashboard.passphrase import passphrase_matches, set_passphrase
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


def create_app(profile: Profile, *, clock: Callable[[], datetime]) -> FastAPI:
    """Build the dashboard for `profile`, telling time with `clock`."""
    del clock
    app = FastAPI()

    @app.get("/")
    def overview(request: Request) -> Response:
        if SESSION_COOKIE not in request.cookies:
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse("")

    @app.post("/login")
    def login(passphrase: Annotated[str, Form()]) -> Response:
        if not passphrase_matches(profile, passphrase):
            refusal = '<p role="alert">Adgangsfrasen er forkert.</p>'
            return HTMLResponse(_LOGIN_PAGE.format(message=refusal))
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, "1", httponly=True, samesite="strict")
        return response

    return app
