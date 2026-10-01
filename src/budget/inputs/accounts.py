# Copyright 2026 Therkel
"""`accounts.toml`: the account registry, only accounts inside the reporting boundary.

The registry is keyed by the household's own account ID. An account names the
source format its inbox folder receives and, optionally, the bank's number for
it, which is checked against an export's filename and never stored as Bronze
evidence.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from budget.profiles import ACCOUNTS_FILE_NAME, Profile

_FORMAT_VERSION = 1
_TOP_LEVEL_KEYS = ("format", "account")


class ConfigurationError(ValueError):
    """A household input file breaks its rules.

    `problems` holds one line per problem, each naming the file, the entry and
    the problem, in file order, so a caller can list every one before stopping.
    """

    def __init__(self, problems: tuple[str, ...]) -> None:
        """Keep every problem, and show them one per line."""
        self.problems = problems
        super().__init__("\n".join(problems))


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
    if problems:
        raise ConfigurationError(tuple(problems))
    return MappingProxyType(
        {
            account_id: Account(
                account_id=account_id,
                display_name=entry["display_name"],
                account_type=entry["account_type"],
                ownership_scope=entry["ownership_scope"],
                currency=entry["currency"],
                source_format=entry["source_format"],
                bank_account_number=entry.get("bank_account_number"),
                closed_on=entry.get("closed_on"),
            )
            for account_id, entry in entries.items()
        }
    )
