# Copyright 2026 Therkel
"""Find CSS rules that repeat another rule's declarations."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# An innermost block: a selector list and declarations with no nested braces.
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
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


def enclosing_preludes(css: str, position: int) -> list[str]:
    """Return the preludes of the blocks still open at `position`, outermost first."""
    open_blocks: list[str] = []
    start = 0
    for index, character in enumerate(css[:position]):
        if character == "{":
            open_blocks.append(" ".join(css[start:index].split()))
            start = index + 1
        elif character in "};":
            if character == "}":
                open_blocks.pop()
            start = index + 1
    return open_blocks


def parse_rules(css: str) -> list[Rule]:
    """Return the rules of `css` in source order."""
    # Blank each comment but keep its line breaks, so line numbers still hold.
    css = COMMENT.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), css)
    rules = []
    for match in RULE.finditer(css):
        prelude = match.group(1)
        start = match.start(1) + len(prelude) - len(prelude.lstrip())
        body = match.group(2).split(";")
        rules.append(
            Rule(
                selector=" ".join(
                    [*enclosing_preludes(css, match.start()), *prelude.split()]
                ),
                line=css.count("\n", 0, start) + 1,
                declarations=frozenset(declaration(d) for d in body if d.strip()),
            )
        )
    return rules


def find_duplicates(css: str, allowlist: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Return one message per pair of rules sharing 3 or more declarations."""
    allowed = list(dict.fromkeys(allowlist))
    rules = parse_rules(css)
    messages = []
    found = set()
    for index, rule in enumerate(rules):
        for earlier in rules[:index]:
            shared = len(rule.declarations & earlier.declarations)
            pair = (rule.selector, earlier.selector)
            if shared < SHARED_LIMIT:
                continue
            found.add(pair)
            if pair not in allowed:
                messages.append(
                    f"`{rule.selector}` shares {shared} declarations with"
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
    del text  # Stub until the green commit reads it.
    return []
