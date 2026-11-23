# Copyright 2026 Therkel
"""Find CSS rules that repeat another rule's declarations."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import tinycss2
from tinycss2.ast import AtRule, Declaration, Node, ParseError, QualifiedRule

# Two rules sharing this many declarations repeat each other.
SHARED_LIMIT = 3


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


def report_overlaps(paths: Iterable[Path]) -> Report:
    """Report declarations shared by rules in `paths`."""
    paths = tuple(paths)
    if not paths:
        return Report(findings=(), diagnostics=())
    return Report(findings=(), diagnostics=())


@dataclass(frozen=True)
class Rule:
    """One CSS rule: its selector list, first line and declarations."""

    selector: str
    line: int
    declarations: frozenset[str]


@dataclass(frozen=True)
class Block:
    """A rule the check cannot read: its prelude and first line."""

    prelude: str
    line: int


def text(nodes: Iterable[Node]) -> str:
    """Return `nodes` as CSS source with runs of whitespace collapsed."""
    return " ".join(str(tinycss2.serialize(nodes)).split())


def declaration(node: Declaration) -> str:
    """Return `property: value` with the property lower-cased."""
    value = text(node.value)
    if node.important:
        value += " !important"
    return f"{node.lower_name}: {value}"


@dataclass
class Parsed:
    """The rules of a stylesheet and the rules the check cannot read."""

    rules: list[Rule]
    nesting: list[Block]
    unreadable: list[Block]

    def add_rule(self, node: QualifiedRule, context: str) -> None:
        """Add a style rule, or note it when it nests another rule."""
        selector = " ".join(filter(None, [context, text(node.prelude)]))
        items = tinycss2.parse_blocks_contents(
            node.content, skip_comments=True, skip_whitespace=True
        )
        errors = [item for item in items if isinstance(item, ParseError)]
        if errors:
            self.unreadable.append(Block(selector, errors[0].source_line))
            return
        if any(not isinstance(item, Declaration) for item in items):
            self.nesting.append(Block(selector, node.source_line))
            return
        self.rules.append(
            Rule(
                selector=selector,
                line=node.source_line,
                declarations=frozenset(
                    declaration(item) for item in items if isinstance(item, Declaration)
                ),
            )
        )

    def add_nodes(self, nodes: Sequence[Node], context: str = "") -> None:
        """Add the style rules among `nodes`, entering at-rule blocks."""
        for node in nodes:
            if isinstance(node, QualifiedRule):
                self.add_rule(node, context)
            elif isinstance(node, AtRule) and node.content is not None:
                inner = tinycss2.parse_rule_list(
                    node.content, skip_comments=True, skip_whitespace=True
                )
                prelude = f"@{node.at_keyword} {text(node.prelude)}"
                self.add_nodes(inner, " ".join(filter(None, [context, prelude])))


def parse_rules(css: str) -> Parsed:
    """Return the rules of `css` in source order, and the rules it cannot read."""
    parsed = Parsed(rules=[], nesting=[], unreadable=[])
    parsed.add_nodes(
        tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
    )
    return parsed


def most_shared_first(rule: Rule, earlier_rules: list[Rule]) -> list[Rule]:
    """Return `earlier_rules` by declarations shared with `rule`, most first."""
    return sorted(
        earlier_rules,
        key=lambda earlier: -len(rule.declarations & earlier.declarations),
    )


def find_duplicates(css: str, allowlist: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Return one message per pair of rules sharing 3 or more declarations."""
    allowed = list(dict.fromkeys(allowlist))
    parsed = parse_rules(css)
    rules = parsed.rules
    messages = [
        f"`{block.prelude}` (line {block.line}) holds CSS the check cannot read;"
        " fix it so it can"
        for block in parsed.unreadable
    ]
    messages.extend(
        f"`{block.prelude}` (line {block.line}) nests a rule;"
        " write it flat so the check can read it"
        for block in parsed.nesting
    )
    found = set()
    for index, rule in enumerate(rules):
        for earlier in most_shared_first(rule, rules[:index]):
            shared = len(rule.declarations & earlier.declarations)
            pair = (rule.selector, earlier.selector)
            if shared < SHARED_LIMIT:
                continue
            found.add(pair)
            if pair not in allowed:
                messages.append(
                    f"`{rule.selector}` (line {rule.line})"
                    f" shares {shared} declarations with"
                    f" `{earlier.selector}` (line {earlier.line});"
                    f" reuse `{earlier.selector}`"
                )
    messages.extend(
        f"allowlist entry `{rule}` / `{earlier}` is no longer a duplicate; remove it"
        for rule, earlier in allowed
        if (rule, earlier) not in found
    )
    return messages


def read_allowlist(text: str) -> list[tuple[str, str]]:
    """Return the `rule | earlier rule` pairs of an allowlist file."""
    pairs = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        rule, separator, earlier = line.partition(" | ")
        if not (separator and rule.strip() and earlier.strip()):
            message = f"line {number} is not `rule | earlier rule`: {line}"
            raise ValueError(message)
        pairs.append((rule.strip(), earlier.strip()))
    return pairs
