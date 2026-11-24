# Copyright 2026 Therkel
"""Report CSS declarations that rule pairs have in common."""

import argparse
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import tinycss2
from tinycss2.ast import (
    AtRule,
    Declaration,
    Node,
    ParseError,
    QualifiedRule,
    WhitespaceToken,
)

# Two rules sharing this many declarations repeat each other.
SHARED_LIMIT = 3
GROUPING_AT_RULES: frozenset[str] = frozenset(
    {
        "container",
        "document",
        "layer",
        "media",
        "scope",
        "starting-style",
        "supports",
        "-moz-document",
    }
)
KEYFRAME_AT_RULES: frozenset[str] = frozenset({"keyframes", "-webkit-keyframes"})
DECLARATION_AT_RULES: frozenset[str] = frozenset(
    {"counter-style", "font-face", "page", "property"}
)
DASHBOARD_ROOT = Path(__file__).resolve().parents[1] / "src" / "budget" / "dashboard"


def discover_stylesheets(root: Path = DASHBOARD_ROOT) -> tuple[Path, ...]:
    """Return dashboard stylesheets under `root` in deterministic order."""
    return tuple(sorted(root.rglob("*.css"), key=lambda path: path.as_posix()))


@dataclass(frozen=True)
class Location:
    """Where a CSS rule starts and how its surrounding at-rules read."""

    path: Path
    line: int
    selector: str
    context: str = ""


@dataclass(frozen=True)
class Overlap:
    """Two rules and the declarations that they literally share."""

    later: Location
    earlier: Location
    declarations: tuple[str, ...]


@dataclass(frozen=True)
class Diagnostic:
    """A stylesheet that could not be read, parsed, or analyzed."""

    path: Path
    line: int | None
    message: str


