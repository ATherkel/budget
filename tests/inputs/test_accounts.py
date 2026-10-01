# Copyright 2026 Therkel
"""`accounts.toml`, through `load_accounts` and a test profile.

Every file here is synthetic and written into the test profile's own inputs
folder; no real `accounts.toml` is read.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.inputs import Account, load_accounts
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile

ACCOUNTS = """\
format = 1

[account.joint-current]
display_name = "Joint current"
account_type = "current"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
bank_account_number = "0012345678"

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "person"
currency = "DKK"
source_format = "danske-csv-v1"
closed_on = 2027-06-30
"""


def profile_with_accounts(root: str | Path, content: str | bytes) -> Profile:
    """Build a test profile whose inputs folder holds the given accounts.toml."""
    profile = make_test_profile(root)
    profile.inputs.mkdir(parents=True)
    data = content.encode() if isinstance(content, str) else content
    profile.accounts_file.write_bytes(data)
    return profile


class LoadAccountsTests(unittest.TestCase):
    def test_accounts_load_keyed_by_account_id(self) -> None:
        with TemporaryDirectory() as directory:
            profile = profile_with_accounts(directory, ACCOUNTS)

            accounts = load_accounts(profile)

        assert list(accounts) == ["joint-current", "joint-savings"]
        assert accounts["joint-current"] == Account(
            account_id="joint-current",
            display_name="Joint current",
            account_type="current",
            ownership_scope="household",
            currency="DKK",
            source_format="danske-csv-v1",
            bank_account_number="0012345678",
        )
        assert accounts["joint-savings"] == Account(
            account_id="joint-savings",
            display_name="Joint savings",
            account_type="savings",
            ownership_scope="person",
            currency="DKK",
            source_format="danske-csv-v1",
            closed_on=date(2027, 6, 30),
        )

    def test_an_account_number_never_reaches_a_repr(self) -> None:
        with TemporaryDirectory() as directory:
            profile = profile_with_accounts(directory, ACCOUNTS)

            accounts = load_accounts(profile)

        assert "0012345678" not in repr(accounts["joint-current"])
        assert "0012345678" not in repr(accounts)


if __name__ == "__main__":
    unittest.main()
