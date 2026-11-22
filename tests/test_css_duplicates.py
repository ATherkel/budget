# Copyright 2026 Therkel
"""The duplicate CSS check names the existing rule to reuse."""

import re
from pathlib import Path

import pytest

from tests.css_duplicates import (
    find_duplicates,
    find_duplicates_in_sheets,
    read_allowlist,
)

REPOSITORY = Path(__file__).resolve().parents[1]
STATIC = REPOSITORY / "src/budget/dashboard/static"

CARD_AND_PANEL = """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

.panel {
  color: var(--ink);
  margin: 0;
  padding: 1rem;
  border: 1px solid var(--line);
}
"""


def test_a_rule_sharing_three_declarations_names_the_rule_to_reuse() -> None:
    assert find_duplicates(CARD_AND_PANEL) == [
        "`.panel` (line 7) shares 3 declarations with `.card` (line 1); reuse `.card`"
    ]


def test_a_rule_repeating_one_in_an_earlier_stylesheet_names_both_files() -> None:
    layout = """\
a {
  color: var(--ink);
}

.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}
"""
    forms = """\

.panel {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
"""
    sheets = {"layout.css": layout, "forms.css": forms}

    message = (
        "`.panel` (forms.css line 2) shares 3 declarations with"
        " `.card` (layout.css line 5); reuse `.card`"
    )
    assert find_duplicates_in_sheets(sheets) == [message]


def test_a_nested_rule_in_a_stylesheet_names_its_file() -> None:
    sheets = {
        "base.css": "a {\n  color: red;\n}\n",
        "forms.css": ".card {\n  &:hover {\n  }\n}\n",
    }

    message = (
        "`.card` (forms.css line 1) nests a rule;"
        " write it flat so the check can read it"
    )
    assert find_duplicates_in_sheets(sheets) == [message]


def test_rules_sharing_two_declarations_pass() -> None:
    css = """\
.card {
  padding: 1rem;
  color: var(--ink);
  border: 1px solid var(--line);
}

.panel {
  padding: 1rem;
  color: var(--ink);
  border: 2px solid var(--line);
}
"""

    assert find_duplicates(css) == []


def test_an_allowlisted_duplicate_passes() -> None:
    assert find_duplicates(CARD_AND_PANEL, allowlist=[(".panel", ".card")]) == []


def test_comments_are_not_part_of_a_rule() -> None:
    css = """\
/* Cards
   and panels */
.card {
  padding: 1rem; /* roomy */
  border: 1px solid var(--line);
  color: var(--ink);
}

/* A panel { is a card } */
.panel {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
"""

    assert find_duplicates(css) == [
        "`.panel` (line 10) shares 3 declarations with `.card` (line 3); reuse `.card`"
    ]


def test_a_rule_inside_media_is_named_with_its_media_query() -> None:
    css = """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

@media (max-width: 48rem) {
  .panel {
    color: var(--ink);
    padding: 1rem;
    border: 1px solid var(--line);
  }
}
"""

    message = (
        "`@media (max-width: 48rem) .panel` (line 8) shares 3 declarations with"
        " `.card` (line 1); reuse `.card`"
    )
    assert find_duplicates(css) == [message]


def test_an_allowlist_entry_that_is_no_longer_a_duplicate_fails() -> None:
    allowlist = [(".panel", ".card"), (".panel", ".banner")]

    assert find_duplicates(CARD_AND_PANEL, allowlist=allowlist) == [
        "allowlist entry `.panel` / `.banner` is no longer a duplicate; remove it"
    ]


def test_the_allowlist_holds_one_pair_per_line() -> None:
    text = """\
# Duplicates the owner has approved.

.panel | .card
.footer-inner | .page-heading h1, .login-intro h1
"""

    assert read_allowlist(text) == [
        (".panel", ".card"),
        (".footer-inner", ".page-heading h1, .login-intro h1"),
    ]


def linked_stylesheets() -> list[str]:
    """Return the stylesheets the dashboard's base page links, in cascade order."""
    base = (REPOSITORY / "src/budget/dashboard/templates/base.html").read_text("utf-8")
    links = re.finditer(r"""<link rel="stylesheet" href="\{\{ '([^']+)'""", base)
    return [link.group(1) for link in links]


def test_every_dashboard_stylesheet_is_linked_from_the_base_page() -> None:
    # The guard below reads only the linked stylesheets.
    shipped = sorted(path.name for path in STATIC.glob("*.css"))

    assert sorted(linked_stylesheets()) == shipped


