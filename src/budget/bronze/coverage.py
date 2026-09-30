# Copyright 2026 Therkel
"""Bank-independent safeguards for a declared covered range.

Nothing in this module knows a source format. It decides whether one import
run's declared range, from `covers_from` through `covers_through`, is one the
payload and its export date allow, whatever produced the payload.
"""

from datetime import date


def declared_range_refused(
    *,
    covers_from: date,
    covers_through: date,
    exported_on: date,
    first_transaction_date: date | None,
    last_transaction_date: date | None,
) -> bool:
    """Say whether an import run's declared range must be refused.

    bronze-layer.md "Covers from and covers through": both ends are inclusive
    and declared, and nothing here falls back, clamps, or corrects them. The
    transaction dates are the parser's span over every record; both are `None`
    when the payload has no records, whether it states no transactions or
    Bronze could not read it.
    """
    starts_after_it_ends = covers_from > covers_through
    ends_after_export = covers_through > exported_on
    transaction_before_range = (
        first_transaction_date is not None and first_transaction_date < covers_from
    )
    transaction_after_range = (
        last_transaction_date is not None and last_transaction_date > covers_through
    )
    return (
        starts_after_it_ends
        or ends_after_export
        or transaction_before_range
        or transaction_after_range
    )
