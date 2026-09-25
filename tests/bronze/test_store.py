# Copyright 2026 Therkel
"""The Bronze store: exact bytes, provenance, and run outcomes.

Every test here goes through `BronzeStore`, with synthetic `danske-csv-v1`
payloads as fixtures and one representative payload per outcome. The rules of
the format itself live in `tests/bronze/parsers/test_danske_csv_v1.py` and the
registry's selection in `tests/bronze/parsers/test_registry.py`, so the store
does not repeat those matrices.
"""

import json
import sqlite3
import unittest
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore

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
    def test_import_preserves_payload_provenance_and_fields_after_reopening(
        self,
    ) -> None:
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

            assert isinstance(run.import_run_id, str)
            assert run.import_run_id
            assert saved_run == run
            assert saved_run.payload_id == expected_payload_id
            assert saved_run.declared_account_id == "daily-account"
            assert saved_run.source_format == "danske-csv-v1"
            assert saved_run.original_filename == "synthetic-20260914.csv"
            assert saved_run.exported_on == date(2026, 9, 14)
            assert saved_run.exported_on_source == "filename"
            assert saved_run.covers_through == date(2026, 9, 13)
            assert saved_run.covers_through_source == "declared"
            assert saved_run.started_at.utcoffset() == timedelta(0)
            assert before_import <= saved_run.started_at
            assert saved_run.started_at <= after_import
            assert saved_run.outcome == "stored"
            assert saved_run.repeat_of is None

            assert payload.payload_id == expected_payload_id
            assert payload.byte_length == 166
            assert payload.content == content
            assert failures == ()
            assert len(records) == 1
            assert records[0].payload_id == expected_payload_id
            assert records[0].record_ordinal == 1
            assert dict(records[0].fields) == {
                "Dato": "12-09-2026",
                "Kategori": " Mad ",
                "Underkategori": " Dagligvarer ",
                "Tekst": ' Café, "Øen"  ',
                "Beløb": "-45,00",
                "Saldo": "955,00",
                "Status": "Udført",
                "Afstemt": "Nej",
            }

    def test_same_bytes_record_repeat_with_own_dates_and_unchanged_payload(
        self,
    ) -> None:
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
                assert saved_repeat == repeat
                assert saved_repeat.import_run_id != original_run.import_run_id
                assert saved_repeat.outcome == "repeat"
                assert saved_repeat.repeat_of == original_run.import_run_id
                assert saved_repeat.payload_id == original_run.payload_id
                assert saved_repeat.declared_account_id == "daily-account"
                assert saved_repeat.source_format == "danske-csv-v1"
                assert saved_repeat.original_filename == "synthetic-20260916.csv"
                assert saved_repeat.exported_on == date(2026, 9, 16)
                assert saved_repeat.exported_on_source == "filename"
                assert saved_repeat.covers_through == date(2026, 9, 15)
                assert saved_repeat.covers_through_source == "declared"
                assert before_repeat <= saved_repeat.started_at
                assert saved_repeat.started_at <= after_repeat
                assert (
                    reopened.get_import_run(original_run.import_run_id) == original_run
                )
                assert reopened.get_payload(saved_repeat.payload_id) == original_payload
                assert (
                    reopened.get_source_records(saved_repeat.payload_id)
                    == original_records
                )
                assert reopened.get_format_failures(saved_repeat.payload_id) == ()

    def test_same_bytes_for_another_account_record_a_refused_run(self) -> None:
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
                assert saved == refused
                assert saved.import_run_id != original.import_run_id
                assert saved.outcome == "refused"
                assert saved.declared_account_id == "savings-account"
                assert saved.payload_id == original.payload_id
                assert saved.repeat_of is None
                assert reopened.get_import_run(original.import_run_id) == original
                assert reopened.get_payload(original.payload_id).content == content
                assert (
                    reopened.get_source_records(original.payload_id) == original_records
                )

    def test_bytes_only_ever_refused_for_one_account_are_free_for_another(
        self,
    ) -> None:
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            # The only run for these bytes asks to cover evidence past the export
            # date, so it is refused and never becomes an original.
            with BronzeStore(database) as store:
                refused = store.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 20),
                )
            assert refused.outcome == "refused"

            # A refusal is nobody's owner, so another account can still declare
            # the same bytes correctly.
            with BronzeStore(database) as reopened:
                accepted = reopened.import_file(
                    source,
                    declared_account_id="savings-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                payload = reopened.get_payload(accepted.payload_id)
                saved_refusal = reopened.get_import_run(refused.import_run_id)

            assert accepted.outcome == "stored"
            assert accepted.repeat_of is None
            assert accepted.payload_id == refused.payload_id
            assert payload.content == content
            assert saved_refusal == refused

    def test_a_malformed_payload_is_recorded_as_a_verdict_with_its_bytes(
        self,
    ) -> None:
        # The exhaustive header, encoding, quoting and date matrices live with
        # the parser in test_danske_csv_v1.py. The store's own job is to keep
        # the bytes and record one verdict, which one payload shows.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        ).replace(b'"Afstemt"', b'"Afstemt?"')

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            source = root / "synthetic-20260914.csv"
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

            assert run.outcome == "stored"
            assert run.covers_through == date(2026, 9, 13)
            assert run.covers_through_source == "declared"
            assert payload.content == content
            assert payload.byte_length == len(content)
            assert records == ()
            assert len(failures) == 1
            assert failures[0].payload_id == run.payload_id
            assert failures[0].source_format == "danske-csv-v1"
            assert failures[0].reason
            # A failure reason is a verdict, never a copy of the source.
            assert source.name not in failures[0].reason
            assert "Dato" not in failures[0].reason
            assert "Afstemt" not in failures[0].reason

    def test_import_metadata_failures_happen_before_persistence(self) -> None:
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
                with pytest.raises(
                    ValueError, match="Declare exported_on"
                ) as missing_export_date:
                    store.import_file(
                        no_suffix,
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                assert "synthetic" not in str(missing_export_date.value)
                with pytest.raises(
                    ValueError, match="not a real date"
                ) as impossible_export_date:
                    store.import_file(
                        impossible_suffix,
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                assert "synthetic" not in str(impossible_export_date.value)
                with pytest.raises(
                    ValueError, match="Unsupported source format"
                ) as unknown_format:
                    store.import_file(
                        no_suffix,
                        declared_account_id="daily-account",
                        source_format="nordea-csv-v1",
                        covers_through=date(2026, 9, 13),
                    )
                assert "synthetic" not in str(unknown_format.value)

            # A refused declaration is not an import: no payload was stored.
            with BronzeStore(database) as reopened, pytest.raises(KeyError):
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
            assert declared.exported_on == date(2026, 9, 14)
            assert declared.exported_on_source == "declared"

    def test_a_date_the_parser_cannot_read_is_a_verdict_not_a_refusal(self) -> None:
        # An unreadable Dato cannot bound a coverage declaration, so the payload
        # is retained with a verdict, never guessed. The date-shape matrix lives
        # with the parser in test_danske_csv_v1.py.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"31-02-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"
            source = root / "synthetic-20260914.csv"
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

            # The declaration was acceptable, so the run is stored with a
            # verdict rather than refused.
            assert run.outcome == "stored"
            assert run.covers_through == date(2026, 9, 13)
            assert run.covers_through_source == "declared"
            assert payload.content == content
            assert records == ()
            assert len(failures) == 1
            assert failures[0].reason
            assert "31-02-2026" not in failures[0].reason
            assert source.name not in failures[0].reason

    def test_a_declared_covers_through_is_bounded_and_never_clamped(self) -> None:
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

                    assert run.outcome == expected_outcome
                    # A refused declaration is recorded as declared, not moved
                    # to the nearest acceptable date.
                    assert run.covers_through == declared
                    assert run.covers_through_source == "declared"
                    assert payload.content == content
                    assert [record.record_ordinal for record in records] == [1, 2]
                    assert dict(records[0].fields)["Dato"] == "12-09-2026"
                    assert dict(records[0].fields)["Status"] == "Slettet"

                    if expected_outcome == "stored":
                        stored_run_id = run.import_run_id
                        assert run.repeat_of is None
                    elif expected_outcome == "repeat":
                        assert run.repeat_of == stored_run_id
                    else:
                        assert run.repeat_of is None

    def test_a_missing_declaration_falls_back_only_where_it_cannot_claim_too_much(
        self,
    ) -> None:
        def payload(dates: tuple[str, ...]) -> bytes:
            lines = [
                (
                    b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
                    b'"Saldo","Status","Afstemt"'
                )
            ]
            lines.extend(
                b'"%s"," Mad "," Dagligvarer "," Caf\xe9",'
                b'"-45,00","955,00","Udf\xf8rt","Nej"' % dato.encode("ascii")
                for dato in dates
            )
            return b"\r\n".join(lines)

        cases = (
            (
                "quiet tail in the last transaction's month",
                ("12-09-2026",),
                date(2026, 9, 14),
                "stored",
            ),
            (
                "fallback lands in a later month",
                ("31-08-2026",),
                date(2026, 9, 14),
                "refused",
            ),
            ("payload states no transactions", (), date(2026, 9, 14), "refused"),
            (
                "fallback before the last transaction",
                ("20-09-2026",),
                date(2026, 9, 14),
                "refused",
            ),
            (
                "fallback lands on the day before a later export date",
                ("30-09-2026",),
                date(2026, 10, 1),
                "stored",
            ),
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "bronze.sqlite3"

            for index, (label, dates, exported_on, expected_outcome) in enumerate(
                cases
            ):
                with self.subTest(declaration=label):
                    content = payload(dates)
                    source = root / f"synthetic-{index}-{exported_on:%Y%m%d}.csv"
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

                    assert run.outcome == expected_outcome
                    assert run.repeat_of is None
                    assert run.exported_on == exported_on
                    assert run.exported_on_source == "filename"
                    # The attempted fallback is recorded, not a date invented
                    # from the payload: covers_through is the export date.
                    assert run.covers_through == exported_on
                    assert run.covers_through_source == "exported_on"
                    assert stored_payload.content == content
                    assert [record.record_ordinal for record in records] == list(
                        range(1, len(dates) + 1)
                    )
                    assert failures == ()

    def test_a_refused_or_failed_presentation_is_evidence_never_an_original(
        self,
    ) -> None:
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
            assert refused.outcome == "refused"

            with BronzeStore(database) as reopened:
                # A refusal still retains the payload and its parsed records.
                assert reopened.get_payload(refused.payload_id).content == content
                refused_records = reopened.get_source_records(refused.payload_id)
                assert len(refused_records) == 1
                assert dict(refused_records[0].fields)["Dato"] == "12-09-2026"

            # The same bytes declared correctly afterwards are a new import, not
            # a repeat of the refusal, and the refusal is left as it was.
            with BronzeStore(database) as reopened:
                corrected = reopened.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
            assert corrected.outcome == "stored"
            assert corrected.repeat_of is None
            assert corrected.import_run_id != refused.import_run_id
            assert corrected.payload_id == refused.payload_id

            with BronzeStore(database) as reopened:
                assert reopened.get_import_run(refused.import_run_id) == refused
                # A refusal never seeds ownership: the same bytes stay refused
                # for another account, and still repeat the stored run only.
                foreign = reopened.import_file(
                    source,
                    declared_account_id="savings-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                assert foreign.outcome == "refused"
                assert foreign.repeat_of is None
                repeated = reopened.import_file(
                    source,
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_through=date(2026, 9, 13),
                )
                assert repeated.outcome == "repeat"
                assert repeated.repeat_of == corrected.import_run_id

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

            assert failed.outcome == "stored"
            assert again.outcome == "repeat"
            assert again.repeat_of == failed.import_run_id
            assert again.payload_id == failed.payload_id
            assert failed_records == ()
            assert len(failures) == 1

    def test_a_store_written_by_the_laxer_baseline_cannot_keep_invalid_records(
        self,
    ) -> None:
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        ).replace(b'"Afstemt"', b'"Wrong"')
        payload_id = sha256(content).hexdigest()
        # Observed in the baseline BronzeStore's own raw_payloads row for these
        # bytes, so the fixture below cannot drift from what it stored.
        assert (
            payload_id
            == "9eb3ef8f9b179c9fa22d054c6d8549c9223869b6382addacdb28c8349f423c6e"
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

            assert run.outcome == "repeat"
            assert run.repeat_of == legacy_run_id
            assert len(failures) == 1
            assert failures[0].source_format == "danske-csv-v1"
            assert failures[0].payload_id == payload_id
            # A payload with a format failure exposes no source records, even
            # when a laxer parser had derived some for the same bytes.
            assert records == ()
            # The evidence itself is untouched: exact bytes and run history.
            assert payload.payload_id == payload_id
            assert payload.content == content
            assert payload.byte_length == len(content)
            assert legacy_run.import_run_id == legacy_run_id
            assert legacy_run.payload_id == payload_id
            assert legacy_run.outcome == "stored"
            assert legacy_run.original_filename == source.name
            assert legacy_run.covers_through == date(2026, 9, 13)
            assert (
                legacy_run.started_at.isoformat() == "2026-09-22T09:33:11.931353+00:00"
            )

            with BronzeStore(database) as reopened_again:
                assert reopened_again.get_source_records(payload_id) == ()
                assert len(reopened_again.get_format_failures(payload_id)) == 1


if __name__ == "__main__":
    unittest.main()
