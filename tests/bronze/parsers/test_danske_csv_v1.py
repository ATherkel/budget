# Copyright 2026 Therkel
"""The declared rules of `danske-csv-v1`, through its public parser seam.

Every test here uses `parse` and `exported_on_from_filename` only, so a rule
change is observed where a caller sees it. What the store does with these
payloads - retaining bytes, recording verdicts, refusing runs - lives in
`tests/bronze/test_store.py`, which keeps one representative payload per outcome
instead of repeating these matrices.
"""

import unittest
from datetime import date

import pytest

from budget.bronze.parsers.danske_csv_v1 import PARSER

HEADER = (
    b'"Dato","Kategori","Underkategori","Tekst","Bel\xf8b","Saldo","Status","Afstemt"'
)
ONE_RECORD_ROW = (
    b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
    b'"-45,00","955,00","Udf\xf8rt","Nej"'
)
ONE_RECORD_PAYLOAD = HEADER + b"\r\n" + ONE_RECORD_ROW


def header_payload(*rows: bytes) -> bytes:
    """Build a payload from the declared header and the given data rows."""
    return b"\r\n".join([HEADER, *rows])


def dato_row(dato: str) -> bytes:
    """Build one data row whose Dato field carries the given source string."""
    return (
        b'"%s"," Mad "," Dagligvarer "," Caf\xe9",'
        b'"-45,00","955,00","Udf\xf8rt","Nej"' % dato.encode("cp1252")
    )


