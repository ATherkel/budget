# Copyright 2026 Therkel
"""The ranges file: what each account's exports were asked for, in writing.

`budget import --ranges <file>` reads the range the person asked the bank for
from this file instead of asking at the terminal. It holds a default range and
any number of per-account ranges, since one inbox can hold exports downloaded
on different days with different ranges:

    format = 1

    [default]
    from = 2025-08-30
    through = 2026-09-30

    [account.joint-savings]
    from = 2025-09-06
    through = 2026-09-30

The range is declared, never inferred (`bronze-layer.md`), so the file is the
person's own statement, exactly like an answer typed at the prompt.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from budget.importing import Coverage
from budget.inbox import ExportPreview
from budget.inputs import ConfigurationError

RANGES_FILE: str = "the ranges file"


@dataclass(frozen=True)
class DeclaredRanges:
    """A default range, and the ranges of accounts that differ from it."""

    default: Coverage | None
    accounts: Mapping[str, Coverage]

    def coverage(self, account_id: str) -> Coverage | None:
        """Return the account's own range, else the default, else none."""
        return self.accounts.get(account_id, self.default)

    def declared(self, previewed: ExportPreview) -> Coverage:
        """Return the range declared for one inbox file's account."""
        coverage = self.coverage(previewed.account_id)
        if coverage is None:
            problem = (
                f'{RANGES_FILE}: account "{previewed.account_id}" has no range, '
                "and there is no [default]; nothing was imported"
            )
            raise ConfigurationError((problem,))
        return coverage


def _date(table: Mapping[str, object], key: str) -> date:
    """Read one TOML date."""
    value = table[key]
    if not isinstance(value, date):
        raise TypeError(key)
    return value


def _coverage(table: Mapping[str, object]) -> Coverage:
    """Read one table's `from` and `through` dates."""
    return Coverage(
        covers_from=_date(table, "from"), covers_through=_date(table, "through")
    )


def load_ranges(path: Path) -> DeclaredRanges:
    """Read a ranges file."""
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    default = document.get("default")
    accounts = document.get("account", {})
    return DeclaredRanges(
        default=None if default is None else _coverage(default),
        accounts={
            account_id: _coverage(table) for account_id, table in accounts.items()
        },
    )
