# Copyright 2026 Therkel
"""The duplicate CSS check names the existing rule to reuse."""

import re
from pathlib import Path

import pytest

from tests.css_duplicates import find_duplicates, read_allowlist, report_overlaps

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


def test_a_cross_file_overlap_reports_both_locations_and_shared_declarations(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.css"
    base.write_text(
        """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}
""",
        encoding="utf-8",
    )
    feature = tmp_path / "feature.css"
    feature.write_text(
        """\
.panel {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
""",
        encoding="utf-8",
    )

    report = report_overlaps((base, feature))

    assert [
        (
            finding.earlier.path.name,
            finding.earlier.line,
            finding.earlier.selector,
            finding.later.path.name,
            finding.later.line,
            finding.later.selector,
            finding.declarations,
        )
        for finding in report.findings
    ] == [
        (
            "base.css",
            1,
            ".card",
            "feature.css",
            1,
            ".panel",
            (
                "border: 1px solid var(--line)",
                "color: var(--ink)",
                "padding: 1rem",
            ),
        )
    ]


def test_an_overlap_inside_a_media_query_retains_its_grouping_context(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.css"
    base.write_text(
        """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}
""",
        encoding="utf-8",
    )
    responsive = tmp_path / "responsive.css"
    responsive.write_text(
        """\
@media (max-width: 48rem) {
  .panel {
    color: var(--ink);
    padding: 1rem;
    border: 1px solid var(--line);
  }
}
""",
        encoding="utf-8",
    )

    report = report_overlaps((base, responsive))

    assert [
        (finding.earlier.context, finding.later.context) for finding in report.findings
    ] == [("", "@media (max-width: 48rem)")]


def test_declaration_identity_preserves_case_and_string_whitespace_but_normalizes_names(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.css"
    base.write_text(
        """\
.base {
  color: RED;
  --Tone: value;
  content: "a  b";
  padding: 1rem;
  border:
    1px  solid var(--line);
  display: block;
}
""",
        encoding="utf-8",
    )
    variant = tmp_path / "variant.css"
    variant.write_text(
        """\
.variant {
  COLOR: red;
  --tone: value;
  content: "a b";
  PADDING: 1rem;
  border: 1px solid var(--line);
  DISPLAY:block;
}
""",
        encoding="utf-8",
    )

    report = report_overlaps((base, variant))

    assert report.findings[0].declarations == (
        "border: 1px solid var(--line)",
        "display: block",
        "padding: 1rem",
    )


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


def test_app_css_with_a_copied_rule_names_the_original() -> None:
    css = (REPOSITORY / "src/budget/dashboard/static/app.css").read_text("utf-8")
    original = re.search(r"^\.header-inner \{\n(.*?)^\}", css, re.MULTILINE | re.DOTALL)
    assert original, "app.css no longer has a `.header-inner` rule to copy"
    copy = '.copied-header {\n  content: "}";\n' + original.group(1) + "}\n"
    allowlist = read_allowlist(
        (REPOSITORY / "css-duplicates-allowlist.txt").read_text("utf-8")
    )

    messages = find_duplicates(css + "\n" + copy, allowlist)

    assert messages, "the copied rule was not reported"
    assert messages[0].startswith("`.copied-header` (line "), messages
    assert messages[0].endswith("reuse `.header-inner`"), messages
