# Copyright 2026 Therkel
"""`budget import` refuses what it can foresee, and finishes what it cannot.

Gold needs the whole household's files and the imported data, so some refusals
only show once a file is stored. The ones that can be foreseen are refused
before any inbox file is consumed. The others leave Bronze ahead of Silver and
Gold, and the next `import`, with or without inbox files, finishes the
rebuild, the publication and production's backup. Every test passes `main` an
explicit environment, and every account, date and amount is synthetic.
"""

import json
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import complete_backup_sets
from budget.gold.store import GoldStore
from budget.inputs import ConfigurationError
from budget.profiles import Profile
from tests.backups.sets import run_ids
from tests.cli.commands import import_, migrate
from tests.cli.imports import clean_checkout, write_ranges
from tests.cli.pipelines import EXPORT, Prepared, prepared, write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
EXIT_REFUSED_ENVIRONMENT = 4
EXPORT_NAME = "danske-20260305.csv"
EARLY_CLOSE = ACCOUNTS.replace(
    'bank_account_number = "0012345678"\n',
    'bank_account_number = "0012345678"\nclosed_on = 2026-02-20\n',
)
DECISION = {
    "format": 1,
    "entry": 1,
    "decision_id": "d-0001",
    "recorded_at": "2026-04-10T17:02:11Z",
    "kind": "classify",
    "targets": ["a-transaction"],
    "category": "gifts",
    "reason": "A present",
    "supersedes": [],
}


def _run_import(base: Prepared) -> tuple[int, str, str]:
    """Run `budget import` over the household's declared range."""
    ranges = write_ranges(
        base.profile_file.parent, default=("2026-03-01", "2026-03-04")
    )
    if base.profile.name != "production":
        return import_(base.profile_file, "--ranges", str(ranges))
    with mock.patch("subprocess.run", side_effect=clean_checkout):
        return import_(base.profile_file, "--ranges", str(ranges))


def _nothing_stored(profile: Profile, source: Path) -> None:
    """Assert the export is still in the inbox and nothing reached Bronze."""
    assert source.read_bytes() == EXPORT
    assert not profile.import_log_file.exists()
    assert run_ids(profile.bronze_store) == []


@contextmanager
def _gold_refuses_after_the_files_are_stored() -> Iterator[None]:
    """Make the rebuild after the Bronze writes refuse, as a Gold refusal would.

    The household's files are read once, before the first write, so nothing a
    person edits during the import reaches the build; this stands in for a
    refusal that no preflight could foresee.
    """
    refusal = ConfigurationError(
        ('accounts.toml: account "joint-current": closed_on is before a transaction',)
    )
    with mock.patch("budget.inbox.rebuild_through_gold", side_effect=refusal):
        yield


def _close_early(profile: Profile) -> None:
    """Close the account before the incoming export's transaction."""
    write_inputs(profile, EARLY_CLOSE)


def _log_records(profile: Profile) -> list[dict[str, object]]:
    text = profile.log_file("commands.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


class ForeseeableRefusalTests(unittest.TestCase):
    def _refused_before_storing(
        self,
        ruin: Callable[[Profile], object],
        status: int,
        named: str,
        *,
        name: str = "development",
    ) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory), name=name)
            source = drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            ruin(base.profile)

            result = _run_import(base)

            assert result[0] == status
            assert result[1] == ""
            assert named in result[2]
            _nothing_stored(base.profile, source)

    def test_a_missing_taxonomy_stores_nothing(self) -> None:
        self._refused_before_storing(
            lambda profile: profile.input_file("taxonomy.toml").unlink(),
            EXIT_REFUSED_INPUT,
            "taxonomy.toml",
        )

    def test_an_invalid_decision_log_stores_nothing(self) -> None:
        self._refused_before_storing(
            lambda profile: profile.input_file("decisions.jsonl").write_text(
                '{"decision_id": "d-0001"}\n', encoding="utf-8"
            ),
            EXIT_REFUSED_INPUT,
            "decisions.jsonl",
        )

    def test_a_decision_naming_a_dropped_category_stores_nothing(self) -> None:
        self._refused_before_storing(
            lambda profile: profile.input_file("decisions.jsonl").write_text(
                json.dumps(DECISION) + "\n", encoding="utf-8"
            ),
            EXIT_REFUSED_INPUT,
            "gifts",
        )

    def test_an_account_closed_before_an_incoming_transaction_stores_nothing(
        self,
    ) -> None:
        self._refused_before_storing(_close_early, EXIT_REFUSED_INPUT, "closed_on")

    def test_a_commit_git_cannot_name_stores_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory), name="production")
            source = drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            ranges = write_ranges(Path(directory), default=("2026-03-01", "2026-03-04"))

            def unnameable(arguments: list[str], **options: object) -> mock.Mock:
                completed = clean_checkout(arguments, **options)
                if "rev-parse" in arguments:
                    completed.returncode = 128
                return completed

            with mock.patch("subprocess.run", side_effect=unnameable):
                status, stdout, stderr = import_(
                    base.profile_file, "--ranges", str(ranges)
                )

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "cannot be checked" in stderr
            _nothing_stored(base.profile, source)

    def test_a_missing_gold_store_stores_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            for stage in ("bronze", "silver"):
                assert migrate(profile_file, "--stage", stage)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            source = drop(profile, "joint-current", EXPORT_NAME, EXPORT)

            status, stdout, stderr = _run_import(Prepared(profile_file, profile))

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "Gold" in stderr
            _nothing_stored(profile, source)


