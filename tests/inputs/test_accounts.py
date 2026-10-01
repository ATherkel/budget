# Copyright 2026 Therkel
"""`accounts.toml`, through `load_accounts` and a test profile.

Every file here is synthetic and written into the test profile's own inputs
folder; no real `accounts.toml` is read.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.inputs import Account, ConfigurationError, load_accounts
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

    def test_a_file_with_no_accounts_is_an_empty_registry(self) -> None:
        with TemporaryDirectory() as directory:
            profile = profile_with_accounts(directory, "format = 1\n")

            assert dict(load_accounts(profile)) == {}

    def test_a_missing_file_is_a_configuration_error(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with pytest.raises(ConfigurationError) as refusal:
                load_accounts(profile)

        assert refusal.value.problems == ("accounts.toml: the file is missing",)

    def test_a_file_that_is_not_utf8_toml_is_a_configuration_error(self) -> None:
        for content, expected in (
            (b"format = 1\n# \xe6\n", "accounts.toml: the file is not UTF-8"),
            (
                "format = 1\n[account.joint-current\n",
                "accounts.toml: the file is not valid TOML: ",
            ),
        ):
            with self.subTest(content=content), TemporaryDirectory() as directory:
                profile = profile_with_accounts(directory, content)

                with pytest.raises(ConfigurationError) as refusal:
                    load_accounts(profile)

                (problem,) = refusal.value.problems
                assert problem.startswith(expected)

    def test_an_unknown_format_version_is_refused_before_anything_else(self) -> None:
        for content, expected in (
            ("", "accounts.toml: format is missing"),
            ("format = 2\n", "accounts.toml: format must be 1"),
            ('format = "1"\n', "accounts.toml: format must be 1"),
            ("format = true\n", "accounts.toml: format must be 1"),
            # An unknown version's other keys mean nothing yet: none is reported.
            ("format = 2\ncolour = 1\n", "accounts.toml: format must be 1"),
        ):
            with self.subTest(content=content), TemporaryDirectory() as directory:
                profile = profile_with_accounts(directory, content)

                with pytest.raises(ConfigurationError) as refusal:
                    load_accounts(profile)

                assert refusal.value.problems == (expected,)

    def test_an_unknown_top_level_key_is_a_configuration_error(self) -> None:
        for content, expected in (
            (
                '[accounts.joint-current]\ndisplay_name = "Joint current"\n',
                'accounts.toml: unknown key "accounts"',
            ),
            (
                "account = 1\n",
                "accounts.toml: account must hold one [account.<id>] table per account",
            ),
        ):
            with self.subTest(content=content), TemporaryDirectory() as directory:
                profile = profile_with_accounts(directory, f"format = 1\n{content}")

                with pytest.raises(ConfigurationError) as refusal:
                    load_accounts(profile)

                assert refusal.value.problems == (expected,)


if __name__ == "__main__":
    unittest.main()
