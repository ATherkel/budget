# Copyright 2026 Therkel
"""`budget rebuild --from bronze` regenerates Bronze's derived records.

The retained payloads are the only input it needs: the inbox files are gone
before every test here runs it. Every test passes `main` an explicit
environment, and Bronze is read back through its public reads.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore
from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.silver import SilverStore
from tests.cli.commands import rebuild
from tests.cli.pipelines import EXPORT, household
from tests.importing.households import drop

EXIT_OK = 0
EXPORT_FIELDS = {
    "Dato": "01.03.2026",
    "Kategori": " Mad ",
    "Underkategori": " Dagligvarer ",
    "Tekst": "Café",
    "Beløb": "-45,00",
    "Saldo": "955,00",
    "Status": "Udført",
    "Afstemt": "Nej",
}


class RebuildFromBronzeTests(unittest.TestCase):
    def test_retained_payloads_rebuild_bronze_silver_and_gold_without_the_inbox(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            inbox = built.profile.inbox / "joint-current"
            for leftover in inbox.glob("*"):
                leftover.unlink()

            status, stdout, stderr = rebuild(built.profile_file, "--from", "bronze")

            assert (status, stderr) == (EXIT_OK, "")
            assert "1 admitted" in stdout
            assert "published publication 1" in stdout
            with BronzeStore(built.profile) as bronze:
                (run,) = bronze.import_runs()
                records = bronze.get_source_records(run.payload_id)
            assert [dict(record.fields) for record in records] == [EXPORT_FIELDS]
            with SilverStore(built.profile) as silver:
                assert [t.description for t in silver.read().transactions] == ["Café"]
            with GoldStore(built.profile) as gold:
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
            assert [t.description for t in transactions] == ["Café"]


class ProvenanceTests(unittest.TestCase):
    def test_a_rebuild_is_not_an_import_and_keeps_every_run_and_the_log(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            profile = built.profile
            # The same bytes presented again, and a declaration Bronze refuses.
            for name, through in (
                ("danske-20260310.csv", date(2026, 3, 9)),
                ("danske-20260312.csv", date(2026, 3, 20)),
            ):
                source = drop(profile, "joint-current", name, EXPORT)
                with writer_lock(profile) as lock:
                    import_inbox_file(lock, source, Coverage(date(2026, 3, 1), through))
            with BronzeStore(profile) as bronze:
                runs_before = bronze.import_runs()
            log_before = profile.import_log_file.read_bytes()
            assert [run.outcome for run in runs_before] == [
                "stored",
                "repeat",
                "refused",
            ]

            status, _, stderr = rebuild(built.profile_file, "--from", "bronze")

            assert (status, stderr) == (EXIT_OK, "")
            with BronzeStore(profile) as bronze:
                assert bronze.import_runs() == runs_before
            assert profile.import_log_file.read_bytes() == log_before


if __name__ == "__main__":
    unittest.main()