class FailureAndRetryTests(unittest.TestCase):
    def test_a_failure_after_the_commit_is_finished_by_the_next_import(self) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory))
            drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)

            with _gold_refuses_after_the_files_are_stored():
                status, stdout, stderr = _run_import(base)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "[1] joint-current  stored" in stdout
            assert "closed_on" in stderr
            assert "budget import" in stderr
            assert len(run_ids(base.profile.bronze_store)) == 1
            with GoldStore(base.profile) as gold:
                assert gold.current() is None
            failed = _log_records(base.profile)[-1]
            assert failed["command"] == "import"
            counts = failed["counts"]
            assert isinstance(counts, dict)
            assert counts["published"] == 0

            status, stdout, stderr = _run_import(base)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was imported" not in stdout
            assert "published publication 1" in stdout
            with GoldStore(base.profile) as gold:
                current = gold.current()
            assert current is not None
            assert current.publication_id == 1
            retried = _log_records(base.profile)[-1]
            counts = retried["counts"]
            assert isinstance(counts, dict)
            assert counts["published"] == 1

    def test_production_still_backs_up_after_the_failure_and_again_after_the_retry(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory), name="production")
            drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            sets_before = len(complete_backup_sets(base.profile))

            with _gold_refuses_after_the_files_are_stored():
                status, _, stderr = _run_import(base)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "closed_on" in stderr
            assert len(complete_backup_sets(base.profile)) == sets_before + 1

            status, stdout, stderr = _run_import(base)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            assert "Backup" in stdout
            assert len(complete_backup_sets(base.profile)) == sets_before + 2

    def test_a_retry_with_new_inbox_files_finishes_the_outstanding_work_too(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory))
            drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            with _gold_refuses_after_the_files_are_stored():
                assert _run_import(base)[0] == EXIT_REFUSED_ENVIRONMENT
            drop(
                base.profile,
                "joint-current",
                "danske-20260306.csv",
                payload("02.03.2026"),
            )

            status, stdout, stderr = _run_import(base)

            assert (status, stderr) == (EXIT_OK, "")
            assert "[1] joint-current  stored" in stdout
            assert "published publication 1" in stdout
            assert len(run_ids(base.profile.bronze_store)) == 2
            with GoldStore(base.profile) as gold:
                recipe = gold.recipe(1)
            assert len(recipe.import_runs) == 2

    def test_an_import_with_nothing_outstanding_changes_and_backs_up_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory), name="production")
            drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            assert _run_import(base)[0] == EXIT_OK
            sets_before = len(complete_backup_sets(base.profile))

            status, stdout, stderr = _run_import(base)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was imported" in stdout
            assert len(complete_backup_sets(base.profile)) == sets_before
            with GoldStore(base.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]


class RefusedFileTests(unittest.TestCase):
    def test_a_refused_file_retried_publishes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory))
            drop(base.profile, "joint-current", EXPORT_NAME, EXPORT)
            assert _run_import(base)[0] == EXIT_OK
            # The same bytes again, with a range that ends after the export date.
            for name in ("danske-20260312.csv", "danske-20260313.csv"):
                drop(base.profile, "joint-current", name, EXPORT)
                ranges = write_ranges(
                    Path(directory), default=("2026-03-01", "2026-03-20")
                )

                status, stdout, _ = import_(base.profile_file, "--ranges", str(ranges))

                assert status == EXIT_REFUSED_INPUT
                assert "nothing was published" in stdout
            with GoldStore(base.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]


if __name__ == "__main__":
    unittest.main()
