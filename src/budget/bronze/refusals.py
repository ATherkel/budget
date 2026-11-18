# Copyright 2026 Therkel
"""The codes that say why Bronze refused an import run, defined once.

Each code names a rule, never a date, amount, account number or file name.
bronze-layer.md "Rules" lists them with the rule each one stands for. The SQL
migration `bronze/0002_record_refusal_reasons.sql` spells
`RefusalCode.LEGACY_UNRECORDED` as a literal, because a migration is frozen text.
"""

from enum import StrEnum

# Every code Bronze can record, in the order a run records its codes.
REFUSAL_CODES: Final = (
    ACCOUNT_CONFLICT,
    RANGE_STARTS_AFTER_END,
    RANGE_ENDS_AFTER_EXPORT,
    TRANSACTION_BEFORE_RANGE,
    TRANSACTION_AFTER_RANGE,
    LEGACY_UNRECORDED,
)


class RefusalCode(StrEnum):
    """A rule Bronze refused an import run for, in the order bronze-layer.md lists."""

    ACCOUNT_CONFLICT = "account-conflict"
    RANGE_STARTS_AFTER_END = "range-starts-after-end"
    RANGE_ENDS_AFTER_EXPORT = "range-ends-after-export"
    TRANSACTION_BEFORE_RANGE = "transaction-before-range"
    TRANSACTION_AFTER_RANGE = "transaction-after-range"
    # A run refused before codes were recorded: its rule is not known.
    LEGACY_UNRECORDED = "legacy-unrecorded"


def format_1_refusal_reasons(outcome: str) -> tuple[RefusalCode, ...]:
    """Return the codes a run recorded before refusal codes existed implies.

    The first import log format and the first Bronze schema recorded none, so
    a refused run reads as `legacy-unrecorded` and any other run as having
    none. The schema's backfill, replay, the import's log check and a read of
    an older store all use this, so they cannot disagree about an old run.
    """
    return (RefusalCode.LEGACY_UNRECORDED,) if outcome == "refused" else ()
