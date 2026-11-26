# Copyright 2026 Therkel
"""The gate that keeps logic out of the dashboard's templates."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, nodes
from jinja2.defaults import DEFAULT_FILTERS

_ENDS = {"block_begin": "block_end", "variable_begin": "variable_end"}
_BANNED_TAGS = ("if", "elif", "else", "set")
# A tag of these is reported by its name alone: it cannot be parsed by itself.
_UNPARSED_TAGS = ("elif", "else")
# Checked in order, so `Not` is named before the `UnaryExpr` it extends.
_BANNED_NODES: tuple[tuple[type[nodes.Node], str], ...] = (
    (nodes.Compare, "comparison"),
    (nodes.And, "and"),
    (nodes.Or, "or"),
    (nodes.Not, "not"),
    (nodes.BinExpr, "arithmetic"),
    (nodes.UnaryExpr, "arithmetic"),
    (nodes.Concat, "~"),
    (nodes.CondExpr, "inline if"),
    (nodes.Test, "is"),
)


@dataclass
class _Tag:
    """One `{% %}` or `{{ }}` tag: where it starts, its source and its words."""

    line: int
    end: str
    parts: list[str]
    words: list[str] = field(default_factory=list)

    @property
    def source(self) -> str:
        """Return the tag's source as written."""
        return "".join(self.parts)

    @property
    def text(self) -> str:
        """Return the tag's source with each run of whitespace as one space."""
        return " ".join(self.source.split())


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


def _parsed(environment: Environment, tag: _Tag) -> nodes.Template | None:
    """Return `tag` parsed by itself, closed when it opens a block.

    A tag that only continues or ends a block parses to nothing.
    """
    name = tag.words[0]
    if tag.end == "block_end" and (name in _UNPARSED_TAGS or name.startswith("end")):
        return None
    try:
        return environment.parse(tag.source)
    except TemplateSyntaxError:
        return environment.parse(tag.source + "{% end" + name + " %}")


def _node_name(node: nodes.Node) -> str:
    """Return the name the gate reports `node` under."""
    return next(name for kind, name in _BANNED_NODES if isinstance(node, kind))


def _constructs(environment: Environment, tag: _Tag) -> list[str]:
    """Return the banned constructs in `tag`, each once, in source order."""
    found = []
    if tag.end == "block_end" and tag.words[0] in _BANNED_TAGS:
        found.append(tag.words[0])
    tree = _parsed(environment, tag)
    if tree is not None:
        found.extend(
            "for ... if" for loop in tree.find_all(nodes.For) if loop.test is not None
        )
        kinds = tuple(kind for kind, _ in _BANNED_NODES)
        found.extend(_node_name(node) for node in tree.find_all(kinds))
        allowed = _allowed_filters(environment)
        found.extend(
            f"filter {used.name}"
            for used in tree.find_all(nodes.Filter)
            if used.name not in allowed
        )
    return list(dict.fromkeys(found))


def _allowed_filters(environment: Environment) -> set[str]:
    """Return the filters a template may use: budget's own, and `xmlattr`.

    Budget's own are those registered on `environment` over Jinja's defaults.
    """
    own = {
        name
        for name, function in environment.filters.items()
        if DEFAULT_FILTERS.get(name) is not function
    }
    return own | {"xmlattr"}


def gate(environment: Environment, root: Path, allowlist: Path) -> list[str]:
    """Return one message for each way the templates under `root` fail the gate."""
    del allowlist
    messages = []
    for page in sorted(root.rglob("*.html")):
        name = page.relative_to(root).as_posix()
        for tag in _tags(environment, page.read_text(encoding="utf-8")):
            constructs = ", ".join(
                f"`{word}`" for word in _constructs(environment, tag)
            )
            if constructs:
                messages.append(
                    f"{name}:{tag.line}: {constructs} in {tag.text}"
                    " is not on the allowlist"
                )
    return messages
