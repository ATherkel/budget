# Copyright 2026 Therkel
"""Bank-independent safeguards for a declared covered range.

Nothing in this module knows a source format. It decides whether one import
run's declared range, from `covers_from` through `covers_through`, is one the
payload and its export date allow, whatever produced the payload.
"""

from datetime import date

from budget.bronze.refusals import (
    RANGE_ENDS_AFTER_EXPORT,
    RANGE_STARTS_AFTER_END,
    TRANSACTION_AFTER_RANGE,
    TRANSACTION_BEFORE_RANGE,
)


def declared_range_refusals(
    *,
    covers_from: date,
    covers_through: date,
    exported_on: date,
    first_transaction_date: date | None,
    last_transaction_date: date | None,
) -> tuple[str, ...]:
    """Name every rule an import run's declared range breaks, or none.

    bronze-layer.md "Covers from and covers through": both ends are inclusive
    and declared, and nothing here falls back, clamps, or corrects them. The
    transaction dates are the parser's span over every record; both are `None`
    when the payload has no records, whether it states no transactions or
    Bronze could not read it. The codes come back in the order that document
    lists them; the range is refused exactly when any code does.
    """
    broken = (
        (RANGE_STARTS_AFTER_END, covers_from > covers_through),
        (RANGE_ENDS_AFTER_EXPORT, covers_through > exported_on),
        (
            TRANSACTION_BEFORE_RANGE,
            first_transaction_date is not None and first_transaction_date < covers_from,
        ),
        (
            TRANSACTION_AFTER_RANGE,
            last_transaction_date is not None
            and last_transaction_date > covers_through,
        ),
    )
    return tuple(code for code, is_broken in broken if is_broken)
