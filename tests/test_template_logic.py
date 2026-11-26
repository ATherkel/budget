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


@pytest.mark.parametrize(
    ("tag", "closing", "name"),
    [
        ("{{ note | safe }}", "", "safe"),
        ("{{ row.kind | capitalize }}", "", "capitalize"),
        ("{{ row.name | default('-') }}", "", "default"),
        ("{% for row in rows | sort %}", "{% endfor %}", "sort"),
        ("{% filter upper %}", "{% endfilter %}", "upper"),
    ],
)
def test_a_filter_other_than_budgets_own_or_xmlattr_is_reported(
    tmp_path: Path, tag: str, closing: str, name: str
) -> None:
    allowed = (
        "<p{{ card.attributes | xmlattr }}>{{ row.amount | amount }}</p>"
        "<p>{{ row.day | danish_date }}</p>"
    )
    root = templates(tmp_path, {"page.html": f"{allowed}\n{tag}x{closing}\n"})

    assert gate(ENVIRONMENT, root, allowlist(tmp_path)) == [
        f"page.html:2: `filter {name}` in {tag} is not on the allowlist",
    ]


def allowance(path: str, tag: str, issue: str = "issue = 627\n") -> str:
    """Return one allowlist entry for `tag` in `path`."""
    return (
        "\n[[allowance]]\n"
        f"path = {path!r}\n"
        f"tag = {tag!r}\n"
        "reason = 'Moves into Python with the notices.'\n"
        f"{issue}"
    )


def test_a_spot_on_the_allowlist_is_not_reported(tmp_path: Path) -> None:
    root = templates(
        tmp_path,
        {"cards/card.html": "{% if card.open %}\n  open\n{%   endif %}\n"},
    )
    listed = allowlist(tmp_path, allowance("cards/card.html", "{% if card.open %}"))

    assert gate(ENVIRONMENT, root, listed) == []


def test_each_repeat_of_a_spot_needs_its_own_entry(tmp_path: Path) -> None:
    root = templates(
        tmp_path,
        {
            "page.html": (
                "{% for row in rows %}{{ row.name }}{% else %}none{% endfor %}\n"
                "{% for row in more %}{{ row.name }}{% else %}none{% endfor %}\n"
            )
        },
    )
    listed = allowlist(tmp_path, allowance("page.html", "{% else %}"))

    assert gate(ENVIRONMENT, root, listed) == [
        "page.html:2: `else` in {% else %} is not on the allowlist",
    ]


def test_an_entry_that_matches_nothing_is_reported_as_stale(tmp_path: Path) -> None:
    root = templates(tmp_path, {"cards/card.html": "<p>{{ card.title }}</p>\n"})
    listed = allowlist(tmp_path, allowance("cards/card.html", "{% if card.open %}"))

    assert gate(ENVIRONMENT, root, listed) == [
        "allowlist: the entry for {% if card.open %} in cards/card.html"
        " matches nothing; remove it",
    ]


@pytest.mark.parametrize("issue", ["", "issue = 'soon'\n", "issue = 0\n"])
def test_an_entry_without_an_issue_number_is_reported(
    tmp_path: Path, issue: str
) -> None:
    root = templates(tmp_path, {"cards/card.html": "{% if card.open %}x{% endif %}\n"})
    listed = allowlist(
        tmp_path, allowance("cards/card.html", "{% if card.open %}", issue)
    )

    assert gate(ENVIRONMENT, root, listed) == [
        "allowlist: the entry for {% if card.open %} in cards/card.html"
        " names no issue that removes it",
    ]
