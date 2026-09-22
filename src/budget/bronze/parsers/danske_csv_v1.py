"""``danske-csv-v1``: one bank's CSV export, exactly as it declares itself.

Everything format-specific lives here - the encoding, the declared header, the
quoting shape, and the transaction-date syntax. The store knows none of it, and
a future format gets its own module and its own ID rather than a change to this
one's meaning.
"""

import csv
from datetime import date, datetime
from io import StringIO
import re

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
_TRANSACTION_DATE = "%d-%m-%Y"

# The export date convention of this format: `…-YYYYMMDD.csv`.
_EXPORT_DATE_SUFFIX = re.compile(r"-([0-9]{8})\.csv$", re.IGNORECASE)
_EXPORT_DATE = "%Y%m%d"


def _field_quoting_error(text: str) -> str | None:
    """Return why the payload's quoting is not the declared shape, if it is not.

    `danske-csv-v1` quotes every field, and a quote inside a field is doubled.
    So a field opens with a quote, and only a comma, a line break or the end of
    the payload may follow its closing quote. Line endings themselves are not
    checked: the declared CRLF and no-final-line-break rules stay the
    prototype's notes, and a quoted field may carry line breaks of its own.
    """
    index = 0
    length = len(text)
    while index < length:
        if text[index] != '"':
            return "every field must be double-quoted"
        index += 1
        while True:
            if index >= length:
                return "a quoted field is never closed"
            if text[index] == '"':
                if text[index + 1 : index + 2] == '"':
                    index += 2
                    continue
                index += 1
                break
            index += 1
        if index >= length:
            return None
        if text[index] == ",":
            index += 1
            if index >= length:
                # A comma promises another field, and every field is quoted: a
                # bare trailing delimiter is an unquoted empty field.
                return "a record ends with a comma and no quoted field"
            continue
        if text[index] == "\r" and text[index + 1 : index + 2] == "\n":
            index += 2
            continue
        if text[index] in "\r\n":
            index += 1
            continue
        return "a quoted field is followed by unquoted data"
    return None


def _split_payload(content: bytes) -> tuple[list[dict[str, str]], str | None]:
    """Split one payload into source records, or name why it does not match.

    The verdict is deterministic and describes the payload as a whole; it never
    repeats source content, so a failure reason stays safe to show or log.
    """
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
    header, *data = rows
    if tuple(header) != _HEADER:
        return [], "payload header does not match danske-csv-v1"
    records = []
    for ordinal, values in enumerate(data, start=1):
        if len(values) != len(_HEADER):
            return [], (
                f"record {ordinal} has {len(values)} fields, "
                f"expected {len(_HEADER)}"
            )
        records.append(dict(zip(_HEADER, values, strict=True)))
    return records, None


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
        try:
            value = datetime.strptime(fields["Dato"], _TRANSACTION_DATE).date()
        except (KeyError, ValueError):
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
        try:
            return datetime.strptime(suffix.group(1), _EXPORT_DATE).date()
        except ValueError:
            # The name is private provenance: the verdict states the defect and
            # never repeats the digits it came from.
            raise ValueError(
                "the filename's date suffix is not a real date"
            ) from None


# The one parser instance the registry declares for this format ID.
PARSER: SourceParser = DanskeCsvV1Parser()
