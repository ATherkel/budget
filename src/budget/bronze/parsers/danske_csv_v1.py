# Copyright 2026 Therkel
"""``danske-csv-v1``: one bank's CSV export, exactly as it declares itself.

Everything format-specific lives here - the encoding, the declared headers, the
delimiters, the quoting shape, and the transaction-date syntax. The store knows
none of it, and a future format gets its own module and its own ID rather than a
change to this one's meaning. A declared variant the payload names itself, such
as its delimiter or its header layout, is part of this format (see
`docs/developers/source-parsers.md`).
"""

import csv
import re
from datetime import date
from io import StringIO

from budget.bronze.parsers.base import ParserResult, SourceParser

SOURCE_FORMAT_ID = "danske-csv-v1"

# The declared headers of `danske-csv-v1`, in order. An account with bank
# categories exports all eight fields; one without them leaves out Kategori and
# Underkategori entirely. A payload's header must be exactly one of these, it is
# split against that one, and no other field name is ever interpreted.
_HEADERS = (
    (
        "Dato",
        "Kategori",
        "Underkategori",
        "Tekst",
        "Beløb",
        "Saldo",
        "Status",
        "Afstemt",
    ),
    ("Dato", "Tekst", "Beløb", "Saldo", "Status", "Afstemt"),
)

# The delimiters this format accepts. The bank's export dialog offers a comma
# or a semicolon (the default); its blank and tab choices are not this format.
_DELIMITERS = (",", ";")

# The transaction date is the only value this parser reads rather than presents.
# `re.ASCII` keeps `\d` to 0-9: otherwise it also matches other scripts'
# digits, such as Arabic-Indic ones, which `int()` then reads as numbers.
_TRANSACTION_DATE = re.compile(r"\d{2}\.\d{2}\.\d{4}", re.ASCII)

# The end of every name this format reads: `.csv`, after at most one browser
# copy suffix such as `(1)` or ` (1)`, which a browser adds when it saves a second
# download under a name it has already used.
_NAME_END = r"(?: ?\([0-9]+\))?\.csv$"

# The export date convention of this format: `…-YYYYMMDD.csv`.
_EXPORT_DATE_SUFFIX = re.compile(rf"-([0-9]{{8}}){_NAME_END}", re.IGNORECASE)

# The account number convention of this format: `<name>-<10 digits>-YYYYMMDD.csv`.
# Only the ten digits right before the date suffix count, and only after a name.
# A declared number must have that same shape, or it could never match.
_ACCOUNT_NUMBER_DIGITS = "[0-9]{10}"
_ACCOUNT_NUMBER = re.compile(
    rf".-({_ACCOUNT_NUMBER_DIGITS})-[0-9]{{8}}{_NAME_END}", re.IGNORECASE
)
_DECLARED_ACCOUNT_NUMBER = re.compile(_ACCOUNT_NUMBER_DIGITS)


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


def _record_separator_end(
    text: str, index: int, delimiter: str
) -> tuple[int, str | None]:
    """Return the index after a separator, or why that position is not one."""
    length = len(text)
    if index >= length:
        return index, None
    if text[index] == delimiter:
        # A delimiter promises another field, and every field is quoted: a bare
        # trailing delimiter is an unquoted empty field.
        if index + 1 >= length:
            return index, "a record ends with a delimiter and no quoted field"
        return index + 1, None
    if text[index] in "\r\n":
        # A CRLF is one line break, not two.
        return index + (2 if text.startswith("\r\n", index) else 1), None
    if text[index] in _DELIMITERS:
        return index, "a record uses a different delimiter than the header"
    return index, "a quoted field is followed by unquoted data"


def _payload_delimiter(text: str) -> str:
    """Return the delimiter the header writes after its first field.

    The header names the payload's delimiter, so nothing is sniffed from the
    data. A header that shows no accepted delimiter there is read with the
    comma, and the quoting check then rejects it: a tab or a blank, like any
    other character, is unquoted data after a closing quote.
    """
    if text.startswith('"'):
        index, _ = _quoted_field_end(text, 1)
        found = text[index : index + 1]
        if found in _DELIMITERS:
            return found
    return _DELIMITERS[0]


