# Copyright 2026 Therkel
"""`budget rebuild` publishes Gold from the stored Silver and the household inputs.

Every test passes `main` an explicit environment. The Gold publication is read
back through `GoldStore`, so a test sees what a dashboard would.
"""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.store import GoldStore
from budget.inputs import load_configuration
from tests.cli.commands import rebuild
from tests.cli.pipelines import EXPORT, household

EXIT_OK = 0


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


if __name__ == "__main__":
    unittest.main()
