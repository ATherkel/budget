# Copyright 2026 Therkel
"""Public Bronze contracts and local, source-preserving file ingestion.

`budget.bronze` is the seam the rest of the application imports. Everything
else in the package is an implementation detail: parsing lives behind
`budget.bronze.parsers`, which is where a new source format is added.
"""

from budget.bronze.models import (
    FormatFailure,
    ImportDeclaration,
    ImportRun,
    RawPayload,
    SourceRecord,
)
from budget.bronze.refusals import (
    ACCOUNT_CONFLICT,
    LEGACY_UNRECORDED,
    RANGE_ENDS_AFTER_EXPORT,
    RANGE_STARTS_AFTER_END,
    TRANSACTION_AFTER_RANGE,
    TRANSACTION_BEFORE_RANGE,
)
from budget.bronze.storage import (
    migrate_bronze,
)
from budget.bronze.store import BronzeStore

__all__ = [
    "ACCOUNT_CONFLICT",
    "LEGACY_UNRECORDED",
    "RANGE_ENDS_AFTER_EXPORT",
    "RANGE_STARTS_AFTER_END",
    "TRANSACTION_AFTER_RANGE",
    "TRANSACTION_BEFORE_RANGE",
    "BronzeStore",
    "FormatFailure",
    "ImportDeclaration",
    "ImportRun",
    "RawPayload",
    "SourceRecord",
    "migrate_bronze",
]
