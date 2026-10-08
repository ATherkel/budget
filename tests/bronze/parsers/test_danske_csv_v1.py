# Copyright 2026 Therkel
"""The declared rules of `danske-csv-v1`, through its public parser seam.

Every test here uses `parse`, `exported_on_from_filename`,
`account_number_from_filename` and `is_account_number` only, so a rule change is
observed where a caller sees it. What the store does with these payloads -
retaining bytes, recording verdicts, refusing runs - lives in
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
    b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
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
                "Dato": "12.09.2026",
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

    def test_the_declared_header_and_encoding_are_required(self) -> None:
        header_mismatches = {
            "wrong first field name": ONE_RECORD_PAYLOAD.replace(b'"Dato"', b'"Datum"'),
            "wrong last field name": ONE_RECORD_PAYLOAD.replace(
                b'"Afstemt"', b'"Afstemt?"'
            ),
        }
        # Payloads that are not the declared encoding at all. They must be
        # rejected, but no rule says which check rejects them first, so their
        # verdict is not compared with the header verdicts.
        unreadable = {
            "utf-8 encoded header": ONE_RECORD_PAYLOAD.decode("cp1252").encode("utf-8"),
            "byte undefined in windows-1252": ONE_RECORD_PAYLOAD[:-1] + b"\x81",
        }

        def verdict_for(content: bytes) -> str:
            result = PARSER.parse(content)
            assert result.records == ()
            assert result.last_transaction_date is None
            reason = result.failure_reason
            assert reason
            # A failure reason is a verdict, never a copy of the source.
            assert "Dato" not in reason
            assert "Afstemt" not in reason
            return reason

        header_verdicts = []
        for label, content in header_mismatches.items():
            with self.subTest(payload=label):
                header_verdicts.append(verdict_for(content))

        # A wrong field name is the same defect whichever name is wrong.
        assert len(set(header_verdicts)) == 1

        for label, content in unreadable.items():
            with self.subTest(payload=label):
                verdict_for(content)

    def test_every_field_must_be_quoted_exactly_as_the_format_declares(self) -> None:
        header = HEADER + b"\r\n"
        prefix = b'"12.09.2026"," Mad "," Dagligvarer ",'
        suffix = b'"-45,00","955,00","Udf\xf8rt","Nej"'
        unquoted_fields = {
            "unquoted field carrying a stray quote": prefix + b'Ca"fe,' + suffix,
            "unquoted field": prefix + b"Cafe," + suffix,
        }
        other_shapes = {
            "data after a closing quote": prefix + b'"Ca"fe",' + suffix,
            "unterminated quoted field": prefix + b'"Cafe',
            "one field too many": prefix + b'"Caf\xe9","ekstra",' + suffix,
            "one field too few": prefix + b'"Caf\xe9","955,00","Udf\xf8rt","Nej"',
        }
        # A field may hold an escaped quote and a line break of its own; the
        # format allows both inside a quoted field.
        well_formed = (
            header + b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9, ""\xd8en""'
            b'\r\nand more ","-45,00","955,00","Udf\xf8rt","Nej"'
        )
        stored = PARSER.parse(well_formed)
        assert stored.failure_reason is None
        assert len(stored.records) == 1
        assert dict(stored.records[0])["Tekst"] == ' Café, "Øen"\r\nand more '
        assert dict(stored.records[0])["Dato"] == "12.09.2026"
        assert stored.last_transaction_date == date(2026, 9, 12)

        def verdict_for(row: bytes) -> str:
            # A shape the format does not declare is a verdict on the payload,
            # not a refusal, and it derives nothing.
            result = PARSER.parse(header + row)
            assert result.records == ()
            assert result.last_transaction_date is None
            reason = result.failure_reason
            assert reason
            assert "Cafe" not in reason
            assert 'Ca"fe' not in reason
            assert "Caf\xe9" not in reason
            return reason

        unquoted_verdicts = []
        for label, row in unquoted_fields.items():
            with self.subTest(payload=label):
                unquoted_verdicts.append(verdict_for(row))

        # A field that never opens with a quote is the same defect whatever text
        # it carried instead.
        assert len(set(unquoted_verdicts)) == 1

        for label, row in other_shapes.items():
            with self.subTest(payload=label):
                verdict_for(row)

    def test_a_backslash_escaped_quote_is_one_quote_in_its_field(self) -> None:
        # The bank writes a quote inside a field as `\"`, not doubled: a Tekst
        # of `"Example"`, quotes included, arrives as `"\"Example\""`.
        payload = (
            b'"Dato";"Tekst";"Bel\xf8b";"Saldo";"Status";"Afstemt"\r\n'
            b'"12.09.2026";"\\"Example\\"";"-45,00";"955,00";"Udf\xf8rt";"Nej"'
        )

        result = PARSER.parse(payload)

        assert result.failure_reason is None
        assert [dict(record) for record in result.records] == [
            {
                "Dato": "12.09.2026",
                "Tekst": '"Example"',
                "Beløb": "-45,00",
                "Saldo": "955,00",
                "Status": "Udført",
                "Afstemt": "Nej",
            }
        ]

    def test_a_backslash_before_anything_but_a_quote_is_kept(self) -> None:
        # Only `\"` is an escape: any other backslash is source text, a doubled
        # one included.
        row = dato_row("12.09.2026").replace(b'" Caf\xe9"', rb'"\Cafe C:\\n\t"')

        result = PARSER.parse(header_payload(row))

        assert result.failure_reason is None
        assert dict(result.records[0])["Tekst"] == r"\Cafe C:\\n\t"

    def test_a_field_may_end_in_a_backslash(self) -> None:
        # The bank does not escape a backslash, so a Tekst ending in one is
        # written `\"` before its delimiter, a line break or the payload's end.
        # There the quote can only close the field.
        endings = {
            "before the delimiter": dato_row("12.09.2026").replace(
                b'" Caf\xe9"', rb'"Shop.dk/Ref\ \12345678\"'
            ),
            "before a line break": dato_row("12.09.2026").replace(b'"Nej"', rb'"Nej\"')
            + b"\r\n"
            + dato_row("13.09.2026"),
            "before an LF line break": dato_row("12.09.2026").replace(
                b'"Nej"', rb'"Nej\"'
            )
            + b"\n"
            + dato_row("13.09.2026"),
            "at the payload's end": dato_row("12.09.2026").replace(
                b'"Nej"', rb'"Nej\"'
            ),
        }
        expected = {
            "before the delimiter": ("Tekst", "Shop.dk/Ref\\ \\12345678\\"),
            "before a line break": ("Afstemt", "Nej\\"),
            "before an LF line break": ("Afstemt", "Nej\\"),
            "at the payload's end": ("Afstemt", "Nej\\"),
        }

        for label, row in endings.items():
            with self.subTest(payload=label):
                result = PARSER.parse(header_payload(row))

                assert result.failure_reason is None
                field, value = expected[label]
                assert dict(result.records[0])[field] == value

    def test_only_the_payloads_own_delimiter_ends_a_field_after_a_backslash(
        self,
    ) -> None:
        # The other accepted delimiter is ordinary text inside a field, so a
        # `\"` before it is still an escaped quote.
        header = (b"Dato", b"Tekst", b"Bel\xf8b", b"Saldo", b"Status", b"Afstemt")
        cases = {
            b";": (b'K\xf8b \\"X\\", Y', 'Køb "X", Y'),
            b",": (b'K\xf8b \\"X\\"; Y', 'Køb "X"; Y'),
        }

        for delimiter, (tekst, decoded) in cases.items():
            with self.subTest(delimiter=delimiter):
                record = (
                    b"12.09.2026",
                    tekst,
                    b"-45,00",
                    b"955,00",
                    b"Udf\xf8rt",
                    b"Nej",
                )
                payload = b"\r\n".join(
                    delimiter.join(b'"%s"' % value for value in row)
                    for row in (header, record)
                )

                result = PARSER.parse(payload)

                assert result.failure_reason is None
                assert dict(result.records[0])["Tekst"] == decoded

    def test_escaped_quotes_do_not_excuse_broken_quoting(self) -> None:
        broken = {
            # A `\"` before the delimiter is a backslash and the closing quote,
            # so a quote that really stood there ends the field early.
            "quote before the delimiter": rb'"\"Example\",x"',
            "data after the closing quote": rb'"\"Example\"" x',
        }

        for label, tekst in broken.items():
            with self.subTest(payload=label):
                row = dato_row("12.09.2026").replace(b'" Caf\xe9"', tekst)

                result = PARSER.parse(header_payload(row))

                assert result.records == ()
                assert result.last_transaction_date is None
                reason = result.failure_reason
                assert reason
                assert "Example" not in reason
                assert "\\" not in reason

    def test_a_row_ending_in_a_comma_still_needs_its_quoted_field(self) -> None:
        header = HEADER + b"\r\n"
        seven_fields = (
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt",'
        )

        # An empty final field is legal when it is quoted.
        quoted_empty = PARSER.parse(header + seven_fields + b'""')

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

    def test_one_trailing_line_break_is_accepted(self) -> None:
        # A single final line break carries no data, so an export an editor has
        # touched still reads. A blank line after the last record would be a
        # record of its own and stays invalid.
        for ending in (b"\r\n", b"\n"):
            with self.subTest(ending=ending):
                result = PARSER.parse(ONE_RECORD_PAYLOAD + ending)

                assert result.failure_reason is None
                assert len(result.records) == 1
                assert dict(result.records[0])["Dato"] == "12.09.2026"
                assert result.last_transaction_date == date(2026, 9, 12)

        for ending in (b"\r\n\r\n", b"\n\n"):
            with self.subTest(ending=ending):
                result = PARSER.parse(ONE_RECORD_PAYLOAD + ending)

                assert result.records == ()
                assert result.last_transaction_date is None
                assert result.failure_reason

    def test_a_comma_or_a_semicolon_delimits_a_whole_payload(self) -> None:
        # The bank's export dialog offers either delimiter and defaults to the
        # semicolon, so both read the same. One payload uses one of them
        # throughout; any other delimiter is not this format.
        semicolon_header = (
            b'"Dato";"Kategori";"Underkategori";"Tekst";'
            b'"Bel\xf8b";"Saldo";"Status";"Afstemt"'
        )
        semicolon_row = (
            b'"12.09.2026";" Mad ";" Dagligvarer ";" Caf\xe9, bar; k\xf8kken";'
            b'"-45,00";"955,00";"Udf\xf8rt";"Nej"'
        )
        semicolon_payload = semicolon_header + b"\r\n" + semicolon_row

        result = PARSER.parse(semicolon_payload + b"\r\n")

        assert result.failure_reason is None
        assert [dict(record) for record in result.records] == [
            {
                "Dato": "12.09.2026",
                "Kategori": " Mad ",
                "Underkategori": " Dagligvarer ",
                "Tekst": " Café, bar; køkken",
                "Beløb": "-45,00",
                "Saldo": "955,00",
                "Status": "Udført",
                "Afstemt": "Nej",
            }
        ]
        assert result.last_transaction_date == date(2026, 9, 12)

        # Mixing the two accepted delimiters is named as a delimiter mismatch,
        # not a quoting defect. A tab or a blank is no accepted delimiter, so
        # it is only unquoted data after a quoted field.
        mismatch = "different delimiter"
        unquoted = "unquoted data"
        rejected = {
            "semicolon header, comma record": (
                semicolon_header + b"\r\n" + ONE_RECORD_ROW,
                mismatch,
            ),
            "comma header, semicolon record": (
                HEADER + b"\r\n" + semicolon_row,
                mismatch,
            ),
            "both within one record": (
                HEADER + b"\r\n" + ONE_RECORD_ROW.replace(b'","-45,00"', b'";"-45,00"'),
                mismatch,
            ),
            "tab-delimited": (
                semicolon_payload.replace(b'";"', b'"\t"'),
                unquoted,
            ),
            "space-delimited": (
                semicolon_payload.replace(b'";"', b'" "'),
                unquoted,
            ),
        }

        for label, (content, named_defect) in rejected.items():
            with self.subTest(payload=label):
                refused = PARSER.parse(content)

                assert refused.records == ()
                assert refused.last_transaction_date is None
                reason = refused.failure_reason
                assert reason
                assert named_defect in reason
                assert "Caf" not in reason

    def test_an_account_without_bank_categories_exports_six_fields(self) -> None:
        # Some accounts carry no bank categories, and their exports leave out
        # Kategori and Underkategori entirely. The header names which of the
        # two declared layouts a payload uses, and its records present only the
        # fields it has: Bronze never invents the missing two.
        for delimiter in (b",", b";"):
            with self.subTest(delimiter=delimiter):
                header = delimiter.join(
                    (
                        b'"Dato"',
                        b'"Tekst"',
                        b'"Bel\xf8b"',
                        b'"Saldo"',
                        b'"Status"',
                        b'"Afstemt"',
                    )
                )
                rows = (
                    delimiter.join(
                        (
                            b'"05.09.2026"',
                            b'"Fra l\xf8nkonto"',
                            b'"1.000,00"',
                            b'"1.000,00"',
                            b'"Udf\xf8rt"',
                            b'"Nej"',
                        )
                    ),
                    delimiter.join(
                        (
                            b'"30.09.2026"',
                            b'"Rente"',
                            b'"16,45"',
                            b'"1.016,45"',
                            b'"Udf\xf8rt"',
                            b'"Nej"',
                        )
                    ),
                )

                result = PARSER.parse(b"\r\n".join((header, *rows)))

                assert result.failure_reason is None
                assert [dict(record) for record in result.records] == [
                    {
                        "Dato": "05.09.2026",
                        "Tekst": "Fra lønkonto",
                        "Beløb": "1.000,00",
                        "Saldo": "1.000,00",
                        "Status": "Udført",
                        "Afstemt": "Nej",
                    },
                    {
                        "Dato": "30.09.2026",
                        "Tekst": "Rente",
                        "Beløb": "16,45",
                        "Saldo": "1.016,45",
                        "Status": "Udført",
                        "Afstemt": "Nej",
                    },
                ]
                assert result.last_transaction_date == date(2026, 9, 30)

        six_field_header = b'"Dato","Tekst","Bel\xf8b","Saldo","Status","Afstemt"'
        six_field_row = b'"12.09.2026","Caf\xe9","-45,00","955,00","Udf\xf8rt","Nej"'
        rejected = {
            "six-field header, eight-field record": (
                six_field_header + b"\r\n" + ONE_RECORD_ROW
            ),
            "eight-field header, six-field record": HEADER + b"\r\n" + six_field_row,
            "only one of the two category fields": (
                HEADER.replace(b'"Underkategori",', b"")
                + b"\r\n"
                + ONE_RECORD_ROW.replace(b'" Dagligvarer ",', b"")
            ),
        }

        for label, content in rejected.items():
            with self.subTest(payload=label):
                refused = PARSER.parse(content)

                assert refused.records == ()
                assert refused.last_transaction_date is None
                reason = refused.failure_reason
                assert reason
                assert "Caf" not in reason

    def test_the_coverage_bounds_are_the_date_span_whatever_the_row_order(
        self,
    ) -> None:
        # The row carrying the maximum Dato comes first and is cancelled, and
        # the minimum sits between two later dates, so a bound read from row
        # order or Status would land somewhere else.
        payload = header_payload(
            b'"12.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Slettet","Nej"',
            b'"05.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","1000,00","Udf\xf8rt","Nej"',
            b'"08.09.2026"," Mad "," Dagligvarer "," Caf\xe9",'
            b'"-45,00","955,00","Udf\xf8rt","Nej"',
        )

        result = PARSER.parse(payload)

        assert result.failure_reason is None
        assert result.first_transaction_date == date(2026, 9, 5)
        assert result.last_transaction_date == date(2026, 9, 12)
        assert [dict(record)["Dato"] for record in result.records] == [
            "12.09.2026",
            "05.09.2026",
            "08.09.2026",
        ]
        assert [dict(record)["Status"] for record in result.records] == [
            "Slettet",
            "Udført",
            "Udført",
        ]

        # A payload that states no transactions is readable and bounds nothing.
        quiet = PARSER.parse(header_payload())
        assert quiet.failure_reason is None
        assert quiet.records == ()
        assert quiet.first_transaction_date is None
        assert quiet.last_transaction_date is None

    def test_a_date_must_be_zero_padded_dd_mm_yyyy(self) -> None:
        # The declared shape is two day digits, two month digits and four year
        # digits, separated by periods. A one-digit day or month, a leading
        # space, Unicode digits, the ISO order, trailing text and any other
        # separator are each outside it.
        rejected = (
            "1.9.2026",
            "01.9.2026",
            " 1.09.2026",
            "3.10.2026",
            "2026-09-12",
            "12.09.2026 ",
            "¹².09.2026",
            "12-09-2026",
            "12/09/2026",
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

        accepted = PARSER.parse(header_payload(dato_row("12.09.2026")))
        assert accepted.failure_reason is None
        assert [dict(record)["Dato"] for record in accepted.records] == ["12.09.2026"]
        assert accepted.last_transaction_date == date(2026, 9, 12)

    def test_an_unreadable_transaction_date_is_a_verdict_without_records(self) -> None:
        row = (
            b'%s," Mad "," Dagligvarer "," Caf\xe9","-45,00","955,00","Udf\xf8rt","Nej"'
        )
        malformed = {
            "impossible date": b'"31.02.2026"',
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
        # A browser copy suffix does not turn a refusal into a missing date.
        for filename in (
            "synthetic-20260931.csv",
            "synthetic-20260931(3).csv",
            "synthetic-20260931 (3).csv",
        ):
            with self.subTest(filename=filename):
                with pytest.raises(ValueError, match="not a real date") as refusal:
                    PARSER.exported_on_from_filename(filename)

                assert "synthetic" not in str(refusal.value)
                assert "20260931" not in str(refusal.value)

    def test_the_parser_reads_the_account_number_before_the_date_suffix(
        self,
    ) -> None:
        # A string, so the leading zeros survive.
        assert (
            PARSER.account_number_from_filename("synthetic-0012345678-20260914.csv")
            == "0012345678"
        )
        assert (
            PARSER.account_number_from_filename("SYNTHETIC-0012345678-20260914.CSV")
            == "0012345678"
        )
        # Only the ten digits right before the date suffix are the number.
        assert (
            PARSER.account_number_from_filename(
                "synthetic-9999999999-0012345678-20260914.csv"
            )
            == "0012345678"
        )

    def test_a_name_without_a_ten_digit_account_number_carries_none(self) -> None:
        # No number means no check, never a failure.
        arabic_indic = "".join(chr(0x0660 + int(digit)) for digit in "0012345678")
        for filename in (
            "synthetic-20260914.csv",
            "synthetic-123456789-20260914.csv",
            "synthetic-12345678901-20260914.csv",
            "0012345678-20260914.csv",
            "synthetic-0012345678.csv",
            "synthetic-0012345678-20260914.txt",
            f"synthetic-{arabic_indic}-20260914.csv",
        ):
            with self.subTest(filename=filename):
                assert PARSER.account_number_from_filename(filename) is None

    def test_a_browser_copy_suffix_keeps_the_filename_convention(self) -> None:
        # A browser saves a second download of one name as "…(1).csv".
        for filename in (
            "synthetic-0012345678-20260914(1).csv",
            "synthetic-0012345678-20260914 (2).csv",
            "synthetic-0012345678-20260914(12).CSV",
        ):
            with self.subTest(filename=filename):
                assert PARSER.exported_on_from_filename(filename) == date(2026, 9, 14)
                assert PARSER.account_number_from_filename(filename) == "0012345678"
        for filename in (
            "synthetic-0012345678-20260914().csv",
            "synthetic-0012345678-20260914(a).csv",
            "synthetic-0012345678-20260914  (1).csv",
            "synthetic-0012345678-20260914(1)(2).csv",
        ):
            with self.subTest(filename=filename):
                assert PARSER.exported_on_from_filename(filename) is None
                assert PARSER.account_number_from_filename(filename) is None

    def test_a_declared_account_number_is_ten_ascii_digits(self) -> None:
        assert PARSER.is_account_number("0012345678")
        arabic_indic = "".join(chr(0x0660 + int(digit)) for digit in "0012345678")
        for value in (
            "3456 0012345678",
            "3456-0012345678",
            " 0012345678",
            "0012345678 ",
            "12345678",
            "00123456789",
            arabic_indic,
        ):
            with self.subTest(value=value):
                assert not PARSER.is_account_number(value)


if __name__ == "__main__":
    unittest.main()
