# Copyright 2026 Therkel
"""Source formats: each reads its source records into source-neutral values."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from budget.bronze.models import SourceRecord
from budget.silver.formats import danske_csv_v1
from budget.silver.formats.record import ReadRecord, ReadResult, RecordError

type RecordReader = Callable[[SourceRecord, int], ReadResult]


@dataclass(frozen=True)
class SourceFormat:
    """How Silver reads one source format."""

    read: RecordReader
    # A format that states a balance on every booked row has its balance
    # chain verified within each export (ADR-010).
    states_balances: bool


FORMATS: Mapping[str, SourceFormat] = {
    "danske-csv-v1": SourceFormat(read=danske_csv_v1.read_record, states_balances=True),
}

__all__ = ["FORMATS", "ReadRecord", "ReadResult", "RecordError", "SourceFormat"]
