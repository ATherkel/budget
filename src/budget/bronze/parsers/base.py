"""The contract every source parser implements.

A parser is the only place that knows a source format's rules: its encoding,
its layout, its field names, and the syntax of any date it has to read. It
takes the exact bytes of one raw payload and returns one `ParserResult`. It
never touches storage, never guesses which format it is looking at, and never
interprets a value.
"""

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ParserResult:
    """One payload's source records, or the reason it does not match.

    `records` are keyed by the format's own field names and keep their decoded
    strings untouched: no trimming, typing, or mapping. `last_transaction_date`
    exists for one purpose, bounding a declared `covers_through`; it is never
    stored in place of the source value. `failure_reason` is a verdict on the
    payload as a whole, safe to show or log because it repeats neither source
    content nor the filename. A failure exposes no records, which is why the
    two cases are constructed rather than assembled by hand.
    """

    records: tuple[Mapping[str, str], ...] = ()
    last_transaction_date: date | None = None
    failure_reason: str | None = None

    @classmethod
    def matched(
        cls,
        records: tuple[Mapping[str, str], ...],
        last_transaction_date: date | None,
    ) -> "ParserResult":
        """Present a payload the parser recognised in full."""
        return cls(records=records, last_transaction_date=last_transaction_date)

    @classmethod
    def failed(cls, reason: str) -> "ParserResult":
        """Present a payload the parser could not read, and why, and nothing else."""
        return cls(failure_reason=reason)


class SourceParser(Protocol):
    """One declared source format, named by its exact format ID."""

    source_format: str

    def parse(self, content: bytes) -> ParserResult:
        """Split one payload into source records, or state why it does not match."""
        ...

    def exported_on_from_filename(self, filename: str) -> date | None:
        """Read the export date a filename declares, if this format declares one.

        `None` means the name carries no date this format recognises, so the
        operator has to declare one. A `ValueError` means the name carries a
        date-shaped suffix that is not a real date, which is a mistake rather
        than a missing declaration. The message never repeats the filename.
        """
        ...
