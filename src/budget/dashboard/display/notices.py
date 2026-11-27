# Copyright 2026 Therkel
"""A page's optional parts, as a list of notices its template loops over.

A page shows a notice only when Python puts it in the list, so the template
holds no condition. It renders each one with `{% include notice.template %}`,
which sees the page's own values beside `notice`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Notice:
    """One optional part of a page and the template that renders it.

    A notice of its own template reads what it needs from the page.
    """

    template: str


def shown(*parts: tuple[bool, Notice]) -> tuple[Notice, ...]:
    """Return the notice of each `(show, notice)` pair that is shown, in order."""
    return tuple(notice for show, notice in parts if show)


def newer_figures(is_current: bool) -> tuple[Notice, ...]:
    """Return the notice that newer figures exist, unless these are the newest."""
    return shown((not is_current, Notice("newer_figures.html")))
