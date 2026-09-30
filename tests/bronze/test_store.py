# Copyright 2026 Therkel
"""The Bronze store: exact bytes, provenance, and run outcomes.

Every test here opens `BronzeStore` on a migrated test profile, with synthetic
`danske-csv-v1` payloads as fixtures and one representative payload per
outcome. The rules of the format itself live in
`tests/bronze/parsers/test_danske_csv_v1.py`, the registry's selection in
`tests/bronze/parsers/test_registry.py`, and the store file's migrations and
guards in `tests/bronze/test_storage.py`.
"""

import unittest
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from budget.bronze import (
    BronzeStore,
    FormatFailure,
    ImportDeclaration,
    ImportRun,
    SourceRecord,
    migrate_bronze,
)
from budget.bronze.parsers.base import ParserResult
from budget.bronze.parsers.registry import UnsupportedSourceFormatError
from budget.bronze.store import ParserFormatMismatchError
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile


def migrated_profile(directory: str | Path) -> Profile:
    """Build the test profile for one temporary directory and migrate it."""
    profile = make_test_profile(directory)
    migrate_bronze(profile)
    return profile


class LineParser:
    """A real, tiny format: one source record per line, up to a limit."""

    source_format = "synthetic-lines-v1"

    def __init__(
        self,
        field: str | None,
        limit: int | None = None,
        failure: str = "this version reads no lines",
    ) -> None:
        """Hold the field each record carries, or fail every payload."""
        self._field = field
        self._limit = limit
        self._failure = failure

    def parse(self, content: bytes) -> ParserResult:
        """Present one record per line under this version's field name."""
        if self._field is None:
            return ParserResult.failed(self._failure)
        lines = [line for line in content.decode("ascii").splitlines() if line]
        if self._limit is not None:
            lines = lines[: self._limit]
        return ParserResult.matched(
            tuple({self._field: line} for line in lines),
            None,
            None,
        )

    def exported_on_from_filename(self, filename: str) -> date | None:
        """Read a -YYYYMMDD.csv suffix, as a real format does."""
        digits = filename.removesuffix(".csv").rpartition("-")[2]
        if len(digits) != 8 or not digits.isdigit():
            return None
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None


def danske_payload(*datos: str) -> bytes:
    """Build a `danske-csv-v1` payload with one record per given Dato string."""
    lines = [
        (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"'
        )
    ]
    lines.extend(
        b'"%s"," Mad "," Dagligvarer "," Caf\xe9",'
        b'"-45,00","955,00","Udf\xf8rt","Nej"' % dato.encode("ascii")
        for dato in datos
    )
    return b"\r\n".join(lines)


def import_into_new_store(
    content: bytes,
    *,
    covers_from: date,
    covers_through: date,
) -> tuple[ImportRun, tuple[SourceRecord, ...], tuple[FormatFailure, ...]]:
    """Import one payload exported on 2026-09-14 into its own new store.

    Every call gets a fresh store, so an accepted declaration never depends on
    an earlier call having stored the same bytes. What comes back is read from
    the reopened store.
    """
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "synthetic-20260914.csv"
        source.write_bytes(content)
        profile = migrated_profile(root)

        with BronzeStore(profile) as store:
            run = store.import_file(
                source,
                ImportDeclaration(
                    declared_account_id="daily-account",
                    source_format="danske-csv-v1",
                    covers_from=covers_from,
                    covers_through=covers_through,
                ),
            )
        with BronzeStore(profile) as reopened:
            saved = reopened.get_import_run(run.import_run_id)
            records = reopened.get_source_records(run.payload_id)
            failures = reopened.get_format_failures(run.payload_id)

    assert saved == run
    return saved, records, failures


