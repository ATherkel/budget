# Copyright 2026 Therkel
"""`accounts.toml`: the account registry, only accounts inside the reporting boundary.

The registry is keyed by the household's own account ID. An account names the
source format its inbox folder receives and, optionally, the bank's number for
it, which is checked against an export's filename and never stored as Bronze
evidence.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Literal

from budget.bronze.parsers import source_formats, source_parser
from budget.inputs.document import (
    ConfigurationError,
    file_problem,
    keyed_tables,
    read_document,
    unknown_top_level_keys,
)
from budget.inputs.fields import (
    TEXT,
    FieldRule,
    entry_problems,
    is_date,
    is_text,
    one_of,
)
from budget.profiles import ACCOUNTS_FILE_NAME, Profile


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


# Every key an account may carry, required ones first, in the order a missing
# one is reported.
_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {
        "display_name": TEXT,
        "account_type": one_of("current", "savings"),
        "ownership_scope": one_of("household", "person"),
        "currency": TEXT,
        "source_format": one_of(*source_formats()),
        "bank_account_number": FieldRule(
            is_text, "must be a quoted string", required=False
        ),
        "closed_on": FieldRule(
            is_date, "must be a date such as 2027-06-30", required=False
        ),
    }
)


def _entry_problem(account_id: str, text: str) -> str:
    """Name the file and the entry a problem is in."""
    return file_problem(ACCOUNTS_FILE_NAME, f'account "{account_id}": {text}')


def _entry_problems(account_id: str, entry: object) -> list[str]:
    """List one entry's problems: its ID, then its keys, then what is missing."""
    return [
        _entry_problem(account_id, problem)
        for problem in entry_problems(account_id, entry, _FIELDS, "joint-current")
    ]


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
    if source_format not in source_formats() or not is_text(number):
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
        if not is_text(number):
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
    document = read_document(profile.accounts_file, ACCOUNTS_FILE_NAME)
    problems = unknown_top_level_keys(document, ACCOUNTS_FILE_NAME, ("account",))
    entries, shape_problems = keyed_tables(document, ACCOUNTS_FILE_NAME, "account")
    problems.extend(shape_problems)
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
