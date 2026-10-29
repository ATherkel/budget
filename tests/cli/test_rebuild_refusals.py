# Copyright 2026 Therkel
"""A refused Gold rebuild publishes nothing, and says what to put right.

Nothing includes the bytes of `gold.db`: `gold.build` promises "nothing was
published", and only the pipeline can keep that promise.
"""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.lifecycle import Lifecycle, import_export, lifecycle
from tests.importing.households import ACCOUNTS

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
ONLY_ANOTHER_ACCOUNT = """\
format = 1

[account.joint-offset]
display_name = "Joint offset"
account_type = "current"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
"""
SAVINGS_ROWS = (("03.02.2026", "RENTE", "10,00", "10,00"),)


def _with_two_accounts_published(folder: Path) -> Lifecycle:
    """Publish P1 from Silver that holds transactions on two accounts."""
    household = lifecycle(folder)
    import_export(
        household.profile,
        "danske-20260304.csv",
        SAVINGS_ROWS,
        through=date(2026, 3, 3),
        account_id="joint-savings",
    )
    assert rebuild(household.profile_file)[0] == EXIT_OK
    return household


class UndeclaredAccountTests(unittest.TestCase):
    def test_accounts_removed_from_the_registry_refuse_and_change_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            household = _with_two_accounts_published(Path(directory))
            store = household.profile.gold_store
            before = sha256(store.read_bytes()).hexdigest()
            household.profile.accounts_file.write_text(
                ONLY_ANOTHER_ACCOUNT, encoding="utf-8"
            )

            status, stdout, stderr = rebuild(household.profile_file)

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert 'account "joint-current" is not declared' in stderr
            assert 'account "joint-savings" is not declared' in stderr
            assert "nothing was published" in stderr
            assert sha256(store.read_bytes()).hexdigest() == before
            with GoldStore(household.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]

    def test_declaring_the_accounts_again_lets_the_rerun_publish(self) -> None:
        with TemporaryDirectory() as directory:
            household = _with_two_accounts_published(Path(directory))
            registry = household.profile.accounts_file
            registry.write_text(ONLY_ANOTHER_ACCOUNT, encoding="utf-8")
            assert rebuild(household.profile_file)[0] == EXIT_REFUSED_INPUT
            # The savings account closed after its last transaction.
            registry.write_text(ACCOUNTS + "closed_on = 2026-06-30\n", encoding="utf-8")

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(household.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1, 2]


if __name__ == "__main__":
    unittest.main()
