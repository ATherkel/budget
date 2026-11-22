# Copyright 2026 Therkel
"""Find CSS rules that repeat another rule's declarations."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Two rules sharing this many declarations repeat each other.
SHARED_LIMIT = 3


@dataclass(frozen=True)
class Rule:
    """One CSS rule: its selector list, first line and declarations."""

    selector: str
    line: int
    declarations: frozenset[str]


def declaration(text: str) -> str:
    """Return `property: value` with the property lower-cased."""
    name, _, value = text.partition(":")
    return f"{name.strip().lower()}: {' '.join(value.split())}"


@dataclass
class Block:
    """A block still open while the parser walks the CSS."""

    prelude: str
    line: int
    body_start: int
    has_child: bool = False


def open_block(css: str, prelude_start: int, brace: int) -> Block:
    """Return the block whose prelude runs from `prelude_start` to `brace`."""
    text = css[prelude_start:brace]
    first = prelude_start + len(text) - len(text.lstrip())
    return Block(
        prelude=" ".join(text.split()),
        line=css.count("\n", 0, first) + 1,
        body_start=brace + 1,
    )


def close_rule(css: str, block: Block, brace: int, parents: list[Block]) -> Rule:
    """Return the rule a closed block without nested blocks holds."""
    body = css[block.body_start : brace].split(";")
    return Rule(
        selector=" ".join([*(parent.prelude for parent in parents), block.prelude]),
        line=block.line,
        declarations=frozenset(declaration(d) for d in body if d.strip()),
    )


def parse_rules(css: str) -> tuple[list[Rule], list[Block]]:
    """Return the rules of `css` in source order, and the rules that nest a rule."""
    # Blank each comment but keep its line breaks, so line numbers still hold.
    css = COMMENT.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), css)
    rules = []
    nesting = []
    stack: list[Block] = []
    # A prelude starts after the last `{`, `}` or `;`.
    start = 0
    for index, character in enumerate(css):
        if character == "{":
            if stack:
                stack[-1].has_child = True
            stack.append(open_block(css, start, index))
        elif character == "}":
            block = stack.pop()
            if not block.has_child:
                rules.append(close_rule(css, block, index, stack))
            elif not block.prelude.startswith("@"):
                nesting.append(block)
        if character in "{};":
            start = index + 1
    return rules, nesting


def most_shared_first(rule: Rule, earlier_rules: list[Rule]) -> list[Rule]:
    """Return `earlier_rules` by declarations shared with `rule`, most first."""
    return sorted(
        earlier_rules,
        key=lambda earlier: -len(rule.declarations & earlier.declarations),
    )


def find_duplicates(css: str, allowlist: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Return one message per pair of rules sharing 3 or more declarations."""
    allowed = list(dict.fromkeys(allowlist))
    rules, nesting = parse_rules(css)
    messages = [
        f"`{block.prelude}` (line {block.line}) nests a rule;"
        " write it flat so the check can read it"
        for block in nesting
    ]
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
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            rule, _, earlier = line.partition(" | ")
            pairs.append((rule.strip(), earlier.strip()))
    return pairs
