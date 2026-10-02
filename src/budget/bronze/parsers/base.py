# Copyright 2026 Therkel
"""The contract every source parser implements.

A parser is the only place that knows a source format's rules: its encoding,
its layout, its field names, and the syntax of any date it has to read. It
takes the exact bytes of one raw payload and returns one `ParserResult`. It
never touches storage, never guesses which format it is looking at, and leaves
every decoded field as it arrived. The one value a parser reads rather than
presents is the transaction date, whose earliest and latest values bound a
declared range from `covers_from` through `covers_through`; `danske_csv_v1` is
today's example, and nothing else may be trimmed, typed, or mapped.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class ParserResult:
    """One payload's source records, or the reason it does not match.

    `records` are keyed by the format's own field names and keep their decoded
    strings untouched: no trimming, typing, or mapping.
    `first_transaction_date` and `last_transaction_date` are the earliest and
    latest values of the same source date field over every record, and exist
    for one purpose, bounding a declared range; they are never stored in place
    of the source value, and both are `None` when there are no records.
    `failure_reason` is a verdict on the payload as a whole, safe to show or
    log because it repeats neither source content nor the filename.

    A parser reports either records or a failure, never both. `matched` and
    `failed` are convenience constructors for those two cases; this dataclass
    is a plain frozen record with no runtime validation, so keeping the two
    apart is the parser's obligation rather than something the type enforces.
    """

    records: tuple[Mapping[str, str], ...] = ()
    first_transaction_date: date | None = None
    last_transaction_date: date | None = None
    failure_reason: str | None = None

    @classmethod
    def matched(
        cls,
        records: tuple[Mapping[str, str], ...],
        first_transaction_date: date | None,
        last_transaction_date: date | None,
    ) -> "ParserResult":
        """Present a payload the parser recognised in full, and its date span."""
        return cls(
            records=records,
            first_transaction_date=first_transaction_date,
            last_transaction_date=last_transaction_date,
        )

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

    def account_number_from_filename(self, filename: str) -> str | None:
        """Read the bank account number a filename carries, if this format has one.

        The number exists only to be checked against the account's declared
        `bank_account_number`: it is never stored as Bronze evidence and never
        selects an account. `None` means the name carries no number this format
        recognises, so no check applies.
        """
        ...

    def is_account_number(self, value: str) -> bool:
        """Say whether a declared number has the shape this format's filenames carry.

        A declaration of another shape could never match a filename, so every
        export for the account would be refused as misfiled. The account
        registry refuses it instead, where the household can see the cause.
        """
        ...
