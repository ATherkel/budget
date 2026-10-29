# Copyright 2026 Therkel
"""A rebuild checks everything Gold needs before it writes anything.

`rebuild --from silver` replaces Silver and then publishes Gold, so a refusal
Gold would make has to come first: a configuration error "fails the build and
changes nothing". Every test passes `main` an explicit environment.
"""

import unittest
from collections.abc import Callable
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.pipelines import household, present_again, write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
EXIT_REFUSED_ENVIRONMENT = 4
_MARCH_9 = date(2026, 3, 9)


def _refusal_leaves_silver_untouched(
    name: str, ruin: Callable[[Profile], None]
) -> None:
    """Spoil one household input, and expect a refusal that replaced nothing.

    A repeat run is presented first, so the Silver a rebuild would derive
    differs from the stored one: only a rebuild that wrote before it refused
    could leave the stored Silver changed.
    """
    with TemporaryDirectory() as directory:
        built = household(Path(directory))
        with SilverStore(built.profile) as silver:
            before = silver.read()
        present_again(built.profile, "danske-20260310.csv", _MARCH_9)
        ruin(built.profile)

        status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

        assert status == EXIT_REFUSED_INPUT
        assert stdout == ""
        assert name in stderr
        with SilverStore(built.profile) as silver:
            assert silver.read() == before


def _delete_taxonomy(profile: Profile) -> None:
    profile.input_file("taxonomy.toml").unlink()


def _break_taxonomy(profile: Profile) -> None:
    profile.input_file("taxonomy.toml").write_text("[group.food\n", encoding="utf-8")


def _close_account_early(profile: Profile) -> None:
    """Close the account before its stored transaction, which Gold refuses."""
    registry = ACCOUNTS.replace(
        'bank_account_number = "0012345678"\n',
        'bank_account_number = "0012345678"\nclosed_on = 2026-02-20\n',
    )
    write_inputs(profile, registry)


class RebuildPreflightTests(unittest.TestCase):
    def test_a_missing_taxonomy_leaves_silver_untouched(self) -> None:
        _refusal_leaves_silver_untouched("taxonomy.toml", _delete_taxonomy)

    def test_a_malformed_taxonomy_leaves_silver_untouched(self) -> None:
        _refusal_leaves_silver_untouched("taxonomy.toml", _break_taxonomy)

    def test_an_account_closed_before_its_transaction_leaves_silver_untouched(
        self,
    ) -> None:
        _refusal_leaves_silver_untouched("closed_on", _close_account_early)

    def test_a_missing_gold_store_refuses_before_silver_is_replaced(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            for stage in ("bronze", "silver"):
                assert migrate(profile_file, "--stage", stage)[0] == EXIT_OK
            built = development_profile(folder)
            write_inputs(built)

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "Gold" in stderr
            with SilverStore(built) as silver:
                assert not silver.is_built()


if __name__ == "__main__":
    unittest.main()
