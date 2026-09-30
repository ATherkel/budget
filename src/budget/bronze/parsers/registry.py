# Copyright 2026 Therkel
"""Explicit source-format selection: one declared ID, one parser.

There is no auto-detection, no entry-point discovery, and no mutable
registration API. A format ID that is not in this mapping is not accepted
input, and the store refuses it by name before it reads anything. Adding a
format is adding one module and one entry here, never a guess about a bank, an
account, or a filename.
"""

from collections.abc import Mapping
from types import MappingProxyType

from budget.bronze.parsers.base import SourceParser
from budget.bronze.parsers.danske_csv_v1 import PARSER as _DANSKE_CSV_V1


class UnsupportedSourceFormatError(ValueError):
    """A declared source format has no parser in the registry."""

    def __init__(self, source_format: str) -> None:
        """Name the format that is not accepted input."""
        super().__init__(f"Unsupported source format: {source_format}")


_PARSERS: Mapping[str, SourceParser] = MappingProxyType(
    {_DANSKE_CSV_V1.source_format: _DANSKE_CSV_V1}
)


def source_formats() -> tuple[str, ...]:
    """Return every declared format ID, in a stable order."""
    return tuple(sorted(_PARSERS))


def source_parser(source_format: str) -> SourceParser:
    """Return the parser declared for one exact format ID."""
    try:
        return _PARSERS[source_format]
    except KeyError:
        raise UnsupportedSourceFormatError(source_format) from None