class DanskeCsvV1ParserTests(unittest.TestCase):
    def test_a_payload_is_presented_with_its_decoded_fields_unchanged(self) -> None:
        result = PARSER.parse(ONE_RECORD_PAYLOAD)

        assert result.failure_reason is None
        assert [dict(record) for record in result.records] == [
            {
                "Dato": "12-09-2026",
                "Kategori": " Mad ",
                "Underkategori": " Dagligvarer ",
                "Tekst": " Café",
                "Beløb": "-45,00",
                "Saldo": "955,00",
                "Status": "Udført",
                "Afstemt": "Nej",
            }
        ]
        assert result.last_transaction_date == date(2026, 9, 12)

    def test_a_verdict_offers_no_records_and_no_coverage_bound(self) -> None:
        # A byte Windows-1252 leaves undefined: the payload is not decodable as
        # the declared encoding, so the verdict is the whole answer.
        result = PARSER.parse(ONE_RECORD_PAYLOAD[:-1] + b"\x81")

        assert result.records == ()
        assert result.last_transaction_date is None
        reason = result.failure_reason
        assert reason
        assert "Dato" not in reason

    def test_the_declared_header_and_encoding_are_required(self) -> None:
        malformed = {
            "unexpected header": ONE_RECORD_PAYLOAD.replace(
                b'"Afstemt"', b'"Afstemt?"'
            ),
            "utf-8 encoded header": ONE_RECORD_PAYLOAD.decode("cp1252").encode("utf-8"),
            "byte undefined in windows-1252": ONE_RECORD_PAYLOAD[:-1] + b"\x81",
        }
        header_reasons = []

        for label, content in malformed.items():
            with self.subTest(payload=label):
                result = PARSER.parse(content)

                assert result.records == ()
                assert result.last_transaction_date is None
                reason = result.failure_reason
                assert reason
                # A failure reason is a verdict, never a copy of the source.
                assert "Dato" not in reason
                assert "Afstemt" not in reason
                if "header" in label:
                    header_reasons.append(reason)

        # The same defect gives the same verdict whatever the payload said.
        assert len(header_reasons) == 2
        assert header_reasons[0] == header_reasons[1]

    def test_every_field_must_be_quoted_exactly_as_the_format_declares(self) -> None:
        header = HEADER + b"\r\n"
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

        stored = PARSER.parse(well_formed)
        assert stored.failure_reason is None
        assert len(stored.records) == 1
        assert dict(stored.records[0])["Tekst"] == ' Café, "Øen"\r\nand more '
        assert dict(stored.records[0])["Dato"] == "12-09-2026"
        assert stored.last_transaction_date == date(2026, 9, 12)

        for label, row in malformed.items():
            with self.subTest(payload=label):
                result = PARSER.parse(header + row)

                # A shape the format does not declare is a verdict on the
                # payload, not a refusal, and it derives nothing.
                assert result.records == ()
                assert result.last_transaction_date is None
                reason = result.failure_reason
                assert reason
                assert "Cafe" not in reason
                assert 'Ca"fe' not in reason
                assert "Caf\xe9" not in reason
                if "unquoted field" in label or label.endswith("stray quote"):
                    quoting_reasons.append(reason)

        # The same defect gives the same verdict whatever the row said.
        assert len(quoting_reasons) == 2
        assert quoting_reasons[0] == quoting_reasons[1]

    def test_a_row_ending_in_a_comma_still_needs_its_quoted_field(self) -> None:
        header = HEADER + b"\r\n"
        seven_fields = (
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt",'
        )

        # An empty final field is legal when it is quoted, and a trailing line
        # break after it stays legal too.
        quoted_empty = PARSER.parse(header + seven_fields + b'""\r\n')

        assert quoted_empty.failure_reason is None
        assert len(quoted_empty.records) == 1
        assert dict(quoted_empty.records[0])["Afstemt"] == ""

        # A trailing comma with nothing after it is an unquoted eighth field,
        # however many fields csv.reader then counts.
        trailing_comma = PARSER.parse(header + seven_fields)

        assert trailing_comma.records == ()
        assert trailing_comma.last_transaction_date is None
        reason = trailing_comma.failure_reason
        assert reason
        assert "Udf\xf8rt" not in reason

    def test_the_coverage_bound_is_the_latest_date_whatever_the_row_order(self) -> None:
        # The row carrying the maximum Dato comes first and is cancelled, so a
        # bound read from row order or Status would land somewhere else.
        payload = header_payload(
            b'"12-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Slettet","Nej"',
            b'"05-09-2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","1000,00","Udf\xf8rt","Nej"',
        )

        result = PARSER.parse(payload)

        assert result.failure_reason is None
        assert result.last_transaction_date == date(2026, 9, 12)
        assert [dict(record)["Dato"] for record in result.records] == [
            "12-09-2026",
            "05-09-2026",
        ]
        assert [dict(record)["Status"] for record in result.records] == [
            "Slettet",
            "Udført",
        ]

    def test_a_date_must_be_zero_padded_dd_mm_yyyy(self) -> None:
        # The declared shape is two day digits, two month digits and four year
        # digits. A one-digit day or month, a leading space, Unicode digits, the
        # ISO order and trailing text are each outside it.
        rejected = (
            "1-9-2026",
            "01-9-2026",
            " 1-09-2026",
            "3-10-2026",
            "2026-09-12",
            "12-09-2026 ",
            "¹²-09-2026",
        )
        failure_reasons = []

        for dato in rejected:
            with self.subTest(dato=dato):
                result = PARSER.parse(header_payload(dato_row(dato)))

                assert result.records == ()
                assert result.last_transaction_date is None
                reason = result.failure_reason
                assert reason
                assert dato not in reason
                failure_reasons.append(reason)

        # Every shape defect is one verdict, whatever the text looked like.
        assert len(set(failure_reasons)) == 1

        accepted = PARSER.parse(header_payload(dato_row("12-09-2026")))
        assert accepted.failure_reason is None
        assert [dict(record)["Dato"] for record in accepted.records] == ["12-09-2026"]
        assert accepted.last_transaction_date == date(2026, 9, 12)

    def test_an_unreadable_transaction_date_is_a_verdict_without_records(self) -> None:
        row = (
            b'%s," Mad "," Dagligvarer "," Caf\xe9","-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = {
            "impossible date": b'"31-02-2026"',
            "unexpected date shape": b'"2026-09-12"',
        }
        failure_reasons = []

        for label, dato in malformed.items():
            with self.subTest(dato=label):
                result = PARSER.parse(header_payload(row % dato))

                assert result.records == ()
                assert result.last_transaction_date is None
                reason = result.failure_reason
                assert reason
                assert dato.decode("cp1252") not in reason
                failure_reasons.append(reason)

        assert len(failure_reasons) == 2
        assert failure_reasons[0] == failure_reasons[1]

    def test_the_parser_owns_its_export_date_filename_convention(self) -> None:
        assert PARSER.exported_on_from_filename("synthetic-20260914.csv") == date(
            2026, 9, 14
        )
        # A name this format does not recognise is not a failure: the operator
        # can still declare the export date for it.
        assert PARSER.exported_on_from_filename("synthetic.csv") is None
        assert PARSER.exported_on_from_filename("synthetic-20260914.txt") is None

    def test_an_unreadable_date_suffix_is_refused_without_naming_the_file(self) -> None:
        with pytest.raises(ValueError, match="not a real date") as refusal:
            PARSER.exported_on_from_filename("synthetic-20260931.csv")

        assert "synthetic" not in str(refusal.value)
        assert "20260931" not in str(refusal.value)


if __name__ == "__main__":
    unittest.main()
