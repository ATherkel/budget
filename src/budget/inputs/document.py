# Copyright 2026 Therkel
"""Reading one household TOML file, and refusing it as a whole.

Every input file is UTF-8, with or without a byte-order mark, and carries
`format = 1` (`operations.md`, *Household Inputs*). Problems are lines naming
the file first, so one `ConfigurationError` can list them across files.
"""

import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_FORMAT_VERSION = 1


class ConfigurationError(ValueError):
    """A household input file breaks its rules.

    `problems` holds one line per problem, each naming the file, the entry and
    the problem, in file order, so a caller can list every one before stopping.
    """

    def __init__(self, problems: tuple[str, ...]) -> None:
        """Keep every problem, and show them one per line."""
        self.problems = problems
        super().__init__("\n".join(problems))


def file_problem(file_name: str, text: str) -> str:
    """Name the file a problem is in."""
    return f"{file_name}: {text}"


def read_document(path: Path, file_name: str) -> dict[str, Any]:
    """Read the file as UTF-8 TOML with a known format, or refuse it as a whole.

    `bool` is a subclass of `int` in Python, so the version's type is compared
    exactly: `format = true` is not version 1. An unknown version's other keys
    mean nothing yet, so none is judged.
    """
    document = _parse(path, file_name)
    version = document.get("format")
    if version is None:
        problem = file_problem(file_name, "format is missing")
    elif type(version) is not int or version != _FORMAT_VERSION:
        problem = file_problem(file_name, f"format must be {_FORMAT_VERSION}")
    else:
        return document
    raise ConfigurationError((problem,))


def _parse(path: Path, file_name: str) -> dict[str, Any]:
    """Decode and parse the file."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        problem = file_problem(file_name, "the file is missing")
        raise ConfigurationError((problem,)) from None
    try:
        # A leading byte-order mark is still UTF-8, and is dropped.
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        problem = file_problem(file_name, "the file is not UTF-8")
        raise ConfigurationError((problem,)) from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        problem = file_problem(file_name, f"the file is not valid TOML: {error}")
        raise ConfigurationError((problem,)) from None


def keyed_tables(
    document: Mapping[str, object], file_name: str, kind: str
) -> tuple[Mapping[str, object], list[str]]:
    """Return the file's `[<kind>.<id>]` entries, or a problem with their shape.

    A `kind` key holding anything but a table of entries gives none.
    """
    entries = document.get(kind, {})
    if isinstance(entries, dict):
        return dict[str, object](entries), []
    problem = file_problem(
        file_name, f"{kind} must hold one [{kind}.<id>] table per {kind}"
    )
    return {}, [problem]


def unknown_top_level_keys(
    document: Mapping[str, object], file_name: str, known: Iterable[str]
) -> list[str]:
    """Name each top-level key the file may not carry; `format` is always known."""
    allowed = {"format", *known}
    return [
        file_problem(file_name, f'unknown key "{key}"')
        for key in document
        if key not in allowed
    ]
