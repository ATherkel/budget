"""Bronze behavior through the public store interface, using synthetic inputs."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kernel.bronze import BronzeStore


class BronzeStoreTests(unittest.TestCase):
    def test_import_preserves_payload_provenance_and_fields_after_reopening(self):
        # Explicit Windows-1252 bytes, CRLF, and no final line break.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        # Independently calculated with .NET SHA256, not the Bronze code.
        expected_payload_id = (
            "46677a064218cc78e114e60ba2a01525fe2c28f5de0e594284e34914b7be895a"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            database = root / "bronze.sqlite3"

            before_import = datetime.now(UTC)
            with BronzeStore(database) as store:
                run = store.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
            after_import = datetime.now(UTC)

            # A retained import must not depend on the original file remaining.
            source.unlink()

            with BronzeStore(database) as reopened:
                saved_run = reopened.get_import_run(run.import_run_id)
                payload = reopened.get_payload(saved_run.payload_id)
                records = reopened.get_source_records(saved_run.payload_id)
                failures = reopened.get_format_failures(saved_run.payload_id)

            self.assertIsInstance(run.import_run_id, str)
            self.assertTrue(run.import_run_id)
            self.assertEqual(saved_run, run)
            self.assertEqual(saved_run.payload_id, expected_payload_id)
            self.assertEqual(saved_run.declared_account_id, "daily-account")
            self.assertEqual(saved_run.source_format, "danske-csv-v1")
            self.assertEqual(saved_run.original_filename, "synthetic-20260914.csv")
            self.assertEqual(saved_run.exported_on, date(2026, 9, 14))
            self.assertEqual(saved_run.exported_on_source, "filename")
            self.assertEqual(saved_run.covers_through, date(2026, 9, 13))
            self.assertEqual(saved_run.covers_through_source, "declared")
            self.assertEqual(saved_run.started_at.utcoffset(), timedelta(0))
            self.assertLessEqual(before_import, saved_run.started_at)
            self.assertLessEqual(saved_run.started_at, after_import)
            self.assertEqual(saved_run.outcome, "stored")
            self.assertIsNone(saved_run.repeat_of)

            self.assertEqual(payload.payload_id, expected_payload_id)
            self.assertEqual(payload.byte_length, 166)
            self.assertEqual(payload.content, content)
            self.assertEqual(failures, ())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].payload_id, expected_payload_id)
            self.assertEqual(records[0].record_ordinal, 1)
            self.assertEqual(
                dict(records[0].fields),
                {
                    "Dato": "12-09-2026",
                    "Kategori": " Mad ",
                    "Underkategori": " Dagligvarer ",
                    "Tekst": ' Café, "Øen"  ',
                    "Beløb": "-45,00",
                    "Saldo": "955,00",
                    "Status": "Udført",
                    "Afstemt": "Nej",
                },
            )

    def test_same_bytes_record_repeat_with_own_dates_and_unchanged_payload(self):
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_source = root / "synthetic-20260914.csv"
            later_source = root / "synthetic-20260916.csv"
            original_source.write_bytes(content)
            later_source.write_bytes(content)
            database = root / "bronze.sqlite3"

            with BronzeStore(database) as store:
                original_run = store.import_file(
                    original_source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                original_payload = store.get_payload(original_run.payload_id)
                original_records = store.get_source_records(original_run.payload_id)

            before_repeat = datetime.now(UTC)
            with BronzeStore(database) as reopened:
                repeat = reopened.import_file(
                    later_source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 15),
                )
            after_repeat = datetime.now(UTC)

            with BronzeStore(database) as reopened:
                saved_repeat = reopened.get_import_run(repeat.import_run_id)
                self.assertEqual(saved_repeat, repeat)
                self.assertNotEqual(saved_repeat.import_run_id, original_run.import_run_id)
                self.assertEqual(saved_repeat.outcome, "repeat")
                self.assertEqual(saved_repeat.repeat_of, original_run.import_run_id)
                self.assertEqual(saved_repeat.payload_id, original_run.payload_id)
                self.assertEqual(saved_repeat.declared_account_id, "daily-account")
                self.assertEqual(saved_repeat.source_format, "danske-csv-v1")
                self.assertEqual(saved_repeat.original_filename, "synthetic-20260916.csv")
                self.assertEqual(saved_repeat.exported_on, date(2026, 9, 16))
                self.assertEqual(saved_repeat.exported_on_source, "filename")
                self.assertEqual(saved_repeat.covers_through, date(2026, 9, 15))
                self.assertEqual(saved_repeat.covers_through_source, "declared")
                self.assertLessEqual(before_repeat, saved_repeat.started_at)
                self.assertLessEqual(saved_repeat.started_at, after_repeat)
                self.assertEqual(
                    reopened.get_import_run(original_run.import_run_id), original_run
                )
                self.assertEqual(
                    reopened.get_payload(saved_repeat.payload_id), original_payload
                )
                self.assertEqual(
                    reopened.get_source_records(saved_repeat.payload_id), original_records
                )
                self.assertEqual(reopened.get_format_failures(saved_repeat.payload_id), ())

    def test_same_bytes_for_another_account_record_a_refused_run(self):
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            database = root / "bronze.sqlite3"

            with BronzeStore(database) as store:
                original = store.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                original_records = store.get_source_records(original.payload_id)

            with BronzeStore(database) as reopened:
                refused = reopened.import_file(
                    source,
                    declared_account_id="savings-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )

            with BronzeStore(database) as reopened:
                saved = reopened.get_import_run(refused.import_run_id)
                self.assertEqual(saved, refused)
                self.assertNotEqual(saved.import_run_id, original.import_run_id)
                self.assertEqual(saved.outcome, "refused")
                self.assertEqual(saved.declared_account_id, "savings-account")
                self.assertEqual(saved.payload_id, original.payload_id)
                self.assertIsNone(saved.repeat_of)
                self.assertEqual(
                    reopened.get_import_run(original.import_run_id), original
                )
                self.assertEqual(
                    reopened.get_payload(original.payload_id).content, content
                )
                self.assertEqual(
                    reopened.get_source_records(original.payload_id),
                    original_records,
                )


if __name__ == "__main__":
    unittest.main()
