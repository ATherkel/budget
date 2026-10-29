# Copyright 2026 Therkel
"""Fixtures several Bronze tests share: a migrated profile and a tiny format.

`LineParser` is a real parser of an invented format, one source record per
line. Tests hand it to a `BronzeStore` as another version of a format, which is
how a parser fix is presented without mocking a project parser.
"""

from datetime import date
from pathlib import Path

from budget.bronze import migrate_bronze
from budget.bronze.parsers.base import ParserResult
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile


def migrated_profile(directory: str | Path) -> Profile:
    """Build the test profile for one temporary directory and migrate it."""
    profile = make_test_profile(directory)
    migrate_bronze(profile)
    return profile


class LineParser:
    """A real, tiny format: one source record per line, up to a limit."""

    source_format = "synthetic-lines-v1"

    def __init__(
        self,
        field: str | None,
        limit: int | None = None,
        failure: str = "this version reads no lines",
    ) -> None:
        """Hold the field each record carries, or fail every payload."""
        self._field = field
        self._limit = limit
        self._failure = failure

    def parse(self, content: bytes) -> ParserResult:
        """Present one record per line under this version's field name."""
        if self._field is None:
            return ParserResult.failed(self._failure)
        lines = [line for line in content.decode("ascii").splitlines() if line]
        if self._limit is not None:
            lines = lines[: self._limit]
        return ParserResult.matched(
            tuple({self._field: line} for line in lines),
            None,
            None,
        )

    def exported_on_from_filename(self, filename: str) -> date | None:
        """Read a -YYYYMMDD.csv suffix, as a real format does."""
        digits = filename.removesuffix(".csv").rpartition("-")[2]
        if len(digits) != 8 or not digits.isdigit():
            return None
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None

    def account_number_from_filename(self, filename: str) -> str | None:
        """Fail loudly if called: Bronze never reads an account number."""
        raise NotImplementedError

    def is_account_number(self, value: str) -> bool:
        """Fail loudly if called: Bronze never checks an account number."""
        raise NotImplementedError


class SecondLineParser(LineParser):
    """Another declared format, which happens to read the same bytes."""

    source_format = "synthetic-lines-v2"
