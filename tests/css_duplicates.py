# Copyright 2026 Therkel
"""Find CSS rules that repeat another rule's declarations."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# An innermost block: a selector list and declarations with no nested braces.
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
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


def parse_rules(css: str) -> list[Rule]:
    """Return the rules of `css` in source order."""
    rules = []
    for match in RULE.finditer(css):
        prelude = match.group(1)
        start = match.start(1) + len(prelude) - len(prelude.lstrip())
        body = match.group(2).split(";")
        rules.append(
            Rule(
                selector=" ".join(prelude.split()),
                line=css.count("\n", 0, start) + 1,
                declarations=frozenset(declaration(d) for d in body if d.strip()),
            )
        )
    return rules


def find_duplicates(css: str, allowlist: Iterable[tuple[str, str]] = ()) -> list[str]:
    """Return one message per pair of rules sharing 3 or more declarations."""
    del allowlist  # Stub until the green commit reads it.
    rules = parse_rules(css)
    messages = []
    for index, rule in enumerate(rules):
        for earlier in rules[:index]:
            shared = len(rule.declarations & earlier.declarations)
            if shared >= SHARED_LIMIT:
                messages.append(
                    f"`{rule.selector}` shares {shared} declarations with"
                    f" `{earlier.selector}` (line {earlier.line});"
                    f" reuse `{earlier.selector}`"
                )
    return messages