def test_the_dashboard_stylesheets_repeat_no_rule_outside_the_allowlist() -> None:
    sheets = {name: (STATIC / name).read_text("utf-8") for name in linked_stylesheets()}
    allowlist = read_allowlist(
        (REPOSITORY / "css-duplicates-allowlist.txt").read_text("utf-8")
    )

    messages = find_duplicates_in_sheets(sheets, allowlist)

    assert not messages, "\n".join(messages)


def test_a_rule_after_a_top_level_statement_is_named_by_its_own_selector() -> None:
    css = """\
@import url("base.css");
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

.panel {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
"""

    assert find_duplicates(css) == [
        "`.panel` (line 8) shares 3 declarations with `.card` (line 2); reuse `.card`"
    ]


def test_a_nested_rule_is_reported_as_unreadable() -> None:
    css = """\
.card {
  padding: 1rem;
  &:hover {
    color: var(--ink);
  }
}
"""

    assert find_duplicates(css) == [
        "`.card` (line 1) nests a rule; write it flat so the check can read it"
    ]


def test_the_rule_sharing_the_most_declarations_is_named_first() -> None:
    css = """\
.card {
  padding: 1rem;
  margin: 0;
  color: var(--ink);
}

.panel {
  padding: 1rem;
  margin: 0;
  color: var(--ink);
  border: 1px solid var(--line);
}

.new {
  padding: 1rem;
  margin: 0;
  color: var(--ink);
  border: 1px solid var(--line);
}
"""

    assert find_duplicates(css) == [
        "`.panel` (line 7) shares 3 declarations with `.card` (line 1); reuse `.card`",
        "`.new` (line 14) shares 4 declarations with `.panel` (line 7); reuse `.panel`",
        "`.new` (line 14) shares 3 declarations with `.card` (line 1); reuse `.card`",
    ]


def test_an_allowlist_line_without_a_pair_is_refused() -> None:
    with pytest.raises(ValueError, match=r"line 2 is not `rule \| earlier rule`: a\|b"):
        read_allowlist("# header\na|b\n")


def test_declarations_match_across_spacing_and_property_case() -> None:
    css = """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

.panel {
  PADDING:1rem;
  border:
    1px  solid var(--line);
  Color : var(--ink)
}
"""

    assert find_duplicates(css) == [
        "`.panel` (line 7) shares 3 declarations with `.card` (line 1); reuse `.card`"
    ]


def test_a_brace_inside_a_string_is_part_of_the_value() -> None:
    css = """\
.new-a {
  color: red;
  padding: 0;
  margin: 0;
  content: "{";
}
.new-b {
  color: red;
  padding: 0;
  margin: 0;
}
"""

    assert find_duplicates(css) == [
        "`.new-b` (line 7) shares 3 declarations with `.new-a` (line 1); reuse `.new-a`"
    ]


def test_a_semicolon_inside_a_string_is_part_of_the_value() -> None:
    css = """\
.quote-a {
  content: "a;b;c;d";
}
.quote-b {
  content: "x;b;c;d";
}
"""

    assert find_duplicates(css) == []


def test_css_the_check_cannot_read_is_reported_with_its_line() -> None:
    css = """\
.card {
  color: red;
  12px;
}
"""

    assert find_duplicates(css) == [
        "`.card` (line 3) holds CSS the check cannot read; fix it so it can"
    ]


def test_the_dashboard_stylesheets_with_a_copied_rule_name_the_original() -> None:
    sheets = {name: (STATIC / name).read_text("utf-8") for name in linked_stylesheets()}
    pattern = re.compile(r"^\.header-inner \{\n(.*?)^\}", re.MULTILINE | re.DOTALL)
    original = next(filter(None, map(pattern.search, sheets.values())), None)
    assert original, "no dashboard stylesheet has a `.header-inner` rule to copy"
    copy = '.copied-header {\n  content: "}";\n' + original.group(1) + "}\n"
    allowlist = read_allowlist(
        (REPOSITORY / "css-duplicates-allowlist.txt").read_text("utf-8")
    )

    messages = find_duplicates_in_sheets({**sheets, "copy.css": copy}, allowlist)

    assert messages, "the copied rule was not reported"
    assert messages[0].startswith("`.copied-header` (copy.css line 1)"), messages
    assert messages[0].endswith("reuse `.header-inner`"), messages
