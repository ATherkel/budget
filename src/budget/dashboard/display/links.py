# Copyright 2026 Therkel
"""A row of links where the current choice is marked, as `switch_link` renders it."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SwitchLink:
    """One choice in a row of links: its label and its anchor's attributes."""

    label: str
    # Rendered with `xmlattr`, which leaves out an attribute whose value is None.
    attributes: dict[str, str | None]


def switch_links(
    current: str, choices: Iterable[tuple[str, str, str, str]]
) -> list[SwitchLink]:
    """Return one link per `(value, id, href, label)`, marking `current` the page."""
    return [
        SwitchLink(
            label,
            {
                "id": link_id,
                "href": href,
                "aria-current": "page" if value == current else None,
            },
        )
        for value, link_id, href, label in choices
    ]
