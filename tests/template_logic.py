# Copyright 2026 Therkel
"""The gate that keeps logic out of the dashboard's templates."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment

_ENDS = {"block_begin": "block_end", "variable_begin": "variable_end"}
_BANNED_TAGS = ("if", "elif", "else")


@dataclass
class _Tag:
    """One `{% %}` or `{{ }}` tag: where it starts, its source and its words."""

    line: int
    end: str
    parts: list[str]
    words: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Return the tag's source with each run of whitespace as one space."""
        return " ".join("".join(self.parts).split())


def _tags(environment: Environment, source: str) -> Iterator[_Tag]:
    """Yield each tag of `source`, in order, as Jinja's lexer splits it."""
    tag = None
    for line, kind, value in environment.lex(source):
        if kind in _ENDS:
            tag = _Tag(line, _ENDS[kind], [value])
        elif tag is not None:
            tag.parts.append(value)
            if kind == tag.end:
                yield tag
                tag = None
            elif kind != "whitespace":
                tag.words.append(value)


def _constructs(tag: _Tag) -> list[str]:
    """Return the banned constructs in `tag`."""
    if tag.end == "block_end" and tag.words[0] in _BANNED_TAGS:
        return [tag.words[0]]
    return []


def gate(environment: Environment, root: Path, allowlist: Path) -> list[str]:
    """Return one message for each way the templates under `root` fail the gate."""
    del allowlist
    messages = []
    for page in sorted(root.rglob("*.html")):
        name = page.relative_to(root).as_posix()
        for tag in _tags(environment, page.read_text(encoding="utf-8")):
            constructs = ", ".join(f"`{word}`" for word in _constructs(tag))
            if constructs:
                messages.append(
                    f"{name}:{tag.line}: {constructs} in {tag.text}"
                    " is not on the allowlist"
                )
    return messages
