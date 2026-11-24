# Copyright 2026 Therkel
"""A feature that only serves one page, to show how a feature plugs in."""

from pathlib import Path

from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from budget.dashboard.features import Dashboard, Feature


def register(dashboard: Dashboard) -> None:
    """Serve the sample page at `/sample` to a logged-in reader."""

    @dashboard.app.get("/sample")
    def sample(request: Request) -> Response:
        page = dashboard.templates.get_template("sample_feature/page.html")
        return dashboard.for_reader(request, lambda: HTMLResponse(page.render()))


SAMPLE = Feature(folder=Path(__file__).parent, register=register)
