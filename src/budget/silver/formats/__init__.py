# Copyright 2026 Therkel
"""Source formats: each reads its source records into source-neutral values."""

from collections.abc import Callable, Mapping

from budget.bronze.models import SourceRecord
from budget.silver.formats import danske_csv_v1
from budget.silver.formats.record import ReadRecord

type RecordReader = Callable[[SourceRecord, int], ReadRecord]

READERS: Mapping[str, RecordReader] = {
    "danske-csv-v1": danske_csv_v1.read_record,
}

__all__ = ["READERS", "ReadRecord", "RecordReader"]
