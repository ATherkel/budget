"""Bronze behavior through the public store interface, using synthetic inputs."""

from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from kernel.bronze import BronzeStore


# The on-disk shape the baseline BronzeStore wrote, copied verbatim. A test that
# models a store left behind by that code pins what it has to keep reading; the
# baseline module itself is deliberately not a test dependency.
_LEGACY_BRONZE_SCHEMA = """
CREATE TABLE raw_payloads (
    payload_id TEXT PRIMARY KEY,
    byte_length INTEGER NOT NULL,
    content BLOB NOT NULL
);
CREATE TABLE import_runs (
    import_run_id TEXT PRIMARY KEY,
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    declared_account_id TEXT NOT NULL,
    source_format TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    exported_on TEXT NOT NULL,
    exported_on_source TEXT NOT NULL,
    covers_through TEXT NOT NULL,
    covers_through_source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    repeat_of TEXT REFERENCES import_runs(import_run_id)
);
CREATE TABLE source_records (
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    record_ordinal INTEGER NOT NULL,
    fields TEXT NOT NULL,
    PRIMARY KEY (payload_id, record_ordinal)
);
CREATE TABLE format_failures (
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    source_format TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (payload_id, source_format)
);
"""


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


    def test_malformed_payloads_yield_a_format_failure_and_no_source_records(self):
        well_formed = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = {
            "unexpected header": well_formed.replace(b'"Afstemt"', b'"Afstemt?"'),
            "utf-8 encoded header": well_formed.decode("cp1252").encode("utf-8"),
            "byte undefined in windows-1252": well_formed[:-1] + b"\x81",
        }
        header_failure_reasons = []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"

            for index, (label, content) in enumerate(malformed.items()):
                with self.subTest(payload=label):
                    source = root / f"synthetic-{index}-20260914.csv"
                    source.write_bytes(content)
                    with BronzeStore(database) as store:
                        run = store.import_file(
                            source,
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_through=date(2026, 9, 13),
                        )
                    with BronzeStore(database) as reopened:
                        payload = reopened.get_payload(run.payload_id)
                        records = reopened.get_source_records(run.payload_id)
                        failures = reopened.get_format_failures(run.payload_id)

                    self.assertEqual(run.outcome, "stored")
                    self.assertEqual(run.covers_through, date(2026, 9, 13))
                    self.assertEqual(run.covers_through_source, "declared")
                    self.assertEqual(payload.content, content)
                    self.assertEqual(payload.byte_length, len(content))
                    self.assertEqual(records, ())
                    self.assertEqual(len(failures), 1)
                    self.assertEqual(failures[0].payload_id, run.payload_id)
                    self.assertEqual(failures[0].source_format, "danske-csv-v1")
                    self.assertTrue(failures[0].reason)
                    # A failure reason is a verdict, never a copy of the source.
                    self.assertNotIn(source.name, failures[0].reason)
                    self.assertNotIn("Dato", failures[0].reason)
                    self.assertNotIn("Afstemt", failures[0].reason)
                    if "header" in label:
                        header_failure_reasons.append(failures[0].reason)

            self.assertEqual(len(header_failure_reasons), 2)
            self.assertEqual(header_failure_reasons[0], header_failure_reasons[1])


    def test_import_metadata_failures_happen_before_persistence(self):
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        expected_payload_id = (
            "46677a064218cc78e114e60ba2a01525fe2c28f5de0e594284e34914b7be895a"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            no_suffix = root / "synthetic.csv"
            impossible_suffix = root / "synthetic-20260931.csv"
            no_suffix.write_bytes(content)
            impossible_suffix.write_bytes(content)

            with BronzeStore(database) as store:
                with self.assertRaises(ValueError) as missing_export_date:
                    store.import_file(
                        no_suffix,
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                self.assertNotIn("synthetic", str(missing_export_date.exception))
                with self.assertRaises(ValueError) as impossible_export_date:
                    store.import_file(
                        impossible_suffix,
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                self.assertNotIn("synthetic", str(impossible_export_date.exception))
                with self.assertRaises(ValueError) as unknown_format:
                    store.import_file(
                        no_suffix,
                        declared_account_id="daily-account",
                        source_format="nordea-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                self.assertNotIn("synthetic", str(unknown_format.exception))

            with BronzeStore(database) as reopened:
                # A refused declaration is not an import: no payload was stored.
                with self.assertRaises(KeyError):
                    reopened.get_payload(expected_payload_id)

            # A declared export date is the run's date, whatever the filename
            # cannot say: the impossible suffix is never read as a date.
            with BronzeStore(database) as store:
                declared = store.import_file(
                    impossible_suffix,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    exported_on=date(2026, 9, 14),
                    covers_through=date(2026, 9, 13),
                )
            self.assertEqual(declared.exported_on, date(2026, 9, 14))
            self.assertEqual(declared.exported_on_source, "declared")


    def test_an_unreadable_transaction_date_is_a_format_failure(self):
        header = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
        )
        row = (
            b'%s," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = {
            "impossible date": b'"31-02-2026"',
            "unexpected date shape": b'"2026-09-12"',
        }
        failure_reasons = []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"

            for index, (label, dato) in enumerate(malformed.items()):
                with self.subTest(dato=label):
                    content = header + row % dato
                    source = root / f"synthetic-{index}-20260914.csv"
                    source.write_bytes(content)
                    with BronzeStore(database) as store:
                        run = store.import_file(
                            source,
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_through=date(2026, 9, 13),
                        )
                    with BronzeStore(database) as reopened:
                        payload = reopened.get_payload(run.payload_id)
                        records = reopened.get_source_records(run.payload_id)
                        failures = reopened.get_format_failures(run.payload_id)

                    # An unreadable Dato cannot bound a coverage declaration,
                    # so the payload is retained with a verdict, never guessed.
                    self.assertEqual(run.outcome, "stored")
                    self.assertEqual(payload.content, content)
                    self.assertEqual(records, ())
                    self.assertEqual(len(failures), 1)
                    self.assertTrue(failures[0].reason)
                    self.assertNotIn(dato.decode("cp1252"), failures[0].reason)
                    self.assertNotIn(source.name, failures[0].reason)
                    failure_reasons.append(failures[0].reason)

            self.assertEqual(len(failure_reasons), 2)
            self.assertEqual(failure_reasons[0], failure_reasons[1])


    def test_a_declared_covers_through_is_bounded_and_never_clamped(self):
        # The row carrying the maximum Dato comes first and is cancelled, so a
        # bound read from row order or Status would land somewhere else.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Slettet","Nej"\r\n'
            b'"05-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","1000,00","Udf\xf8rt","Nej"'
        )
        cases = (
            ("after the export date", date(2026, 9, 15), "refused"),
            ("before the last transaction", date(2026, 9, 11), "refused"),
            ("on the last transaction", date(2026, 9, 12), "stored"),
            ("on the export date", date(2026, 9, 14), "repeat"),
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            database = root / "bronze.sqlite3"
            stored_run_id = None

            for label, declared, expected_outcome in cases:
                with self.subTest(covers_through=label):
                    with BronzeStore(database) as store:
                        run = store.import_file(
                            source,
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_through=declared,
                        )
                    with BronzeStore(database) as reopened:
                        payload = reopened.get_payload(run.payload_id)
                        records = reopened.get_source_records(run.payload_id)

                    self.assertEqual(run.outcome, expected_outcome)
                    # A refused declaration is recorded as declared, not moved
                    # to the nearest acceptable date.
                    self.assertEqual(run.covers_through, declared)
                    self.assertEqual(run.covers_through_source, "declared")
                    self.assertEqual(payload.content, content)
                    self.assertEqual(
                        [record.record_ordinal for record in records], [1, 2]
                    )
                    self.assertEqual(dict(records[0].fields)["Dato"], "12-09-2026")
                    self.assertEqual(dict(records[0].fields)["Status"], "Slettet")

                    if expected_outcome == "stored":
                        stored_run_id = run.import_run_id
                        self.assertIsNone(run.repeat_of)
                    elif expected_outcome == "repeat":
                        self.assertEqual(run.repeat_of, stored_run_id)
                    else:
                        self.assertIsNone(run.repeat_of)


    def test_a_missing_declaration_falls_back_only_where_it_cannot_claim_too_much(self):
        def payload(dates):
            lines = [
                b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
                b'"Saldo","Status","Afstemt"'
            ]
            lines.extend(
                b'"%s"," Mad "," Dagligvarer "," Caf\xe9",'
                b'"-45,00","955,00","Udf\xf8rt","Nej"' % dato.encode("ascii")
                for dato in dates
            )
            return b"\r\n".join(lines)

        cases = (
            ("quiet tail in the last transaction's month", ("12-09-2026",), "stored"),
            ("fallback lands in a later month", ("31-08-2026",), "refused"),
            ("payload states no transactions", (), "refused"),
            ("fallback before the last transaction", ("20-09-2026",), "refused"),
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"

            for index, (label, dates, expected_outcome) in enumerate(cases):
                with self.subTest(declaration=label):
                    content = payload(dates)
                    source = root / f"synthetic-{index}-20260914.csv"
                    source.write_bytes(content)
                    with BronzeStore(database) as store:
                        run = store.import_file(
                            source,
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                        )
                    with BronzeStore(database) as reopened:
                        stored_payload = reopened.get_payload(run.payload_id)
                        records = reopened.get_source_records(run.payload_id)
                        failures = reopened.get_format_failures(run.payload_id)

                    self.assertEqual(run.outcome, expected_outcome)
                    self.assertIsNone(run.repeat_of)
                    self.assertEqual(run.exported_on, date(2026, 9, 14))
                    self.assertEqual(run.exported_on_source, "filename")
                    # The attempted fallback is recorded, not a date invented
                    # from the payload: covers_through is the export date.
                    self.assertEqual(run.covers_through, date(2026, 9, 14))
                    self.assertEqual(run.covers_through_source, "exported_on")
                    self.assertEqual(stored_payload.content, content)
                    self.assertEqual(
                        [record.record_ordinal for record in records],
                        list(range(1, len(dates) + 1)),
                    )
                    self.assertEqual(failures, ())


    def test_a_refused_or_failed_presentation_is_evidence_never_an_original(self):
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = content[:-1] + b"\x81"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            with BronzeStore(database) as store:
                refused = store.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 20),
                )
            self.assertEqual(refused.outcome, "refused")

            with BronzeStore(database) as reopened:
                # A refusal still retains the payload and its parsed records.
                self.assertEqual(
                    reopened.get_payload(refused.payload_id).content, content
                )
                refused_records = reopened.get_source_records(refused.payload_id)
                self.assertEqual(len(refused_records), 1)
                self.assertEqual(
                    dict(refused_records[0].fields)["Dato"], "12-09-2026"
                )

            # The same bytes declared correctly afterwards are a new import, not
            # a repeat of the refusal, and the refusal is left as it was.
            with BronzeStore(database) as reopened:
                corrected = reopened.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
            self.assertEqual(corrected.outcome, "stored")
            self.assertIsNone(corrected.repeat_of)
            self.assertNotEqual(corrected.import_run_id, refused.import_run_id)
            self.assertEqual(corrected.payload_id, refused.payload_id)

            with BronzeStore(database) as reopened:
                self.assertEqual(
                    reopened.get_import_run(refused.import_run_id), refused
                )
                # A refusal never seeds ownership: the same bytes stay refused
                # for another account, and still repeat the stored run only.
                foreign = reopened.import_file(
                    source,
                    declared_account_id="savings-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                self.assertEqual(foreign.outcome, "refused")
                self.assertIsNone(foreign.repeat_of)
                repeated = reopened.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                self.assertEqual(repeated.outcome, "repeat")
                self.assertEqual(repeated.repeat_of, corrected.import_run_id)

            # A payload that failed its format is stored once, so presenting it
            # again records its own repeat run and keeps the one failure.
            malformed_source = root / "synthetic-20260915.csv"
            malformed_source.write_bytes(malformed)
            with BronzeStore(database) as reopened:
                failed = reopened.import_file(
                    malformed_source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                )
                again = reopened.import_file(
                    malformed_source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                )
                failures = reopened.get_format_failures(failed.payload_id)
                failed_records = reopened.get_source_records(failed.payload_id)

            self.assertEqual(failed.outcome, "stored")
            self.assertEqual(again.outcome, "repeat")
            self.assertEqual(again.repeat_of, failed.import_run_id)
            self.assertEqual(again.payload_id, failed.payload_id)
            self.assertEqual(failed_records, ())
            self.assertEqual(len(failures), 1)


    def test_a_store_written_by_the_laxer_baseline_cannot_keep_invalid_records(self):
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        ).replace(b'"Afstemt"', b'"Wrong"')
        payload_id = sha256(content).hexdigest()
        # Observed in the baseline BronzeStore's own raw_payloads row for these
        # bytes, so the fixture below cannot drift from what it stored.
        self.assertEqual(
            payload_id,
            "9eb3ef8f9b179c9fa22d054c6d8549c9223869b6382addacdb28c8349f423c6e",
        )
        legacy_run_id = "4ade3d79f4984d59b522d8509a9bfbe5"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            database = root / "bronze.sqlite3"

            # A store the baseline wrote: it split a payload whose header did not
            # match the declared format and derived one record from it.
            connection = sqlite3.connect(database)
            connection.executescript(_LEGACY_BRONZE_SCHEMA)
            connection.execute(
                "INSERT INTO raw_payloads (payload_id, byte_length, content)"
                " VALUES (?, ?, ?)",
                (payload_id, len(content), content),
            )
            connection.execute(
                "INSERT INTO import_runs ("
                " import_run_id, payload_id, declared_account_id, source_format,"
                " original_filename, exported_on, exported_on_source,"
                " covers_through, covers_through_source, started_at, outcome, repeat_of"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    legacy_run_id,
                    payload_id,
                    "daily-account",
                    "danske-csv-v1",
                    source.name,
                    "2026-09-14",
                    "filename",
                    "2026-09-13",
                    "declared",
                    "2026-09-22T09:33:11.931353+00:00",
                    "stored",
                    None,
                ),
            )
            connection.execute(
                "INSERT INTO source_records (payload_id, record_ordinal, fields)"
                " VALUES (?, ?, ?)",
                (
                    payload_id,
                    1,
                    json.dumps(
                        {
                            "Dato": "12-09-2026",
                            "Kategori": " Mad ",
                            "Underkategori": " Dagligvarer ",
                            "Tekst": " Café",
                            "Beløb": "-45,00",
                            "Saldo": "955,00",
                            "Status": "Udført",
                            "Wrong": "Nej",
                        }
                    ),
                ),
            )
            connection.commit()
            connection.close()

            with BronzeStore(database) as reopened:
                run = reopened.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                failures = reopened.get_format_failures(run.payload_id)
                records = reopened.get_source_records(run.payload_id)
                payload = reopened.get_payload(run.payload_id)
                legacy_run = reopened.get_import_run(legacy_run_id)

            self.assertEqual(run.outcome, "repeat")
            self.assertEqual(run.repeat_of, legacy_run_id)
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0].source_format, "danske-csv-v1")
            self.assertEqual(failures[0].payload_id, payload_id)
            # A payload with a format failure exposes no source records, even
            # when a laxer parser had derived some for the same bytes.
            self.assertEqual(records, ())
            # The evidence itself is untouched: exact bytes and run history.
            self.assertEqual(payload.payload_id, payload_id)
            self.assertEqual(payload.content, content)
            self.assertEqual(payload.byte_length, len(content))
            self.assertEqual(legacy_run.import_run_id, legacy_run_id)
            self.assertEqual(legacy_run.payload_id, payload_id)
            self.assertEqual(legacy_run.outcome, "stored")
            self.assertEqual(legacy_run.original_filename, source.name)
            self.assertEqual(legacy_run.covers_through, date(2026, 9, 13))
            self.assertEqual(
                legacy_run.started_at.isoformat(), "2026-09-22T09:33:11.931353+00:00"
            )

            with BronzeStore(database) as reopened_again:
                self.assertEqual(reopened_again.get_source_records(payload_id), ())
                self.assertEqual(len(reopened_again.get_format_failures(payload_id)), 1)


    def test_every_field_must_be_quoted_exactly_as_the_format_declares(self):
        header = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
        )
        prefix = b'"12-09-2026"," Mad "," Dagligvarer ",'
        suffix = b'"-45,00","955,00","Udf\xf8rt","Nej"'
        malformed = {
            "unquoted field carrying a stray quote": prefix + b'Ca"fe,' + suffix,
            "unquoted field": prefix + b"Cafe," + suffix,
            "data after a closing quote": prefix + b'"Ca"fe",' + suffix,
            "unterminated quoted field": prefix + b'"Cafe',
            "one field too many": prefix + b'"Caf\xe9","ekstra",' + suffix,
            "one field too few": prefix + b'"Caf\xe9","955,00","Udf\xf8rt","Nej"',
        }
        # A field may hold an escaped quote and a line break of its own; the
        # format allows both inside a quoted field.
        well_formed = (
            header + b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""'
            b'\r\nand more ","-45,00","955,00","Udf\xf8rt","Nej"'
        )
        quoting_reasons = []

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            good_source = root / "synthetic-good-20260914.csv"
            good_source.write_bytes(well_formed)

            with BronzeStore(database) as store:
                stored = store.import_file(
                    good_source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                stored_records = store.get_source_records(stored.payload_id)
                stored_failures = store.get_format_failures(stored.payload_id)
                stored_payload = store.get_payload(stored.payload_id)

            self.assertEqual(stored.outcome, "stored")
            self.assertEqual(stored_failures, ())
            self.assertEqual(len(stored_records), 1)
            self.assertEqual(dict(stored_records[0].fields)["Tekst"], ' Café, "Øen"\r\nand more ')
            self.assertEqual(dict(stored_records[0].fields)["Dato"], "12-09-2026")
            self.assertEqual(stored_payload.content, well_formed)

            for index, (label, row) in enumerate(malformed.items()):
                with self.subTest(payload=label):
                    content = header + row
                    source = root / f"synthetic-{index}-20260914.csv"
                    source.write_bytes(content)
                    with BronzeStore(database) as store:
                        run = store.import_file(
                            source,
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_through=date(2026, 9, 13),
                        )
                    with BronzeStore(database) as reopened:
                        payload = reopened.get_payload(run.payload_id)
                        records = reopened.get_source_records(run.payload_id)
                        failures = reopened.get_format_failures(run.payload_id)

                    # A shape the format does not declare is a verdict on the
                    # payload, not a refusal, and it derives nothing.
                    self.assertEqual(run.outcome, "stored")
                    self.assertEqual(payload.content, content)
                    self.assertEqual(records, ())
                    self.assertEqual(len(failures), 1)
                    self.assertEqual(failures[0].source_format, "danske-csv-v1")
                    self.assertTrue(failures[0].reason)
                    self.assertNotIn(source.name, failures[0].reason)
                    self.assertNotIn("Cafe", failures[0].reason)
                    self.assertNotIn('Ca"fe', failures[0].reason)
                    self.assertNotIn("Caf\xe9", failures[0].reason)
                    if "unquoted field" in label or label.endswith("stray quote"):
                        quoting_reasons.append(failures[0].reason)

            # The same defect gives the same verdict whatever the row said.
            self.assertEqual(len(quoting_reasons), 2)
            self.assertEqual(quoting_reasons[0], quoting_reasons[1])


if __name__ == "__main__":
    unittest.main()
