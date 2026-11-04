# Copyright 2026 Therkel
"""`budget import` after a `void-import-run` decision.

A voided run no longer stands for its export: presenting the bytes again is a
new presentation, never the retry of that run (`operations.md`, *Failure and
Retry*), and never an account conflict with it (`bronze-layer.md`). The void
is written into the household's own decision log, as `budget decide` would
record it.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from tests.cli.commands import import_
from tests.cli.imports import write_ranges
from tests.cli.pipelines import prepared
from tests.importing.households import drop, log_entries, payload

EXIT_OK = 0
EXPORT = "danske-20260310.csv"


def void(profile: Profile, import_run_id: str) -> None:
    """Record the first decision of the log: a void of `import_run_id`."""
    entry = {
        "format": 1,
        "entry": 1,
        "decision_id": "d-0001",
        "recorded_at": "2026-03-11T09:00:00Z",
        "kind": "void-import-run",
        "targets": [import_run_id],
        "reason": "Declared with the wrong range",
        "supersedes": [],
    }
    profile.input_file("decisions.jsonl").write_text(
        json.dumps(entry) + "\n", encoding="utf-8"
    )


class VoidedRunTests(unittest.TestCase):
    def test_a_voided_runs_file_dropped_again_with_a_corrected_range_is_stored(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            household = prepared(folder)
            profile = household.profile
            content = payload("01.03.2026")
            drop(profile, "joint-current", EXPORT, content)
            wrong = write_ranges(folder, default=("2026-03-01", "2026-03-09"))
            assert import_(household.profile_file, "--ranges", str(wrong))[0] == EXIT_OK
            (voided,) = log_entries(profile)
            void(profile, str(voided["import_run_id"]))
            source = drop(profile, "joint-current", EXPORT, content)
            corrected = write_ranges(folder, default=("2026-02-01", "2026-03-09"))

            status, _, stderr = import_(
                household.profile_file, "--ranges", str(corrected)
            )

            assert (status, stderr) == (EXIT_OK, "")
            entries = log_entries(profile)
            assert len(entries) == 2
            new = entries[1]
            assert new["import_run_id"] != voided["import_run_id"]
            assert (new["outcome"], new["repeat_of"]) == ("stored", None)
            assert (new["covers_from"], new["covers_through"]) == (
                "2026-02-01",
                "2026-03-09",
            )
            assert not source.exists()
