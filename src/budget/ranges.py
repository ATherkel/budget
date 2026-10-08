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

Both ends are inclusive TOML dates, without quotes. The range is declared,
never inferred (`bronze-layer.md`), so the file is the person's own statement,
exactly like an answer typed at the prompt. A file that breaks these rules is
refused whole, listing every problem, before anything is imported. So is an
`[account.<id>]` that `accounts.toml` does not declare: a misspelt account
would otherwise fall back to the default without a word.
"""

import tomllib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

from budget.importing import Coverage
from budget.inbox import ExportPreview
from budget.inputs import ConfigurationError

RANGES_FILE: Final = "the ranges file"
RANGES_FORMAT: Final = 1
_KEYS: Final = frozenset({"format", "default", "account"})
_RANGE_KEYS: Final = ("from", "through")
_NOTHING_IMPORTED: Final = "; nothing was imported"


class RangesFileError(ConfigurationError):
    """The ranges file breaks its rules; every problem is named.

    Each line names the ranges file, never its path, and the last says that
    nothing was imported.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        """Prefix each problem, and end the last with the outcome."""
        lines = [f"{RANGES_FILE}: {problem}" for problem in problems]
        lines[-1] += _NOTHING_IMPORTED
        super().__init__(tuple(lines))


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
                f'account "{previewed.account_id}" has no range, and there is '
                "no [default]"
            )
            raise RangesFileError((problem,))
        return coverage


def _document(path: Path) -> Mapping[str, object]:
    """Read the file as TOML, refusing what cannot be read or parsed."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise RangesFileError((f"cannot be read: {reason}",)) from None
    except UnicodeDecodeError:
        raise RangesFileError(("is not UTF-8 text",)) from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise RangesFileError((f"is not valid TOML: {error}",)) from None


def _date(
    where: str, table: Mapping[str, object], key: str, problems: list[str]
) -> date | None:
    """Read one plain TOML date, or note why it is not one."""
    if key not in table:
        problems.append(f"{where}: {key} is missing")
        return None
    value = table[key]
    # A date-time is a `date` too, but a range is whole days.
    if not isinstance(value, date) or isinstance(value, datetime):
        problems.append(
            f"{where}: {key} must be a date such as 2026-09-30, without quotes"
        )
        return None
    return value


def _coverage(where: str, table: object, problems: list[str]) -> Coverage | None:
    """Read one `from`/`through` table, or note every way it is wrong."""
    if not isinstance(table, dict):
        problems.append(f"{where} must be a table")
        return None
    problems.extend(
        f"{where}: unknown key {key}" for key in table if key not in _RANGE_KEYS
    )
    start = _date(where, table, "from", problems)
    end = _date(where, table, "through", problems)
    if start is None or end is None:
        return None
    return Coverage(covers_from=start, covers_through=end)


def _accounts(
    table: object, known: Collection[str], problems: list[str]
) -> dict[str, Coverage]:
    """Read every `[account.<id>]` table an account in `accounts.toml` owns."""
    if not isinstance(table, dict):
        problems.append("account must hold [account.<id>] tables")
        return {}
    found: dict[str, Coverage] = {}
    for key, entry in table.items():
        account_id = str(key)
        where = f"[account.{account_id}]"
        if account_id not in known:
            problems.append(f'{where}: "{account_id}" is not in accounts.toml')
        coverage = _coverage(where, entry, problems)
        if coverage is not None:
            found[account_id] = coverage
    return found


def load_ranges(path: Path, known_accounts: Collection[str]) -> DeclaredRanges:
    """Read a ranges file whose accounts are all in `known_accounts`."""
    document = _document(path)
    problems: list[str] = []
    form = document.get("format")
    if type(form) is not int or form != RANGES_FORMAT:
        problems.append(f"format must be {RANGES_FORMAT}")
    problems.extend(f"unknown key {key}" for key in document if key not in _KEYS)
    default = None
    if "default" in document:
        default = _coverage("[default]", document["default"], problems)
    accounts = _accounts(document.get("account", {}), known_accounts, problems)
    if problems:
        raise RangesFileError(problems)
    return DeclaredRanges(default=default, accounts=accounts)
