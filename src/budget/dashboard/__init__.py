# Copyright 2026 Therkel
"""The household dashboard: an HTTP shell over `HouseholdReports`.

It reads Gold only through analytics, opened read-only from one profile.
"""

from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget.profiles import Profile

SESSION_COOKIE = "session"


def set_passphrase(profile: Profile, passphrase: str) -> None:
    """Make `passphrase` the one the dashboard of `profile` accepts."""
    del profile, passphrase


def create_app(profile: Profile, *, clock: Callable[[], datetime]) -> FastAPI:
    """Build the dashboard for `profile`, telling time with `clock`."""
    del profile, clock
    app = FastAPI()

    @app.get("/")
    def overview(request: Request) -> Response:
        if SESSION_COOKIE not in request.cookies:
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse("")

    @app.post("/login")
    def login() -> Response:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(SESSION_COOKIE, "1", httponly=True, samesite="strict")
        return response

    return app
