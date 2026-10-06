# Copyright 2026 Therkel
"""`budget rebuild` refuses a nonempty decision log it cannot read yet.

The decision-log reader is a later slice. Until it exists, a log that holds any
manual decision must refuse the rebuild rather than silently build as if the
household had made no decision, and the stored result must stay as it was.
Every test passes `main` an explicit environment.
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
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
DECISION_LOG = "decisions.jsonl"
SENTINEL = "SENSITIVE-SENTINEL-REASON"
# One synthetic *withdrawn* entry, in the documented `decisions.jsonl` shape.
DECISION_ENTRY = (
    json.dumps(
        {
            "format": 1,
            "entry": 1,
            "decision_id": "d-0001",
            "recorded_at": "2026-04-10T17:02:11Z",
            "kind": "withdrawn",
            "targets": ["SENSITIVE-SENTINEL-TARGET"],
            "reason": SENTINEL,
            "supersedes": [],
        }
    )
    + "\n"
)


def _migrated_profile_with_accounts(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _import_one_export(profile: Profile) -> None:
    """Seed Bronze with one stored import run, as `budget import` will."""
    source = drop(
        profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
    )
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )


class RebuildDecisionLogTests(unittest.TestCase):
    def test_a_nonempty_decision_log_refuses_the_rebuild(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _migrated_profile_with_accounts(profile_file, folder)
            _import_one_export(profile)

            # With no decision log at all, the rebuild builds and stores.
            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                before = store.read()
            assert [t.description for t in before.transactions] == ["Café"]

            log = profile.input_file(DECISION_LOG)
            log.write_text(DECISION_ENTRY, encoding="utf-8")

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_REFUSED_INPUT
            assert DECISION_LOG in stderr
            assert "nothing was written" in stderr
            # The refusal never repeats the household's own decision text.
            assert SENTINEL not in stderr
            assert SENTINEL not in stdout
            with SilverStore(profile) as store:
                assert store.read() == before

            # An empty log means no decisions, so the rebuild is allowed.
            log.write_text("", encoding="utf-8")
            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK


if __name__ == "__main__":
    unittest.main()
