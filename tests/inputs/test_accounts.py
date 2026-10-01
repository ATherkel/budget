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


def entry_problem(account_id: str, text: str) -> str:
    """Spell one entry's problem the way the loader reports it."""
    return f'accounts.toml: account "{account_id}": {text}'


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

    def test_every_broken_entry_is_named_with_its_problems_in_file_order(
        self,
    ) -> None:
        content = """\
format = 1
account.loose = "Joint current"

[account.Joint-Current]
display_name = "Joint current"
account_type = "current"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"

[account.joint-savings]
display_name = "Joint savings"
account_type = "credit"
ownership_scope = "household"
currency = "DKK"
source_format = "nordea-csv-v1"
colour = "blue"
bank_account_number = 1234567890
closed_on = "2027-06-30"

[account.card]
display_name = ""
ownership_scope = "family"
"""
        with TemporaryDirectory() as directory:
            profile = profile_with_accounts(directory, content)

            with pytest.raises(ConfigurationError) as refusal:
                load_accounts(profile)

        assert refusal.value.problems == (
            entry_problem("loose", "must be a table of keys"),
            entry_problem(
                "Joint-Current",
                "the ID must be lowercase words joined by hyphens, "
                "such as joint-current",
            ),
            entry_problem(
                "joint-savings", "account_type must be one of current, savings"
            ),
            entry_problem(
                "joint-savings", "source_format must be one of danske-csv-v1"
            ),
            entry_problem("joint-savings", 'unknown key "colour"'),
            entry_problem(
                "joint-savings", "bank_account_number must be a quoted string"
            ),
            entry_problem(
                "joint-savings", "closed_on must be a date such as 2027-06-30"
            ),
            entry_problem("card", "display_name must be a non-empty string"),
            entry_problem("card", "ownership_scope must be one of household, person"),
            entry_problem("card", "account_type is missing"),
            entry_problem("card", "currency is missing"),
            entry_problem("card", "source_format is missing"),
        )

    def test_every_value_has_its_declared_type(self) -> None:
        for line, expected in (
            ("display_name = 5", "display_name must be a non-empty string"),
            ('currency = ""', "currency must be a non-empty string"),
            ('bank_account_number = ""', "bank_account_number must be a quoted string"),
            (
                "closed_on = 2027-06-30T12:00:00Z",
                "closed_on must be a date such as 2027-06-30",
            ),
            (
                "closed_on = 2027-06-30T12:00:00",
                "closed_on must be a date such as 2027-06-30",
            ),
        ):
            key = line.partition(" ")[0]
            entry = "\n".join(
                kept for kept in ACCOUNTS.splitlines()[2:9] if not kept.startswith(key)
            )
            content = f"format = 1\n{entry}\n{line}\n"
            with self.subTest(line=line), TemporaryDirectory() as directory:
                profile = profile_with_accounts(directory, content)

                with pytest.raises(ConfigurationError) as refusal:
                    load_accounts(profile)

                assert refusal.value.problems == (
                    entry_problem("joint-current", expected),
                )

    def test_an_account_id_is_lowercase_words_joined_by_hyphens(self) -> None:
        entry = ACCOUNTS.splitlines()[3:9]
        for account_id, accepted in (
            ("joint", True),
            ("card-2", True),
            ("joint_current", False),
            ("joint--current", False),
            ("-joint", False),
            ("joint-", False),
            ("kørsel", False),
        ):
            content = "\n".join(["format = 1", f'[account."{account_id}"]', *entry])
            with self.subTest(account_id=account_id), TemporaryDirectory() as directory:
                profile = profile_with_accounts(directory, content)

                if accepted:
                    assert list(load_accounts(profile)) == [account_id]
                    continue
                with pytest.raises(ConfigurationError) as refusal:
                    load_accounts(profile)
                (problem,) = refusal.value.problems
                assert problem.startswith(entry_problem(account_id, ""))

    def test_two_accounts_may_not_declare_one_bank_account_number(self) -> None:
        content = ACCOUNTS.replace(
            "closed_on = 2027-06-30", 'bank_account_number = "0012345678"'
        )
        with TemporaryDirectory() as directory:
            profile = profile_with_accounts(directory, content)

            with pytest.raises(ConfigurationError) as refusal:
                load_accounts(profile)

        assert refusal.value.problems == (
            entry_problem(
                "joint-savings",
                'bank_account_number is already declared by account "joint-current"',
            ),
        )
        assert "0012345678" not in str(refusal.value)


if __name__ == "__main__":
    unittest.main()