def _field_quoting_error(text: str, delimiter: str) -> str | None:
    """Return why the payload's quoting is not the declared shape, if it is not.

    `danske-csv-v1` quotes every field, and a quote inside a field is doubled.
    So a field opens with a quote, and only the payload's delimiter, a line
    break or the end of the payload may follow its closing quote. One payload
    keeps one delimiter, so a record written with the other one fails here.
    Line endings are not otherwise checked: LF endings and one optional final
    line break read normally, and a quoted field may carry line breaks of its
    own.
    """
    index = 0
    length = len(text)
    while index < length:
        if text[index] != '"':
            return "every field must be double-quoted"
        index, error = _quoted_field_end(text, index + 1)
        if error is not None:
            return error
        index, error = _record_separator_end(text, index, delimiter)
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
    delimiter = _payload_delimiter(text)
    quoting_error = _field_quoting_error(text, delimiter)
    if quoting_error is not None:
        return [], f"payload quoting does not match danske-csv-v1: {quoting_error}"
    try:
        rows = list(
            csv.reader(
                StringIO(text, newline=""),
                delimiter=delimiter,
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
    first, *data = rows
    header = tuple(first)
    if header not in _HEADERS:
        return [], "payload header does not match danske-csv-v1"
    records = []
    for ordinal, values in enumerate(data, start=1):
        if len(values) != len(header):
            return [], (
                f"record {ordinal} has {len(values)} fields, expected {len(header)}"
            )
        records.append(dict(zip(header, values, strict=True)))
    return records, None


def _transaction_date(value: str) -> date | None:
    """Read one zero-padded `DD.MM.YYYY` transaction date, or None.

    The declared shape is exact: two ASCII day digits, two month digits and four
    year digits, separated by periods, and the result must be a real calendar
    date. A one-digit day or month, a leading space, Unicode digits, the ISO
    order, another separator or trailing text is a malformed `Dato`, so the
    payload gets a format failure instead of a guess.
    """
    if _TRANSACTION_DATE.fullmatch(value) is None:
        return None
    try:
        return date(int(value[6:]), int(value[3:5]), int(value[:2]))
    except ValueError:
        return None


def _transaction_date_span(
    records: list[dict[str, str]],
) -> tuple[tuple[date | None, date | None], str | None]:
    """Read Dato for one purpose only: bounding a declared covered range.

    Every record counts, whatever its row order or Status, and neither value is
    stored anywhere: the source record keeps its original string. A payload
    whose Dato cannot be read yields a verdict instead, so a missing bound can
    never pass for a satisfied one.
    """
    first: date | None = None
    last: date | None = None
    for ordinal, fields in enumerate(records, start=1):
        value = _transaction_date(fields["Dato"])
        if value is None:
            return (None, None), f"record {ordinal} has an unreadable transaction date"
        if first is None or value < first:
            first = value
        if last is None or value > last:
            last = value
    return (first, last), None


class DanskeCsvV1Parser:
    """The declared rules of `danske-csv-v1`."""

    source_format = SOURCE_FORMAT_ID

    def parse(self, content: bytes) -> ParserResult:
        """Present one `danske-csv-v1` payload's records, or why it does not match."""
        records, failure_reason = _split_payload(content)
        if failure_reason is not None:
            return ParserResult.failed(failure_reason)
        (first, last), failure_reason = _transaction_date_span(records)
        if failure_reason is not None:
            return ParserResult.failed(failure_reason)
        return ParserResult.matched(tuple(records), first, last)

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

    def account_number_from_filename(self, filename: str) -> str | None:
        """Read the account number of a `<name>-<10 digits>-YYYYMMDD.csv` name."""
        match = _ACCOUNT_NUMBER.search(filename)
        return None if match is None else str(match.group(1))

    def is_account_number(self, value: str) -> bool:
        """Accept the ten ASCII digits a `danske-csv-v1` filename carries."""
        return _DECLARED_ACCOUNT_NUMBER.fullmatch(value) is not None


# The one parser instance the registry declares for this format ID.
PARSER: SourceParser = DanskeCsvV1Parser()
