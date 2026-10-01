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
from typing import Literal

from budget.profiles import Profile


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


def load_accounts(profile: Profile) -> Mapping[str, Account]:
    """Load and validate the profile's `accounts.toml`, keyed by account ID."""
    raise NotImplementedError