@dataclass(frozen=True)
class Report:
    """Advisory overlaps and the failures that prevented a complete report."""

    findings: tuple[Overlap, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class Rule:
    """One CSS rule: its selector list, first line and declarations."""

    selector: str
    line: int
    declarations: frozenset[str]


@dataclass(frozen=True)
class _GroupedRule:
    """A parsed style rule with its stylesheet path and at-rule context."""

    path: Path
    rule: Rule
    context: str


def _grouped_rules(
    nodes: Sequence[Node],
    path: Path,
    diagnostics: list[Diagnostic],
    context: str = "",
) -> list[_GroupedRule]:
    """Return style rules in `nodes` and record syntax it cannot analyze."""
    rules: list[_GroupedRule] = []
    for node in nodes:
        if isinstance(node, ParseError):
            diagnostics.append(_parse_error(path, node))
        elif isinstance(node, QualifiedRule):
            grouped = _style_rule(path, node, diagnostics, context)
            if grouped is not None:
                rules.append(grouped)
        elif isinstance(node, AtRule) and node.content is not None:
            rules.extend(_at_rule_rules(node, path, diagnostics, context))
    return rules


def _parse_error(path: Path, error: ParseError) -> Diagnostic:
    """Return a diagnostic containing tinycss2's parser message."""
    return Diagnostic(
        path=path,
        line=error.source_line,
        message=f"parse error: {error.message}",
    )


def _style_rule(
    path: Path,
    node: QualifiedRule,
    diagnostics: list[Diagnostic],
    context: str,
) -> _GroupedRule | None:
    """Return one readable style rule, or diagnose unsupported block contents."""
    selector = text(node.prelude)
    items = tinycss2.parse_blocks_contents(
        node.content,
        skip_comments=True,
        skip_whitespace=True,
    )
    errors = [item for item in items if isinstance(item, ParseError)]
    diagnostics.extend(_parse_error(path, error) for error in errors)
    unsupported = [
        item for item in items if not isinstance(item, (Declaration, ParseError))
    ]
    if unsupported:
        diagnostics.append(
            Diagnostic(
                path=path,
                line=unsupported[0].source_line,
                message=f"unsupported nested rule inside `{selector}`",
            )
        )
    if errors or unsupported:
        return None
    return _GroupedRule(
        path=path,
        rule=Rule(
            selector=selector,
            line=node.source_line,
            declarations=frozenset(
                declaration(item) for item in items if isinstance(item, Declaration)
            ),
        ),
        context=context,
    )


def _at_rule_rules(
    node: AtRule,
    path: Path,
    diagnostics: list[Diagnostic],
    context: str,
) -> list[_GroupedRule]:
    """Return readable rules from a supported block at-rule."""
    content = node.content
    if content is None:
        return []
    keyword = node.at_keyword.lower()
    prelude = text(node.prelude)
    at_rule = f"@{node.at_keyword} {prelude}"
    if keyword in GROUPING_AT_RULES or keyword in KEYFRAME_AT_RULES:
        inner = tinycss2.parse_rule_list(
            content,
            skip_comments=True,
            skip_whitespace=True,
        )
        return _grouped_rules(
            inner,
            path,
            diagnostics,
            " ".join(filter(None, [context, at_rule])),
        )
    if keyword in DECLARATION_AT_RULES:
        return _declaration_at_rule(node, path, diagnostics, context, at_rule)
    diagnostics.append(
        Diagnostic(
            path=path,
            line=node.source_line,
            message=f"unsupported at-rule block `{at_rule}`",
        )
    )
    return []


def _declaration_at_rule(
    node: AtRule,
    path: Path,
    diagnostics: list[Diagnostic],
    context: str,
    at_rule: str,
) -> list[_GroupedRule]:
    """Return one declaration-style at-rule, or diagnose its block contents."""
    content = node.content
    if content is None:
        return []
    items = tinycss2.parse_blocks_contents(
        content,
        skip_comments=True,
        skip_whitespace=True,
    )
    errors = [item for item in items if isinstance(item, ParseError)]
    diagnostics.extend(_parse_error(path, error) for error in errors)
    unsupported = [
        item for item in items if not isinstance(item, (Declaration, ParseError))
    ]
    if unsupported:
        diagnostics.append(
            Diagnostic(
                path=path,
                line=unsupported[0].source_line,
                message=f"unsupported nested block inside `{at_rule}`",
            )
        )
    if errors or unsupported:
        return []
    return [
        _GroupedRule(
            path=path,
            rule=Rule(
                selector=at_rule,
                line=node.source_line,
                declarations=frozenset(
                    declaration(item) for item in items if isinstance(item, Declaration)
                ),
            ),
            context=context,
        )
    ]


def report_overlaps(paths: Iterable[Path]) -> Report:
    """Report declarations shared by rules in `paths`."""
    rules: list[_GroupedRule] = []
    diagnostics: list[Diagnostic] = []
    for path in paths:
        try:
            css = path.read_text(encoding="utf-8")
        except OSError as error:
            diagnostics.append(_read_error(path, error))
            continue
        except UnicodeDecodeError as error:
            diagnostics.append(
                Diagnostic(
                    path=path,
                    line=None,
                    message=(
                        "cannot decode stylesheet as UTF-8 at byte "
                        f"{error.start}: {error.reason}"
                    ),
                )
            )
            continue
        nodes = tinycss2.parse_stylesheet(
            css,
            skip_comments=True,
            skip_whitespace=True,
        )
        rules.extend(_grouped_rules(nodes, path, diagnostics))

    findings: list[Overlap] = []
    for index, grouped in enumerate(rules):
        for earlier in rules[:index]:
            shared = grouped.rule.declarations & earlier.rule.declarations
            if len(shared) < SHARED_LIMIT:
                continue
            findings.append(
                Overlap(
                    later=Location(
                        path=grouped.path,
                        line=grouped.rule.line,
                        selector=grouped.rule.selector,
                        context=grouped.context,
                    ),
                    earlier=Location(
                        path=earlier.path,
                        line=earlier.rule.line,
                        selector=earlier.rule.selector,
                        context=earlier.context,
                    ),
                    declarations=tuple(sorted(shared)),
                )
            )
    return Report(findings=tuple(findings), diagnostics=tuple(diagnostics))


def _read_error(path: Path, error: OSError) -> Diagnostic:
    """Return a portable diagnostic for a stylesheet read failure."""
    if isinstance(error, FileNotFoundError):
        message = "cannot read stylesheet: file not found"
    elif isinstance(error, PermissionError):
        message = "cannot read stylesheet: permission denied"
    else:
        detail = error.strerror or type(error).__name__
        message = f"cannot read stylesheet: {detail}"
    return Diagnostic(path=path, line=None, message=message)


def text(nodes: Iterable[Node]) -> str:
    """Return `nodes` as CSS source with runs of whitespace collapsed."""
    return " ".join(str(tinycss2.serialize(nodes)).split())


def declaration(node: Declaration) -> str:
    """Return a normalized declaration, preserving value-significant text."""
    property_name = node.name if node.name.startswith("--") else node.lower_name
    parts: list[str] = []
    for token in node.value:
        if isinstance(token, WhitespaceToken):
            if parts and parts[-1] != " ":
                parts.append(" ")
        else:
            parts.append(tinycss2.serialize([token]))
    value = "".join(parts).strip()
    if node.important:
        value += " !important"
    return f"{property_name}: {value}"


def format_report(report: Report) -> str:
    """Return the neutral advisory report printed by the executable."""
    count = len(report.findings)
    noun = "finding" if count == 1 else "findings"
    lines = [f"CSS declaration overlap advisory: {count} {noun}"]
    for finding in report.findings:
        lines.extend(
            [
                f"- {location_text(finding.earlier)}",
                f"  with {location_text(finding.later)}",
                "  shared declarations:",
                *(f"    {declaration}" for declaration in finding.declarations),
            ]
        )
    lines.extend(
        [
            "",
            "Review the overlap and decide how these rules should be maintained.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_diagnostics(report: Report) -> str:
    """Return explicit analysis failures for stderr."""
    lines = []
    for diagnostic in report.diagnostics:
        location = (
            f"{diagnostic.path}:{diagnostic.line}"
            if diagnostic.line is not None
            else str(diagnostic.path)
        )
        lines.append(f"CSS analysis error: {location}: {diagnostic.message}")
    return "\n".join(lines) + "\n"


def location_text(location: Location) -> str:
    """Return one location with its path, line, grouping context, and selector."""
    selector = (
        f"{location.context} `{location.selector}`"
        if location.context
        else f"`{location.selector}`"
    )
    return f"{location.path}:{location.line} {selector}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CSS overlap advisory command."""
    parser = argparse.ArgumentParser(
        description="Report declaration overlaps across dashboard CSS."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Stylesheets to inspect; defaults to all dashboard CSS.",
    )
    arguments = parser.parse_args(argv)
    paths = arguments.paths or discover_stylesheets()
    report = report_overlaps(paths)
    sys.stdout.write(format_report(report))
    if report.diagnostics:
        sys.stderr.write(format_diagnostics(report))
    return 1 if report.diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
