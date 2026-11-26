# Copyright 2026 Therkel
"""The error pages: why an address, a selection or a publication shows nothing."""

from pathlib import Path

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from jinja2.environment import TemplateModule

from budget.analytics import InvalidSelectionError, PublicationUnavailableError
from budget.dashboard.display.text import selection_problems
from budget.dashboard.features import Dashboard, Feature


def failure_fragment(
    dashboard: Dashboard,
    error: InvalidSelectionError | PublicationUnavailableError,
) -> TemplateModule:
    """Return the fragment saying why a selection's figures cannot be shown.

    A failure is shown, and echoes no context the page could render. A page
    that embeds the rendered fragment shows it as markup, never escaped again.
    """
    if isinstance(error, InvalidSelectionError):
        page = dashboard.templates.get_template("errors/invalid_selection.html")
        return page.make_module({"problems": selection_problems(error)})
    return dashboard.templates.get_template("errors/unavailable.html").make_module()


def _register(dashboard: Dashboard) -> None:
    """Explain a malformed address in Danish on every page."""
    templates = dashboard.templates

    @dashboard.app.exception_handler(RequestValidationError)
    def malformed_address(request: Request, _error: RequestValidationError) -> Response:
        """Explain a malformed address in Danish, never as FastAPI's JSON.

        htmx swaps only a 2xx, so the fragment answers 200 while the page is a 400.
        """
        if request.url.path == "/report":
            fragment = templates.get_template("errors/invalid_address.html").render()
            return HTMLResponse(fragment)
        page = templates.get_template("errors/invalid_address_page.html").render()
        return HTMLResponse(page, status_code=400)


ERRORS = Feature(folder=Path(__file__).parent, register=_register)
