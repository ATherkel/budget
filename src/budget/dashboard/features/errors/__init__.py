# Copyright 2026 Therkel
"""The error pages: why an address, a selection or a publication shows nothing."""

from pathlib import Path

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse

from budget.dashboard.features import Dashboard, Feature


def _register(dashboard: Dashboard) -> None:
    """Explain a malformed address in Danish on every page."""
    templates = dashboard.templates

    @dashboard.app.exception_handler(RequestValidationError)
    def malformed_address(request: Request, _error: RequestValidationError) -> Response:
        """Explain a malformed address in Danish, never as FastAPI's JSON.

        htmx swaps only a 2xx, so the fragment answers 200 while the page is a 400.
        """
        if request.url.path == "/report":
            fragment = templates.get_template("invalid_address.html").render()
            return HTMLResponse(fragment)
        page = templates.get_template("invalid_address_page.html").render()
        return HTMLResponse(page, status_code=400)


ERRORS = Feature(folder=Path(__file__).parent, register=_register)
