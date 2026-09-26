# Copyright 2026 Therkel
"""``danske-csv-v1``: one bank's CSV export, exactly as it declares itself.

Everything format-specific lives here - the encoding, the declared header, the
quoting shape, and the transaction-date syntax. The store knows none of it, and
a future format gets its own module and its own ID rather than a change to this
one's meaning.
"""

import csv
import re
from datetime import date
from io import StringIO

from budget.bronze.parsers.base import ParserResult, SourceParser

SOURCE_FORMAT_ID = "danske-csv-v1"

# The declared header of `danske-csv-v1`, in order. A payload is split against
# exactly this, and no other field name is ever interpreted.
_HEADER = (
    "Dato",
    "Kategori",
    "Underkategori",
    "Tekst",
    "Beløb",
    "Saldo",
    "Status",
    "Afstemt",
)

# The transaction date is the only value this parser reads rather than presents.
_TRANSACTION_DATE = re.compile(r"[0-9]{2}-[0-9]{2}-[0-9]{4}")

# The export date convention of this format: `…-YYYYMMDD.csv`.
_EXPORT_DATE_SUFFIX = re.compile(r"-([0-9]{8})\.csv$", re.IGNORECASE)


class ExportDateSuffixError(ValueError):
    """A recognised export-date suffix is not a real date."""

    def __init__(self) -> None:
        """State the defect without repeating the private filename."""
        super().__init__("the filename's date suffix is not a real date")


def _quoted_field_end(text: str, start: int) -> tuple[int, str | None]:
    """Return the index after a field's closing quote, or why it never closes."""
    index = start
    length = len(text)
    while index < length:
        if text[index] != '"':
            index += 1
            continue
        if text[index + 1 : index + 2] == '"':
            index += 2
            continue
        return index + 1, None
    return index, "a quoted field is never closed"


def _record_separator_end(text: str, index: int) -> tuple[int, str | None]:
    """Return the index after a separator, or why that position is not one."""
    length = len(text)
    if index >= length:
        return index, None
    if text[index] == ",":
        # A comma promises another field, and every field is quoted: a bare
        # trailing delimiter is an unquoted empty field.
        if index + 1 >= length:
            return index, "a record ends with a comma and no quoted field"
        return index + 1, None
    if text[index] == "\r" and text[index + 1 : index + 2] == "\n":
        return index + 2, None
    if text[index] in "\r\n":
        return index + 1, None
    return index, "a quoted field is followed by unquoted data"


def _field_quoting_error(text: str) -> str | None:
    """Return why the payload's quoting is not the declared shape, if it is not.

    `danske-csv-v1` quotes every field, and a quote inside a field is doubled.
    So a field opens with a quote, and only a comma, a line break or the end of
    the payload may follow its closing quote. Line endings are not otherwise
    checked: LF endings and one optional final line break read normally, and a
    quoted field may carry line breaks of its own.
    """
    index = 0
    length = len(text)
    while index < length:
        if text[index] != '"':
            return "every field must be double-quoted"
        index, error = _quoted_field_end(text, index + 1)
        if error is not None:
            return error
        index, error = _record_separator_end(text, index)
        if error is not None:
            return error
    return None


def _split_rows(content: bytes) -> tuple[list[list[str]], str | None]:
    """Read one payload as CSV rows, or name why it is not readable at all."""
    try:
        text = content.decode("cp1252", errors="strict")
    except UnicodeDecodeError:
        return [], "payload is not strict Windows-1252"
    if not text:
        return [], "payload is empty"
    quoting_error = _field_quoting_error(text)
    if quoting_error is not None:
        return [], f"payload quoting does not match danske-csv-v1: {quoting_error}"
    try:
        rows = list(
            csv.reader(
                StringIO(text, newline=""),
                delimiter=",",
                quotechar='"',
                strict=True,
            )
        )
    except csv.Error:
        return [], "payload is not well-formed CSV"
    if not rows:
        return [], "payload is empty"
    return rows, None


def _split_payload(content: bytes) -> tuple[list[dict[str, str]], str | None]:
    """Split one payload into source records, or name why it does not match.

    The verdict is deterministic and describes the payload as a whole; it never
    repeats source content, so a failure reason stays safe to show or log.
    """
    rows, failure_reason = _split_rows(content)
    if failure_reason is not None:
        return [], failure_reason
    header, *data = rows
    if tuple(header) != _HEADER:
        return [], "payload header does not match danske-csv-v1"
    records = []
    for ordinal, values in enumerate(data, start=1):
        if len(values) != len(_HEADER):
            return [], (
                f"record {ordinal} has {len(values)} fields, expected {len(_HEADER)}"
            )
        records.append(dict(zip(_HEADER, values, strict=True)))
    return records, None


def _transaction_date(value: str) -> date | None:
    """Read one zero-padded `DD-MM-YYYY` transaction date, or None.

    The declared shape is exact: two ASCII day digits, two month digits and four
    year digits, and the result must be a real calendar date. A one-digit day or
    month, a leading space, Unicode digits, the ISO order or trailing text is a
    malformed `Dato`, so the payload gets a format failure instead of a guess.
    """
    if _TRANSACTION_DATE.fullmatch(value) is None:
        return None
    try:
        return date(int(value[6:]), int(value[3:5]), int(value[:2]))
    except ValueError:
        return None


def _last_transaction_date(
    records: list[dict[str, str]],
) -> tuple[date | None, str | None]:
    """Read Dato for one purpose only: bounding a covers_through declaration.

    Every record counts, whatever its row order or Status, and the value is
    never stored anywhere: the source record keeps its original string. A
    payload whose Dato cannot be read yields a verdict instead, so a missing
    bound can never pass for a satisfied one.
    """
    last: date | None = None
    for ordinal, fields in enumerate(records, start=1):
        value = _transaction_date(fields["Dato"])
        if value is None:
            return None, f"record {ordinal} has an unreadable transaction date"
        if last is None or value > last:
            last = value
    return last, None


class DanskeCsvV1Parser:
    """The declared rules of `danske-csv-v1`."""

    source_format = SOURCE_FORMAT_ID

    def parse(self, content: bytes) -> ParserResult:
        """Present one `danske-csv-v1` payload's records, or why it does not match."""
        records, failure_reason = _split_payload(content)
        if failure_reason is not None:
            return ParserResult.failed(failure_reason)
        last_transaction_date, failure_reason = _last_transaction_date(records)
        if failure_reason is not None:
            return ParserResult.failed(failure_reason)
        return ParserResult.matched(tuple(records), last_transaction_date)

    def exported_on_from_filename(self, filename: str) -> date | None:
        """Read the `-YYYYMMDD.csv` export date, if the name carries one."""
        suffix = _EXPORT_DATE_SUFFIX.search(filename)
        if suffix is None:
            return None
        digits = suffix.group(1)
        try:
            return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            # The name is private provenance: the verdict states the defect and
            # never repeats the digits it came from.
            raise ExportDateSuffixError from None


# The one parser instance the registry declares for this format ID.
PARSER: SourceParser = DanskeCsvV1Parser()
