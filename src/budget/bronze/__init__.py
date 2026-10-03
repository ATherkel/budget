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
from budget.bronze.storage import (
    migrate_bronze,
    require_migration_allowed,
)
from budget.bronze.store import BronzeStore

__all__ = [
    "BronzeStore",
    "FormatFailure",
    "ImportDeclaration",
    "ImportRun",
    "RawPayload",
    "SourceRecord",
    "migrate_bronze",
    "require_migration_allowed",
]
