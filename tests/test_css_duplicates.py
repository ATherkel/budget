# Copyright 2026 Therkel
"""The CSS overlap advisory reports shared declarations and analysis failures."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.cli.processes import explicit_environment
from tests.css_duplicates import (
    Diagnostic,
    Location,
    Overlap,
    Report,
    discover_stylesheets,
    format_diagnostics,
    format_report,
    report_dashboard,
    report_overlaps,
)

REPOSITORY = Path(__file__).resolve().parents[1]


def report_css(tmp_path: Path, css: str) -> Report:
    """Return the overlap report for one temporary stylesheet."""
    path = tmp_path / "styles.css"
    path.write_text(css, encoding="utf-8")
    return report_overlaps((path,))


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


def test_parse_and_unsupported_syntax_failures_are_separate_diagnostics(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.css"
    base.write_text(
        """\
.base {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}
""",
        encoding="utf-8",
    )
    copy = tmp_path / "copy.css"
    copy.write_text(
        """\
.copy {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
""",
        encoding="utf-8",
    )
    broken = tmp_path / "broken.css"
    broken.write_text(".broken { color red; }\n", encoding="utf-8")
    nested = tmp_path / "nested.css"
    nested.write_text(
        ".outer { color: red; &:hover { color: blue; } }\n",
        encoding="utf-8",
    )
    unknown = tmp_path / "unknown.css"
    unknown.write_text(
        "@unknown feature { .child { color: red; } }\n",
        encoding="utf-8",
    )

    report = report_overlaps((base, copy, broken, nested, unknown))

    assert (
        [
            (finding.earlier.path.name, finding.later.path.name)
            for finding in report.findings
        ],
        [
            (diagnostic.path.name, diagnostic.line, diagnostic.message)
            for diagnostic in report.diagnostics
        ],
    ) == (
        [("base.css", "copy.css")],
        [
            (
                "broken.css",
                1,
                "parse error: Stop token reached before {} block for a qualified rule.",
            ),
            ("nested.css", 1, "unsupported nested rule inside `.outer`"),
            ("unknown.css", 1, "unsupported at-rule block `@unknown feature`"),
        ],
    )


@pytest.mark.parametrize(
    ("css", "message"),
    [
        (
            ".a { color: red); padding: 1rem; margin: 0; }",
            "parse error: Unmatched )",
        ),
        (
            ".a { color: var(--x, red]); padding: 1rem; margin: 0; }",
            "parse error: Unmatched ]",
        ),
        (
            ".a { background: url(a b); padding: 1rem; margin: 0; }",
            "parse error: bad URL token",
        ),
        (
            ".a] { padding: 1rem; margin: 0; color: red; }",
            "parse error: Unmatched ]",
        ),
        ("@import url(a b);", "parse error: bad URL token"),
        ("@layer foo];", "parse error: Unmatched ]"),
    ],
)
def test_token_errors_in_preludes_and_value_blocks_are_diagnostics(
    tmp_path: Path,
    css: str,
    message: str,
) -> None:
    base = tmp_path / "base.css"
    base.write_text(
        """\
.base {
  padding: 1rem;
  margin: 0;
  color: red;
}
""",
        encoding="utf-8",
    )
    copy = tmp_path / "copy.css"
    copy.write_text(
        """\
.copy {
  color: red;
  padding: 1rem;
  margin: 0;
}
""",
        encoding="utf-8",
    )
    broken = tmp_path / "broken.css"
    broken.write_text(css + "\n", encoding="utf-8")

    report = report_overlaps((base, copy, broken))

    assert (
        [
            (finding.earlier.path.name, finding.later.path.name)
            for finding in report.findings
        ],
        [
            (diagnostic.path.name, diagnostic.line, diagnostic.message)
            for diagnostic in report.diagnostics
        ],
    ) == ([("base.css", "copy.css")], [("broken.css", 1, message)])


def test_dashboard_stylesheet_discovery_is_recursive_and_deterministic(
    tmp_path: Path,
) -> None:
    feature = tmp_path / "features" / "planning" / "chart.css"
    feature.parent.mkdir(parents=True)
    feature.write_text(".chart { color: red; }\n", encoding="utf-8")
    component = tmp_path / "static" / "app.css"
    component.parent.mkdir()
    component.write_text(".app { color: blue; }\n", encoding="utf-8")
    (tmp_path / "README.txt").write_text("not CSS\n", encoding="utf-8")

    assert tuple(
        path.relative_to(tmp_path).as_posix() for path in discover_stylesheets(tmp_path)
    ) == ("features/planning/chart.css", "static/app.css")


def test_a_stylesheet_given_twice_is_analysed_once(tmp_path: Path) -> None:
    stylesheet = tmp_path / "styles.css"
    stylesheet.write_text(
        ".card { padding: 1rem; margin: 0; color: red; }\n", encoding="utf-8"
    )

    assert report_overlaps((stylesheet, stylesheet)) == Report(
        findings=(), diagnostics=()
    )


def test_a_report_without_findings_asks_for_no_review() -> None:
    assert format_report(Report(findings=(), diagnostics=())) == (
        "CSS declaration overlap advisory: 0 findings\n"
    )


def test_dashboard_css_analyses_without_errors() -> None:
    report = report_dashboard()

    assert report.diagnostics == (), format_diagnostics(report)


def test_report_paths_inside_the_repository_are_relative() -> None:
    stylesheet = REPOSITORY / "src" / "budget" / "dashboard" / "static" / "app.css"
    report = Report(
        findings=(
            Overlap(
                later=Location(path=stylesheet, line=9, selector=".copy"),
                earlier=Location(path=stylesheet, line=1, selector=".card"),
                declarations=("color: red", "margin: 0", "padding: 0"),
            ),
        ),
        diagnostics=(
            Diagnostic(path=stylesheet, line=4, message="parse error: Unmatched )"),
        ),
    )

    assert (format_report(report), format_diagnostics(report)) == (
        (
            "CSS declaration overlap advisory: 1 finding\n"
            "- src/budget/dashboard/static/app.css:1 `.card`\n"
            "  with src/budget/dashboard/static/app.css:9 `.copy`\n"
            "  shared declarations:\n"
            "    color: red\n"
            "    margin: 0\n"
            "    padding: 0\n"
            "\n"
            "Review the overlap and decide how these rules should be maintained.\n"
        ),
        (
            "CSS analysis error: src/budget/dashboard/static/app.css:4: "
            "parse error: Unmatched )\n"
        ),
    )


@pytest.mark.parametrize("property_name", ["--x", "font-family"])
def test_tokens_separated_by_a_comment_are_not_one_value(
    tmp_path: Path, property_name: str
) -> None:
    report = report_css(
        tmp_path,
        f"""\
.split {{ {property_name}: a/**/b; padding: 0; margin: 0; }}
.joined {{ {property_name}: ab; padding: 0; margin: 0; }}
""",
    )

    assert report == Report(findings=(), diagnostics=())


def test_a_dashboard_root_without_stylesheets_is_a_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "moved-dashboard"

    report = report_dashboard(root)

    assert report == Report(
        findings=(),
        diagnostics=(Diagnostic(path=root, line=None, message="no stylesheets found"),),
    )


def test_executable_reports_overlap_and_succeeds(tmp_path: Path) -> None:
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

    result = subprocess.run(
        [sys.executable, "-m", "tests.css_duplicates", str(base), str(feature)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPOSITORY,
        env=explicit_environment(),
    )

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        (
            "CSS declaration overlap advisory: 1 finding\n"
            f"- {base}:1 `.card`\n"
            f"  with {feature}:1 `.panel`\n"
            "  shared declarations:\n"
            "    border: 1px solid var(--line)\n"
            "    color: var(--ink)\n"
            "    padding: 1rem\n"
            "\n"
            "Review the overlap and decide how these rules should be maintained.\n"
        ),
        "",
    )


def test_executable_reports_a_read_failure_and_exits_nonzero(tmp_path: Path) -> None:
    stylesheet = tmp_path / "styles.css"
    stylesheet.write_text(
        """\
.card {
  padding: 1rem;
  border: 1px solid var(--line);
  color: var(--ink);
}

.copy {
  color: var(--ink);
  padding: 1rem;
  border: 1px solid var(--line);
}
""",
        encoding="utf-8",
    )
    missing = tmp_path / "missing.css"

    result = subprocess.run(
        [sys.executable, "-m", "tests.css_duplicates", str(stylesheet), str(missing)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPOSITORY,
        env=explicit_environment(),
    )

    assert (
        result.returncode,
        "CSS declaration overlap advisory: 1 finding" in result.stdout,
        result.stderr,
    ) == (
        1,
        True,
        f"CSS analysis error: {missing}: cannot read stylesheet: file not found\n",
    )


def test_an_ordinary_pytest_run_displays_the_overlap_advisory() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_css_duplicates.py::test_rules_sharing_two_declarations_do_not_form_a_finding",
            "-q",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPOSITORY,
        env=explicit_environment(),
    )

    finding = re.search(
        r"^- \S+app\.css:\d+ `\.header-inner`\n"
        r"  with \S+app\.css:\d+ `\.footer-inner`\n"
        r"  shared declarations:\n"
        r"    display: flex\n"
        r"    gap: 1rem\n"
        r"    justify-content: space-between$",
        result.stdout,
        re.MULTILINE,
    )
    assert (result.returncode, bool(finding)) == (0, True), result.stdout


def test_rules_sharing_two_declarations_do_not_form_a_finding(
    tmp_path: Path,
) -> None:
    report = report_css(
        tmp_path,
        """\
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
""",
    )

    assert report.findings == ()


def test_comments_are_not_part_of_a_rule(tmp_path: Path) -> None:
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

    report = report_css(tmp_path, css)

    assert [
        (finding.earlier.line, finding.later.line) for finding in report.findings
    ] == [(3, 10)]


def test_a_rule_after_a_top_level_statement_keeps_its_own_selector(
    tmp_path: Path,
) -> None:
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

    report = report_css(tmp_path, css)

    assert [
        (finding.earlier.line, finding.later.line) for finding in report.findings
    ] == [(2, 8)]


def test_overlap_pair_order_is_deterministic(tmp_path: Path) -> None:
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

    report = report_css(tmp_path, css)

    assert [
        (finding.later.selector, finding.earlier.selector)
        for finding in report.findings
    ] == [
        (".panel", ".card"),
        (".new", ".card"),
        (".new", ".panel"),
    ]


def test_a_brace_inside_a_string_is_part_of_the_value(tmp_path: Path) -> None:
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

    report = report_css(tmp_path, css)

    assert [
        (finding.earlier.selector, finding.later.selector)
        for finding in report.findings
    ] == [(".new-a", ".new-b")]


def test_a_semicolon_inside_a_string_is_part_of_the_value(tmp_path: Path) -> None:
    css = """\
.quote-a {
  content: "a;b;c;d";
}
.quote-b {
  content: "x;b;c;d";
}
"""

    assert report_css(tmp_path, css).findings == ()


def test_app_css_with_a_copied_rule_names_the_original(tmp_path: Path) -> None:
    source = REPOSITORY / "src/budget/dashboard/static/app.css"
    css = (REPOSITORY / "src/budget/dashboard/static/app.css").read_text("utf-8")
    original = re.search(r"^\.header-inner \{\n(.*?)^\}", css, re.MULTILINE | re.DOTALL)
    assert original, "app.css no longer has a `.header-inner` rule to copy"
    copy = '.copied-header {\n  content: "}";\n' + original.group(1) + "}\n"
    copied = tmp_path / "copied.css"
    copied.write_text(copy, encoding="utf-8")

    report = report_overlaps((source, copied))

    matches = [
        finding
        for finding in report.findings
        if finding.later.selector == ".copied-header"
        and finding.earlier.selector == ".header-inner"
    ]
    assert [finding.declarations for finding in matches] == [
        (
            "align-items: center",
            "display: flex",
            "gap: 1rem",
            "justify-content: space-between",
            "min-height: 4.25rem",
        )
    ]
    assert matches, "the copied rule was not reported"
