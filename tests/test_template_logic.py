# Copyright 2026 Therkel
"""Dashboard templates hold no logic, except spots the allowlist names."""

from pathlib import Path

from budget.dashboard import FEATURES, jinja_environment
from tests.template_logic import gate

ENVIRONMENT = jinja_environment(FEATURES)
ALLOWLIST_HEADER = "# Temporary allowances, each with the issue that removes it.\n"


def templates(tmp_path: Path, pages: dict[str, str]) -> Path:
    """Write each page of `pages` under a templates folder and return the folder."""
    root = tmp_path / "templates"
    for name, text in pages.items():
        page = root / name
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(text, encoding="utf-8")
    return root


def allowlist(tmp_path: Path, entries: str = "") -> Path:
    """Write an allowlist holding the header comment and `entries`."""
    path = tmp_path / "allowlist.toml"
    path.write_text(ALLOWLIST_HEADER + entries, encoding="utf-8")
    return path


def test_each_branch_of_an_if_is_reported_with_its_file_and_line(
    tmp_path: Path,
) -> None:
    root = templates(
        tmp_path,
        {
            "cards/card.html": (
                "<p>{{ card.title }}</p>\n"
                "{% if card.open %}open\n"
                "{% elif card.closed %}closed\n"
                "{% else %}unknown{% endif %}\n"
            )
        },
    )

    assert gate(ENVIRONMENT, root, allowlist(tmp_path)) == [
        "cards/card.html:2: `if` in {% if card.open %} is not on the allowlist",
        "cards/card.html:3: `elif` in {% elif card.closed %} is not on the allowlist",
        "cards/card.html:4: `else` in {% else %} is not on the allowlist",
    ]


def test_a_set_is_reported(tmp_path: Path) -> None:
    root = templates(
        tmp_path,
        {"page.html": "{% set label = card.title %}\n<p>{{ label }}</p>\n"},
    )

    assert gate(ENVIRONMENT, root, allowlist(tmp_path)) == [
        "page.html:1: `set` in {% set label = card.title %} is not on the allowlist",
    ]
