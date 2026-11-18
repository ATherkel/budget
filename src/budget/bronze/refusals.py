# Copyright 2026 Therkel
"""The codes that say why Bronze refused an import run, named once.

Each code names a rule, never a date, amount, account number or file name.
bronze-layer.md "Rules" lists them with the rule each one stands for. The SQL
migration `bronze/0002_record_refusal_reasons.sql` spells `LEGACY_UNRECORDED`
as a literal, because a migration is frozen text.
"""

from enum import StrEnum
from typing import Final


class RefusalCode(StrEnum):
    """A rule Bronze refused an import run for, in the order bronze-layer.md lists."""

    ACCOUNT_CONFLICT = "account-conflict"
    RANGE_STARTS_AFTER_END = "range-starts-after-end"
    RANGE_ENDS_AFTER_EXPORT = "range-ends-after-export"
    TRANSACTION_BEFORE_RANGE = "transaction-before-range"
    TRANSACTION_AFTER_RANGE = "transaction-after-range"
    LEGACY_UNRECORDED = "legacy-unrecorded"


ACCOUNT_CONFLICT: Final = "account-conflict"
RANGE_STARTS_AFTER_END: Final = "range-starts-after-end"
RANGE_ENDS_AFTER_EXPORT: Final = "range-ends-after-export"
TRANSACTION_BEFORE_RANGE: Final = "transaction-before-range"
TRANSACTION_AFTER_RANGE: Final = "transaction-after-range"
# A run refused before codes were recorded: its rule is not known.
LEGACY_UNRECORDED: Final = "legacy-unrecorded"


def format_1_refusal_reasons(outcome: str) -> tuple[str, ...]:
    """Return the codes a run recorded before refusal codes existed implies.

    The first import log format and the first Bronze schema recorded none, so
    a refused run reads as `legacy-unrecorded` and any other run as having
    none. The schema's backfill, replay, the import's log check and a read of
    an older store all use this, so they cannot disagree about an old run.
    """
    return (LEGACY_UNRECORDED,) if outcome == "refused" else ()
