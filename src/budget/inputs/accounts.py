# Copyright 2026 Therkel
"""`accounts.toml`: the account registry, only accounts inside the reporting boundary.

The registry is keyed by the household's own account ID. An account names the
source format its inbox folder receives and, optionally, the bank's number for
it, which is checked against an export's filename and never stored as Bronze
evidence.
"""

import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, TypeGuard

from budget.bronze.parsers import source_formats, source_parser
from budget.profiles import ACCOUNTS_FILE_NAME, Profile

_FORMAT_VERSION = 1
_TOP_LEVEL_KEYS = ("format", "account")

# A durable account ID: lowercase ASCII words joined by single hyphens.
_ACCOUNT_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class ConfigurationError(ValueError):
    """A household input file breaks its rules.

    `problems` holds one line per problem, each naming the file, the entry and
    the problem, in file order, so a caller can list every one before stopping.
    """

    def __init__(self, problems: tuple[str, ...]) -> None:
        """Keep every problem, and show them one per line."""
        self.problems = problems
        super().__init__("\n".join(problems))


class MisfiledExportError(ValueError):
    """An export's filename names another bank account than its folder's account.

    This refuses one file, not the configuration: the caller leaves the file in
    the inbox and goes on with the others. The message names the account ID
    only, never the number or the filename, so it is safe to show or log.
    """

    def __init__(self, account_id: str) -> None:
        """Name the account whose inbox folder holds the file."""
        self.account_id = account_id
        super().__init__(
            f'account "{account_id}": the export\'s filename carries another bank '
            "account number than accounts.toml declares; move the file to its "
            "account's inbox folder, or correct the declaration"
        )


@dataclass(frozen=True)
class Account:
    """One account the household imports, as `accounts.toml` declares it.

    `bank_account_number` is kept out of the representation, so the number
    never reaches a log through a repr.
    """

    account_id: str
    display_name: str
    account_type: Literal["current", "savings"]
    ownership_scope: Literal["household", "person"]
    currency: str
    source_format: str
    bank_account_number: str | None = field(default=None, repr=False)
    closed_on: date | None = None

    def check_export_filename(self, filename: str) -> None:
        """Refuse an export whose filename names another bank account.

        The check applies only when this account declares a number and its
        source format reads one from the filename; otherwise nothing is
        checked. A mismatch never chooses another account for the file.
        """
        if self.bank_account_number is None:
            return
        parser = source_parser(self.source_format)
        number = parser.account_number_from_filename(filename)
        if number is not None and number != self.bank_account_number:
            raise MisfiledExportError(self.account_id)


@dataclass(frozen=True)
class _FieldRule:
    """What one `[account.<id>]` key must hold, and how a problem says so."""

    accepts: Callable[[object], bool]
    rule: str
    required: bool = True


def _is_text(value: object) -> TypeGuard[str]:
    """Accept a non-empty TOML string."""
    return isinstance(value, str) and value != ""


def _is_date(value: object) -> bool:
    """Accept a TOML local date; a date-time is a different value."""
    return isinstance(value, date) and not isinstance(value, datetime)


def _one_of(*choices: str) -> _FieldRule:
    """Accept exactly one of the given strings."""
    return _FieldRule(
        accepts=lambda value: value in choices,
        rule=f"must be one of {', '.join(choices)}",
    )


# Every key an account may carry, required ones first, in the order a missing
# one is reported.
_FIELDS: Mapping[str, _FieldRule] = MappingProxyType(
    {
        "display_name": _FieldRule(_is_text, "must be a non-empty string"),
        "account_type": _one_of("current", "savings"),
        "ownership_scope": _one_of("household", "person"),
        "currency": _FieldRule(_is_text, "must be a non-empty string"),
        "source_format": _one_of(*source_formats()),
        "bank_account_number": _FieldRule(
            _is_text, "must be a quoted string", required=False
        ),
        "closed_on": _FieldRule(
            _is_date, "must be a date such as 2027-06-30", required=False
        ),
    }
)


def _problem(text: str) -> str:
    """Name the file a problem is in."""
    return f"{ACCOUNTS_FILE_NAME}: {text}"


