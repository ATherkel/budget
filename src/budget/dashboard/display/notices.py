# Copyright 2026 Therkel
"""A page's optional parts, as a list of notices its template loops over.

A page shows a notice only when Python puts it in the list, so the template
holds no condition. It renders each one with `{% include notice.template %}`,
which sees the page's own values beside `notice`.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from budget.analytics import ReportPublication

# The template of every notice of the shared shape; it calls `notice_section`.
_SHARED = "notice.html"


@dataclass(frozen=True)
class Paragraph:
    """One paragraph of a shared notice: its text and its element's attributes."""

    text: str
    # Rendered with `xmlattr`, which leaves out an attribute whose value is None.
    attributes: dict[str, str | None]


@dataclass(frozen=True)
class Notice:
    """One optional part of a page and the template that renders it.

    A notice of the shared shape names its section, heading and paragraphs; a
    notice of its own template reads what it needs from the page.
    """

    template: str
    name: str = ""
    heading: str = ""
    paragraphs: tuple[Paragraph, ...] = ()


def section(name: str, heading: str, paragraphs: Iterable[Paragraph]) -> Notice:
    """Return a notice of the shared shape: a titled section of paragraphs."""
    return Notice(_SHARED, name, heading, tuple(paragraphs))


def shown(*parts: tuple[bool, Notice]) -> tuple[Notice, ...]:
    """Return the notice of each `(show, notice)` pair that is shown, in order."""
    return tuple(notice for show, notice in parts if show)


def newer_figures(publication: ReportPublication) -> tuple[Notice, ...]:
    """Return the notice that newer figures exist, unless `publication` is current."""
    return shown((not publication.is_current, Notice("newer_figures.html")))
