# Copyright 2026 Therkel
"""`budget rebuild` publishes Gold from the stored Silver and the household inputs.

Every test passes `main` an explicit environment. The Gold publication is read
back through `GoldStore`, so a test sees what a dashboard would.
"""

import re
import unittest
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.store import GoldStore
from budget.inputs import load_configuration
from budget.locking import WriterLock, writer_lock
from budget.rebuilding import GoldRebuild, rebuild_from_gold
from budget.silver import SilverStore
from tests.cli.commands import rebuild
from tests.cli.pipelines import EXPORT, household

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class FirstPublicationTests(unittest.TestCase):
    def test_rebuild_publishes_the_first_publication_from_silver(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 1" in stdout
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert (current.publication_id, current.kind) == (1, "pipeline")
                assert gold.recipe(1) == Recipe(
                    import_runs=frozenset(
                        {
                            RecipeImportRun(
                                built.import_run_id, sha256(EXPORT).hexdigest()
                            )
                        }
                    ),
                    configuration_fingerprint=load_configuration(
                        built.profile
                    ).fingerprint,
                    decision_log_position=0,
                    decision_log_prefix_sha256=sha256(b"").hexdigest(),
                    code_version=None,
                    contract_version="0.2",
                    silver_identity_version="1",
                    python_version="",
                    sqlite_version="",
                )
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
                assert [t.description for t in transactions] == ["Café"]


class UnchangedRecipeTests(unittest.TestCase):
    def test_a_second_rebuild_with_nothing_changed_publishes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                moves = gold.pointer_history()

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == moves
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2


class ClockTests(unittest.TestCase):
    def test_two_builds_of_one_recipe_at_different_times_share_a_fingerprint(
        self,
    ) -> None:
        first_run = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)
        second_run = datetime(2026, 9, 1, 17, 30, tzinfo=UTC)
        published = []
        for name, now in (("early", first_run), ("late", second_run)):
            with TemporaryDirectory() as directory:
                built = household(Path(directory) / name)
                with writer_lock(built.profile) as lock:
                    published.append(rebuild_from_gold(lock, now=now).publication)

        early, late = published
        assert (early.built_at, late.built_at) == (first_run, second_run)
        assert re.fullmatch("[0-9a-f]{64}", early.result_fingerprint)
        assert early.result_fingerprint == late.result_fingerprint


class WriterLockTests(unittest.TestCase):
    def test_a_second_writing_command_refuses_while_a_rebuild_holds_the_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            overlapping: list[tuple[int, str, str]] = []

            def rebuild_while_another_command_runs(
                lock: WriterLock, *, now: datetime
            ) -> GoldRebuild:
                overlapping.append(rebuild(built.profile_file))
                return rebuild_from_gold(lock, now=now)

            with mock.patch(
                "budget.cli.rebuild_from_gold", rebuild_while_another_command_runs
            ):
                status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            ((second_status, second_stdout, second_stderr),) = overlapping
            assert (second_status, second_stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "another command is running" in second_stderr
            with GoldStore(built.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]


class FromSilverTests(unittest.TestCase):
    def test_rebuild_from_silver_rebuilds_silver_then_publishes_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            with SilverStore(built.profile) as silver:
                assert silver.read().transactions == ()

            status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "1 admitted" in stdout
            assert "published publication 1" in stdout
            with SilverStore(built.profile) as silver:
                assert [t.description for t in silver.read().transactions] == ["Café"]
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                transactions = gold.open(current.publication_id).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
                assert [t.description for t in transactions] == ["Café"]


if __name__ == "__main__":
    unittest.main()
