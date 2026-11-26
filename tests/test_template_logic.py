# Copyright 2026 Therkel
"""Dashboard templates hold no logic, except spots the allowlist names."""

from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("tag", "construct"),
    [
        ("{{ rows == 0 }}", "comparison"),
        ("{{ row.kind not in kinds }}", "comparison"),
        ("{{ row.open and row.late }}", "and"),
        ("{{ row.open or row.late }}", "or"),
        ("{{ not row.open }}", "not"),
        ("{{ row.amount + 1 }}", "arithmetic"),
        ("{{ row.amount * 2 }}", "arithmetic"),
        ("{{ -row.amount }}", "arithmetic"),
        ("{{ row.name ~ ':' }}", "~"),
        ("{{ row.name if row.open else '' }}", "inline if"),
        ("{{ row.name is defined }}", "is"),
        ("{{ row_card(row.amount > 0) }}", "comparison"),
        ("{% for row in rows + extra %}", "arithmetic"),
        ("{% include 'cards/' ~ row.kind %}", "~"),
    ],
)
def test_an_expression_with_logic_is_reported(
    tmp_path: Path, tag: str, construct: str
) -> None:
    closing = "{% endfor %}" if tag.startswith("{% for") else ""
    root = templates(tmp_path, {"page.html": f"<p>{tag}</p>{closing}\n"})

    assert gate(ENVIRONMENT, root, allowlist(tmp_path)) == [
        f"page.html:1: `{construct}` in {tag} is not on the allowlist",
    ]


def test_a_for_that_filters_its_rows_is_reported(tmp_path: Path) -> None:
    tag = "{% for row in rows if row.open %}"
    root = templates(
        tmp_path, {"page.html": f"{tag}{{{{ row.name }}}}{{% endfor %}}\n"}
    )

    assert gate(ENVIRONMENT, root, allowlist(tmp_path)) == [
        f"page.html:1: `for ... if` in {tag} is not on the allowlist",
    ]