def _read_document(path: Path) -> dict[str, Any]:
    """Read the file as UTF-8 TOML, or refuse it as a whole."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        problem = _problem("the file is missing")
        raise ConfigurationError((problem,)) from None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        problem = _problem("the file is not UTF-8")
        raise ConfigurationError((problem,)) from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        problem = _problem(f"the file is not valid TOML: {error}")
        raise ConfigurationError((problem,)) from None


def _require_known_format(document: Mapping[str, object]) -> None:
    """Refuse a file whose format version this code does not read.

    `bool` is a subclass of `int` in Python, so the type is compared exactly:
    `format = true` is not version 1.
    """
    version = document.get("format")
    if version is None:
        problem = _problem("format is missing")
    elif type(version) is not int or version != _FORMAT_VERSION:
        problem = _problem(f"format must be {_FORMAT_VERSION}")
    else:
        return
    raise ConfigurationError((problem,))


def _entry_problem(account_id: str, text: str) -> str:
    """Name the file and the entry a problem is in."""
    return _problem(f'account "{account_id}": {text}')


def _entry_problems(account_id: str, entry: object) -> list[str]:
    """List one entry's problems: its ID, then its keys, then what is missing."""
    if not isinstance(entry, dict):
        return [_entry_problem(account_id, "must be a table of keys")]
    problems = []
    if _ACCOUNT_ID.fullmatch(account_id) is None:
        problems.append(
            _entry_problem(
                account_id,
                "the ID must be lowercase words joined by hyphens, "
                "such as joint-current",
            )
        )
    for key, value in entry.items():
        field_rule = _FIELDS.get(key)
        if field_rule is None:
            problems.append(_entry_problem(account_id, f'unknown key "{key}"'))
        elif not field_rule.accepts(value):
            problems.append(_entry_problem(account_id, f"{key} {field_rule.rule}"))
    problems.extend(
        _entry_problem(account_id, f"{key} is missing")
        for key, field_rule in _FIELDS.items()
        if field_rule.required and key not in entry
    )
    return problems


def _number_shape_problems(account_id: str, entry: object) -> list[str]:
    """Name a declared number the account's source format never carries.

    Such a number could never match a filename, so every export for the
    account would be refused as misfiled. Without a known format or a
    well-formed number there is nothing to judge: those have their own problems.
    """
    if not isinstance(entry, dict):
        return []
    source_format = entry.get("source_format")
    number = entry.get("bank_account_number")
    if source_format not in source_formats() or not _is_text(number):
        return []
    if source_parser(source_format).is_account_number(number):
        return []
    return [
        _entry_problem(
            account_id,
            f"bank_account_number is not a {source_format} account number",
        )
    ]


def _shared_number_problems(entries: Mapping[str, object]) -> list[str]:
    """Name each account declaring a bank account number an earlier one declared.

    The problem names both accounts and never the number itself.
    """
    declared_by: dict[str, str] = {}
    problems = []
    for account_id, entry in entries.items():
        number = entry.get("bank_account_number") if isinstance(entry, dict) else None
        if not isinstance(number, str) or not number:
            continue
        earlier = declared_by.setdefault(number, account_id)
        if earlier != account_id:
            problems.append(
                _entry_problem(
                    account_id,
                    f'bank_account_number is already declared by account "{earlier}"',
                )
            )
    return problems


def _account(account_id: str, entry: Mapping[str, Any]) -> Account:
    """Build one account from an entry that has passed every rule."""
    return Account(
        account_id=account_id,
        display_name=entry["display_name"],
        account_type=entry["account_type"],
        ownership_scope=entry["ownership_scope"],
        currency=entry["currency"],
        source_format=entry["source_format"],
        bank_account_number=entry.get("bank_account_number"),
        closed_on=entry.get("closed_on"),
    )


def load_accounts(profile: Profile) -> Mapping[str, Account]:
    """Load and validate the profile's `accounts.toml`, keyed by account ID."""
    document = _read_document(profile.accounts_file)
    _require_known_format(document)
    problems = [
        _problem(f'unknown key "{key}"')
        for key in document
        if key not in _TOP_LEVEL_KEYS
    ]
    entries = document.get("account", {})
    if not isinstance(entries, dict):
        problems.append(
            _problem("account must hold one [account.<id>] table per account")
        )
        entries = {}
    for account_id, entry in entries.items():
        problems.extend(_entry_problems(account_id, entry))
        problems.extend(_number_shape_problems(account_id, entry))
    problems.extend(_shared_number_problems(entries))
    if problems:
        raise ConfigurationError(tuple(problems))
    return MappingProxyType(
        {
            account_id: _account(account_id, entry)
            for account_id, entry in entries.items()
        }
    )
