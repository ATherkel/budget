# Copyright 2026 Therkel
"""The login page (`/login`) and logging out (`/logout`)."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment

from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.login.throttle import LoginThrottle
from budget.dashboard.passphrase import CredentialSnapshot, read_credentials
from budget.dashboard.session import SESSION_COOKIE


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
            templates.get_template("login/login.html").render(message=notice),
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    # An empty form is not a guess, so it is refused without being counted.
    blank = not passphrase.strip()
    if blank or not credentials.matches(passphrase):
        if not blank:
            throttle.failed(now)
        return HTMLResponse(
            templates.get_template("login/login.html").render(
                message="Adgangskoden er forkert."
            )
        )
    throttle.succeeded()
    return None


def _register(dashboard: Dashboard) -> None:
    """Serve logging in at `/login` and logging out at `/logout`."""
    throttle = LoginThrottle()
    templates = dashboard.templates

    @dashboard.app.get("/login")
    def login_page() -> Response:
        page = templates.get_template("login/login.html")
        return HTMLResponse(page.render(message=""))

    @dashboard.app.post("/login")
    def login(passphrase: Annotated[str, Form()] = "") -> Response:
        # One login at a time, from the lock check to recording the outcome.
        with throttle.guard:
            credentials = read_credentials(dashboard.profile)
            refused = _refuse_login(
                templates, credentials, throttle, dashboard.clock(), passphrase
            )
        if refused is not None:
            return refused
        return dashboard.start_session(
            RedirectResponse("/", status_code=303), credentials
        )

    @dashboard.app.post("/logout")
    def logout() -> Response:
        # This browser only; `set-passphrase` logs out every device.
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")
        return response


LOGIN = Feature(folder=Path(__file__).parent, register=_register)
