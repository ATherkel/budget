# Copyright 2026 Therkel
"""The duplicate CSS check names the existing rule to reuse."""

from pathlib import Path

import pytest

from tests.css_duplicates import (
    find_duplicates,
    find_duplicates_in_sheets,
    read_allowlist,
)

REPOSITORY = Path(__file__).resolve().parents[1]

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


def test_app_css_repeats_no_rule_outside_the_allowlist() -> None:
    css = (REPOSITORY / "src/budget/dashboard/static/app.css").read_text("utf-8")
    allowlist = read_allowlist(
        (REPOSITORY / "css-duplicates-allowlist.txt").read_text("utf-8")
    )

    messages = find_duplicates(css, allowlist)

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
