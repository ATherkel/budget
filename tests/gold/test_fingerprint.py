# Copyright 2026 Therkel
"""The result fingerprint covers every record a publication returns.

`publications.md` (*The Recipe*): a SHA-256 over a canonical serialization of
every record through `GoldRepository` and `GoldLineageRepository`, where the
publication's own metadata takes no part. Every record here is the Gold build's
own over the synthetic worked example.
"""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from budget.gold import (
    ClassificationReviewItem,
    GoldLineageRecords,
    GoldRecords,
    GoldResult,
)
from budget.gold.fingerprint import result_fingerprint
from tests.gold.worked_silver import build_from


def _with(
    result: GoldResult,
    *,
    records: GoldRecords | None = None,
    lineage: GoldLineageRecords | None = None,
) -> GoldResult:
    """The same publication with some of its records or lineage replaced."""
    return GoldResult(
        result.publication(),
        result.records if records is None else records,
        result.lineage if lineage is None else lineage,
    )


def _with_amount(result: GoldResult, amount: Decimal) -> GoldResult:
    """The result with its first transaction carrying `amount`."""
    first, *rest = result.records.transactions
    changed = replace(
        result.records, transactions=[replace(first, amount=amount), *rest]
    )
    return _with(result, records=changed)


def test_the_publications_own_metadata_is_not_part_of_the_fingerprint() -> None:
    result = build_from()
    later = replace(
        result.publication(),
        publication_id=9,
        built_at=datetime(2030, 1, 1, tzinfo=UTC),
        known_at=datetime(2030, 1, 1, tzinfo=UTC),
        result_fingerprint="f" * 64,
    )

    assert result_fingerprint(GoldResult(later, result.records, result.lineage)) == (
        result_fingerprint(result)
    )


def test_a_change_to_one_fact_changes_the_fingerprint() -> None:
    result = build_from()
    first = result.records.transactions[0]

    changed = _with_amount(result, first.amount + Decimal("0.01"))

    assert result_fingerprint(changed) != result_fingerprint(result)


def test_a_change_to_lineage_alone_changes_the_fingerprint() -> None:
    result = build_from()
    first, *rest = result.lineage.transaction_lineage

    changed = _with(
        result,
        lineage=replace(
            result.lineage,
            transaction_lineage=[replace(first, rule_ids=("r-another",)), *rest],
        ),
    )

    assert result_fingerprint(changed) != result_fingerprint(result)


def test_a_review_item_alone_changes_the_fingerprint() -> None:
    result = build_from()
    item = ClassificationReviewItem(
        review_item_id="review-1",
        kind="rule-conflict",
        transaction_ids=(result.records.transactions[0].transaction_id,),
        rule_ids=("r-a", "r-b"),
        decision_id=None,
        reason=None,
    )

    changed = _with(
        result,
        lineage=replace(result.lineage, classification_review_items=[item]),
    )

    assert result_fingerprint(changed) != result_fingerprint(result)


def test_an_amount_has_one_fingerprint_whatever_its_scale() -> None:
    result = build_from()

    assert result_fingerprint(_with_amount(result, Decimal("-45.0"))) == (
        result_fingerprint(_with_amount(result, Decimal("-45.00")))
    )
    assert result_fingerprint(_with_amount(result, Decimal("0.00"))) == (
        result_fingerprint(_with_amount(result, Decimal("-0")))
    )


def test_amounts_that_differ_beyond_28_digits_stay_different() -> None:
    result = build_from()

    one = _with_amount(result, Decimal("12345678901234567890123456789.1"))
    other = _with_amount(result, Decimal("12345678901234567890123456789.2"))

    assert result_fingerprint(one) != result_fingerprint(other)


def test_a_value_with_no_canonical_form_is_refused() -> None:
    result = build_from()
    first, *rest = result.records.transactions
    unserialisable = replace(first, description=cast("Any", object()))
    records = replace(result.records, transactions=[unserialisable, *rest])

    with pytest.raises(TypeError, match="no canonical form"):
        result_fingerprint(_with(result, records=records))
