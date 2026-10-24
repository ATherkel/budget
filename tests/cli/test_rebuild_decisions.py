# Copyright 2026 Therkel
"""`budget rebuild --from silver` applies the Silver decisions in the log.

The decision log is the household's: a rebuild reads it, applies every
decision in force, and never builds as if the household had made none. Every
test passes `main` an explicit environment.
"""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import drop, payload

EXIT_OK = 0
DECISION_LOG = "decisions.jsonl"


def _migrated_profile_with_accounts(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    write_inputs(profile)
    return profile


def _import_one_export(profile: Profile) -> str:
    """Seed Bronze with one stored import run, and return its identifier."""
    source = drop(
        profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
    )
    with writer_lock(profile) as lock:
        imported = import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )
    return imported.import_run.import_run_id


def _void(import_run_id: str) -> str:
    """One `void-import-run` entry, in the documented `decisions.jsonl` shape."""
    return (
        json.dumps(
            {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "void-import-run",
                "targets": [import_run_id],
                "reason": "The wrong account's export",
                "supersedes": [],
            }
        )
        + "\n"
    )


class RebuildDecisionLogTests(unittest.TestCase):
    def test_a_voided_import_run_leaves_the_rebuilt_silver(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _migrated_profile_with_accounts(profile_file, folder)
            run_id = _import_one_export(profile)

            # With no decision log at all, the rebuild builds and stores.
            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                assert [t.description for t in store.read().transactions] == ["Café"]

            profile.input_file(DECISION_LOG).write_text(_void(run_id), encoding="utf-8")

            status, _, stderr = rebuild(profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            with SilverStore(profile) as store:
                assert store.read().transactions == ()


if __name__ == "__main__":
    unittest.main()