class BronzeStoreTests(unittest.TestCase):
    def test_a_presentation_replaces_the_whole_derived_cache(self) -> None:
        content = b"12.09.2026\n05.09.2026\n"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-lines.csv"
            source.write_bytes(content)
            profile = migrated_profile(root)
            first = LineParser("datum")
            shorter = LineParser("only", limit=1)
            failing = LineParser(None)

            with BronzeStore(
                profile, parsers={LineParser.source_format: first}
            ) as store:
                run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert [
                    dict(r.fields) for r in store.get_source_records(run.payload_id)
                ] == [{"datum": "12.09.2026"}, {"datum": "05.09.2026"}]

            # A later version of the same format reads fewer fields, so the
            # cache must hold what the current parser presents, not the union.
            with BronzeStore(
                profile, parsers={LineParser.source_format: shorter}
            ) as store:
                store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                records = store.get_source_records(run.payload_id)
                assert [dict(record.fields) for record in records] == [
                    {"only": "12.09.2026"}
                ]
                assert store.get_format_failures(run.payload_id) == ()

            # A version that fails the payload deletes the records and records
            # its reason; the bytes and every earlier run stay.
            with BronzeStore(
                profile, parsers={LineParser.source_format: failing}
            ) as store:
                store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                failures = store.get_format_failures(run.payload_id)
                assert store.get_source_records(run.payload_id) == ()
                assert len(failures) == 1
                assert store.get_payload(run.payload_id).content == content
                assert store.get_import_run(run.import_run_id) == run

            # And a later version that reads again clears the failure.
            with BronzeStore(
                profile, parsers={LineParser.source_format: first}
            ) as store:
                store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert len(store.get_source_records(run.payload_id)) == 2
                assert store.get_format_failures(run.payload_id) == ()

    def test_a_parser_mapping_is_copied_and_validated(self) -> None:
        with TemporaryDirectory() as directory:
            profile = migrated_profile(directory)
            provided = {LineParser.source_format: LineParser("only")}
            store = BronzeStore(profile, parsers=provided)
            try:
                provided.clear()
                source = Path(directory) / "synthetic-lines.csv"
                source.write_bytes(b"12.09.2026\n")
                run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert len(store.get_source_records(run.payload_id)) == 1
            finally:
                store.close()

            empty = BronzeStore(profile, parsers={})
            try:
                with pytest.raises(UnsupportedSourceFormatError):
                    empty.import_file(
                        source,
                        ImportDeclaration(
                            declared_account_id="daily-account",
                            source_format=LineParser.source_format,
                            exported_on=date(2026, 9, 14),
                            covers_from=date(2026, 9, 1),
                            covers_through=date(2026, 9, 13),
                        ),
                    )
            finally:
                empty.close()

            with pytest.raises(ParserFormatMismatchError):
                BronzeStore(
                    profile,
                    parsers={"other-format": LineParser("only")},
                )

    def test_import_preserves_payload_provenance_and_fields_after_reopening(
        self,
    ) -> None:
        # Explicit Windows-1252 bytes, CRLF, and no final line break.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        # Independently calculated with coreutils sha256sum, not the Bronze code.
        expected_payload_id = (
            "f046dc4b35d7b22fa8f02fa0b091ec8110f83f2fb191b36f6c5289065196e4b0"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            profile = migrated_profile(root)

            before_import = datetime.now(UTC)
            with BronzeStore(profile) as store:
                run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
            after_import = datetime.now(UTC)

            # A retained import must not depend on the original file remaining.
            source.unlink()

            with BronzeStore(profile) as reopened:
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
            assert saved_run.covers_from == date(2026, 9, 1)
            assert saved_run.covers_through == date(2026, 9, 13)
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
                "Dato": "12.09.2026",
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
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_source = root / "synthetic-20260914.csv"
            later_source = root / "synthetic-20260916.csv"
            original_source.write_bytes(content)
            later_source.write_bytes(content)
            profile = migrated_profile(root)

            with BronzeStore(profile) as store:
                original_run = store.import_file(
                    original_source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                original_payload = store.get_payload(original_run.payload_id)
                original_records = store.get_source_records(original_run.payload_id)

            before_repeat = datetime.now(UTC)
            with BronzeStore(profile) as reopened:
                repeat = reopened.import_file(
                    later_source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 8, 15),
                        covers_through=date(2026, 9, 15),
                    ),
                )
            after_repeat = datetime.now(UTC)

            with BronzeStore(profile) as reopened:
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
                # A repeat records its own declared range, not the original's.
                assert saved_repeat.covers_from == date(2026, 8, 15)
                assert saved_repeat.covers_through == date(2026, 9, 15)
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

                # The same bounds apply to a repeat: a range that leaves out the
                # payload's transaction is refused, never recorded as a repeat.
                out_of_range = reopened.import_file(
                    later_source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 13),
                        covers_through=date(2026, 9, 15),
                    ),
                )
                assert out_of_range.outcome == "refused"
                assert out_of_range.repeat_of is None
                assert out_of_range.covers_from == date(2026, 9, 13)

    def test_same_bytes_for_another_account_record_a_refused_run(self) -> None:
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            profile = migrated_profile(root)

            with BronzeStore(profile) as store:
                original = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                original_records = store.get_source_records(original.payload_id)

            with BronzeStore(profile) as reopened:
                refused = reopened.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="savings-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )

            with BronzeStore(profile) as reopened:
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
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            # The only run for these bytes asks to cover evidence past the export
            # date, so it is refused and never becomes an original.
            with BronzeStore(profile) as store:
                refused = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 20),
                    ),
                )
            assert refused.outcome == "refused"

            # A refusal is nobody's owner, so another account can still declare
            # the same bytes correctly.
            with BronzeStore(profile) as reopened:
                accepted = reopened.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="savings-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
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
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        ).replace(b'"Afstemt"', b'"Afstemt?"')

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            with BronzeStore(profile) as store:
                run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
            with BronzeStore(profile) as reopened:
                payload = reopened.get_payload(run.payload_id)
                records = reopened.get_source_records(run.payload_id)
                failures = reopened.get_format_failures(run.payload_id)

            assert run.outcome == "stored"
            assert run.covers_from == date(2026, 9, 1)
            assert run.covers_through == date(2026, 9, 13)
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
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""  ",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        expected_payload_id = (
            "f046dc4b35d7b22fa8f02fa0b091ec8110f83f2fb191b36f6c5289065196e4b0"
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            no_suffix = root / "synthetic.csv"
            impossible_suffix = root / "synthetic-20260931.csv"
            no_suffix.write_bytes(content)
            impossible_suffix.write_bytes(content)

            with BronzeStore(profile) as store:
                with pytest.raises(
                    ValueError, match="Declare exported_on"
                ) as missing_export_date:
                    store.import_file(
                        no_suffix,
                        ImportDeclaration(
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_from=date(2026, 9, 1),
                            covers_through=date(2026, 9, 13),
                        ),
                    )
                assert "synthetic" not in str(missing_export_date.value)
                with pytest.raises(
                    ValueError, match="not a real date"
                ) as impossible_export_date:
                    store.import_file(
                        impossible_suffix,
                        ImportDeclaration(
                            declared_account_id="daily-account",
                            source_format="danske-csv-v1",
                            covers_from=date(2026, 9, 1),
                            covers_through=date(2026, 9, 13),
                        ),
                    )
                assert "synthetic" not in str(impossible_export_date.value)
                with pytest.raises(
                    ValueError, match="Unsupported source format"
                ) as unknown_format:
                    store.import_file(
                        no_suffix,
                        ImportDeclaration(
                            declared_account_id="daily-account",
                            source_format="nordea-csv-v1",
                            covers_from=date(2026, 9, 1),
                            covers_through=date(2026, 9, 13),
                        ),
                    )
                assert "synthetic" not in str(unknown_format.value)

            # These declarations were rejected, not refused: nothing was
            # stored, not even a refused run.
            with BronzeStore(profile) as reopened, pytest.raises(KeyError):
                reopened.get_payload(expected_payload_id)

            # A declared export date is the run's date, whatever the filename
            # cannot say: the impossible suffix is never read as a date.
            with BronzeStore(profile) as store:
                declared = store.import_file(
                    impossible_suffix,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
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
            b'"31.02.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            with BronzeStore(profile) as store:
                run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
            with BronzeStore(profile) as reopened:
                payload = reopened.get_payload(run.payload_id)
                records = reopened.get_source_records(run.payload_id)
                failures = reopened.get_format_failures(run.payload_id)

            # The declaration was acceptable, so the run is stored with a
            # verdict rather than refused.
            assert run.outcome == "stored"
            assert run.covers_from == date(2026, 9, 1)
            assert run.covers_through == date(2026, 9, 13)
            assert payload.content == content
            assert records == ()
            assert len(failures) == 1
            assert failures[0].reason
            assert "31.02.2026" not in failures[0].reason
            assert source.name not in failures[0].reason

    def test_the_covered_range_is_a_required_declaration(self) -> None:
        content = danske_payload("12.09.2026")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)
            profile = migrated_profile(root)
            complete: dict[str, Any] = {
                "declared_account_id": "daily-account",
                "source_format": "danske-csv-v1",
                "covers_from": date(2026, 9, 1),
                "covers_through": date(2026, 9, 13),
            }

            with BronzeStore(profile) as store:
                for missing in ("covers_from", "covers_through"):
                    with self.subTest(missing=missing):
                        arguments = {
                            name: value
                            for name, value in complete.items()
                            if name != missing
                        }
                        # Unpacked, so the declaration can leave out a required
                        # field the way an untyped caller could.
                        with pytest.raises(TypeError, match=missing):
                            store.import_file(source, ImportDeclaration(**arguments))

            # A usage error is not a refusal: not even the bytes were kept.
            with BronzeStore(profile) as reopened, pytest.raises(KeyError):
                reopened.get_payload(sha256(content).hexdigest())

    def test_a_declared_range_is_bounded_and_never_clamped(self) -> None:
        # The row carrying the maximum Dato comes first and is cancelled, and
        # the minimum sits between two later dates, so a bound read from row
        # order or Status would land somewhere else. The export date is
        # 2026-09-14, from the filename.
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Slettet","Nej"\r\n'
            b'"05.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","1000,00","Udf\xf8rt","Nej"\r\n'
            b'"08.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        cases = (
            (
                "ends after the export date",
                date(2026, 9, 1),
                date(2026, 9, 15),
                "refused",
            ),
            (
                "starts after the earliest transaction",
                date(2026, 9, 6),
                date(2026, 9, 13),
                "refused",
            ),
            (
                "ends before the latest transaction",
                date(2026, 9, 1),
                date(2026, 9, 11),
                "refused",
            ),
            (
                "starts on the earliest transaction",
                date(2026, 9, 5),
                date(2026, 9, 13),
                "stored",
            ),
            (
                "ends on the latest transaction",
                date(2026, 9, 1),
                date(2026, 9, 12),
                "stored",
            ),
            (
                "ends on the export date",
                date(2026, 9, 1),
                date(2026, 9, 14),
                "stored",
            ),
        )

        for label, covers_from, covers_through, expected_outcome in cases:
            with self.subTest(range=label):
                run, records, failures = import_into_new_store(
                    content, covers_from=covers_from, covers_through=covers_through
                )

                assert run.outcome == expected_outcome
                assert run.repeat_of is None
                # A refused run keeps the declared range, not the nearest
                # acceptable one.
                assert run.covers_from == covers_from
                assert run.covers_through == covers_through
                assert failures == ()
                assert [record.record_ordinal for record in records] == [1, 2, 3]
                assert dict(records[0].fields)["Dato"] == "12.09.2026"
                assert dict(records[0].fields)["Status"] == "Slettet"

    def test_a_quiet_account_declares_a_range_without_transactions(self) -> None:
        # A readable payload that states no transactions shows the account was
        # quiet over the declared range; only the range itself can be wrong.
        content = danske_payload()
        cases = (
            ("a valid range", date(2026, 9, 1), date(2026, 9, 13), "stored"),
            (
                "starts after it ends",
                date(2026, 9, 13),
                date(2026, 9, 1),
                "refused",
            ),
            (
                "ends after the export date",
                date(2026, 9, 1),
                date(2026, 9, 15),
                "refused",
            ),
        )

        for label, covers_from, covers_through, expected_outcome in cases:
            with self.subTest(range=label):
                run, records, failures = import_into_new_store(
                    content, covers_from=covers_from, covers_through=covers_through
                )

                assert run.outcome == expected_outcome
                assert run.covers_from == covers_from
                assert run.covers_through == covers_through
                assert records == ()
                assert failures == ()

    def test_an_unreadable_payload_keeps_its_declared_range(self) -> None:
        # The payload has no dates Bronze can read, so only the range's own
        # bounds apply: it must not start after it ends or reach past the
        # export date.
        content = danske_payload("12.09.2026").replace(b'"Afstemt"', b'"Afstemt?"')
        cases = (
            ("a valid range", date(2026, 9, 1), date(2026, 9, 13), "stored"),
            (
                "starts after it ends",
                date(2026, 9, 13),
                date(2026, 9, 1),
                "refused",
            ),
            (
                "ends after the export date",
                date(2026, 9, 1),
                date(2026, 9, 15),
                "refused",
            ),
        )

        for label, covers_from, covers_through, expected_outcome in cases:
            with self.subTest(range=label):
                run, records, failures = import_into_new_store(
                    content, covers_from=covers_from, covers_through=covers_through
                )

                assert run.outcome == expected_outcome
                assert run.covers_from == covers_from
                assert run.covers_through == covers_through
                assert records == ()
                assert len(failures) == 1
                assert failures[0].source_format == "danske-csv-v1"

    def test_a_refused_or_failed_presentation_is_evidence_never_an_original(
        self,
    ) -> None:
        content = (
            b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b",'
            b'"Saldo","Status","Afstemt"\r\n'
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = content[:-1] + b"\x81"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            source = root / "synthetic-20260914.csv"
            source.write_bytes(content)

            with BronzeStore(profile) as store:
                refused = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 20),
                    ),
                )
            assert refused.outcome == "refused"

            with BronzeStore(profile) as reopened:
                # A refusal still retains the payload and its parsed records.
                assert reopened.get_payload(refused.payload_id).content == content
                refused_records = reopened.get_source_records(refused.payload_id)
                assert len(refused_records) == 1
                assert dict(refused_records[0].fields)["Dato"] == "12.09.2026"

            # The same bytes declared correctly afterwards are a new import, not
            # a repeat of the refusal, and the refusal is left as it was.
            with BronzeStore(profile) as reopened:
                corrected = reopened.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
            assert corrected.outcome == "stored"
            assert corrected.repeat_of is None
            assert corrected.import_run_id != refused.import_run_id
            assert corrected.payload_id == refused.payload_id

            with BronzeStore(profile) as reopened:
                assert reopened.get_import_run(refused.import_run_id) == refused
                # A refusal never seeds ownership: the same bytes stay refused
                # for another account, and still repeat the stored run only.
                foreign = reopened.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="savings-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert foreign.outcome == "refused"
                assert foreign.repeat_of is None
                repeated = reopened.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert repeated.outcome == "repeat"
                assert repeated.repeat_of == corrected.import_run_id

            # A payload that failed its format is stored once, so presenting it
            # again records its own repeat run and keeps the one failure.
            malformed_source = root / "synthetic-20260915.csv"
            malformed_source.write_bytes(malformed)
            with BronzeStore(profile) as reopened:
                failed = reopened.import_file(
                    malformed_source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 14),
                    ),
                )
                again = reopened.import_file(
                    malformed_source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format="danske-csv-v1",
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 14),
                    ),
                )
                failures = reopened.get_format_failures(failed.payload_id)
                failed_records = reopened.get_source_records(failed.payload_id)

            assert failed.outcome == "stored"
            assert again.outcome == "repeat"
            assert again.repeat_of == failed.import_run_id
            assert again.payload_id == failed.payload_id
            assert failed_records == ()
            assert len(failures) == 1

    def test_a_later_failure_refreshes_the_reason_and_keeps_every_run(self) -> None:
        content = b"12.09.2026\n05.09.2026\n"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic-lines.csv"
            source.write_bytes(content)
            profile = migrated_profile(root)
            reader = LineParser("datum")
            first_failure = LineParser(None, failure="the first version refuses this")
            second_failure = LineParser(None, failure="the second version refuses this")

            with BronzeStore(
                profile, parsers={LineParser.source_format: reader}
            ) as store:
                stored_run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )

            with BronzeStore(
                profile, parsers={LineParser.source_format: first_failure}
            ) as store:
                failed_run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                reasons = [
                    failure.reason
                    for failure in store.get_format_failures(stored_run.payload_id)
                ]
                assert reasons == ["the first version refuses this"]

            with BronzeStore(
                profile, parsers={LineParser.source_format: second_failure}
            ) as store:
                store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                refreshed = [
                    failure.reason
                    for failure in store.get_format_failures(stored_run.payload_id)
                ]
                assert refreshed == ["the second version refuses this"]
                assert store.get_source_records(stored_run.payload_id) == ()
                assert store.get_import_run(stored_run.import_run_id) == stored_run
                assert store.get_import_run(failed_run.import_run_id) == failed_run

            with BronzeStore(
                profile, parsers={LineParser.source_format: reader}
            ) as store:
                final_run = store.import_file(
                    source,
                    ImportDeclaration(
                        declared_account_id="daily-account",
                        source_format=LineParser.source_format,
                        exported_on=date(2026, 9, 14),
                        covers_from=date(2026, 9, 1),
                        covers_through=date(2026, 9, 13),
                    ),
                )
                assert store.get_format_failures(stored_run.payload_id) == ()
                for earlier in (stored_run, failed_run, final_run):
                    assert store.get_import_run(earlier.import_run_id) == earlier


if __name__ == "__main__":
    unittest.main()
