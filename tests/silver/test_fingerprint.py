# Copyright 2026 Therkel
"""The versioned fingerprint of every public Silver result record."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.silver import (
    AccountEvidence,
    BalanceObservation,
    EvidenceExport,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
    ValidationError,
    result_fingerprint,
)


def _every_record() -> SilverResult:
    """One synthetic record of every public family Silver returns."""
    return SilverResult(
        transactions=(
            Transaction(
                transaction_id="t1",
                account_id="joint-current",
                transaction_date=date(2026, 3, 1),
                amount=Decimal("12.30"),
                currency="DKK",
                description="SHOP",
                source_system="csv",
                balance=Decimal("100.30"),
                source_status="BOOKED",
                booking_status="booked",
                occurrence=2,
                day_sequence=3,
                identity_version="1",
                bank_category="Food",
                bank_subcategory="Groceries",
            ),
        ),
        transaction_evidence=(
            TransactionEvidence(
                transaction_id="t1",
                payload_id="payload-a",
                record_ordinal=7,
                import_run_id="run-a",
            ),
        ),
        unbooked_records=(
            UnbookedRecord(
                payload_id="payload-a",
                record_ordinal=8,
                import_run_id="run-a",
                account_id="joint-current",
                transaction_date=date(2026, 3, 2),
                amount=Decimal("-1.20"),
                source_status="Pending",
                booking_status="pending",
            ),
        ),
        balance_observations=(
            BalanceObservation(
                account_id="joint-current",
                balance_date=date(2026, 3, 1),
                end_of_day_balance=Decimal("100.30"),
                payload_id="payload-a",
            ),
        ),
        account_evidence=(
            AccountEvidence(
                account_id="joint-current",
                covers_from=date(2026, 3, 1),
                covers_through=date(2026, 3, 31),
            ),
        ),
        evidence_exports=(
            EvidenceExport(
                import_run_id="run-a",
                payload_id="payload-a",
                account_id="joint-current",
                exported_on=date(2026, 4, 2),
                covers_from=date(2026, 3, 1),
                covers_through=date(2026, 3, 31),
            ),
        ),
        import_run_results=(
            ImportRunResult(
                import_run_id="run-a",
                payload_id="payload-a",
                account_id="joint-current",
                status="quarantined",
                covered_from=date(2026, 3, 1),
                covered_to=date(2026, 3, 31),
                errors=(
                    ValidationError(
                        payload_id="payload-a",
                        record_ordinal=7,
                        code="balance-chain-break",
                        message="synthetic break",
                    ),
                ),
                review_item_ids=("review-b", "review-a"),
            ),
        ),
        review_items=(
            ReviewItem(
                review_item_id="review-a",
                kind="balance-break",
                account_id="joint-current",
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
                payload_ids=("payload-b", "payload-a"),
                resolved_by=None,
            ),
        ),
    )


def test_the_silver_fingerprint_is_a_versioned_hash_of_every_public_record() -> None:
    fingerprint = result_fingerprint(
        _every_record(),
        currencies={"joint-savings": "EUR", "joint-current": "DKK"},
    )

    assert fingerprint == (
        "6bd2f02b87c4cc09447b8479ca5b535e17fcd8a025ece2cc24e9db6f0a9b57ab"
    )


def test_incidental_order_and_decimal_scale_do_not_change_the_fingerprint() -> None:
    base = _every_record()
    first = base.transactions[0]
    second = replace(
        first,
        transaction_id="t2",
        description="OTHER",
        amount=Decimal("1.20"),
    )
    ordered = replace(base, transactions=(first, second))
    reordered = replace(
        base,
        transactions=(
            replace(second, amount=Decimal("1.200")),
            replace(first, amount=Decimal("12.300")),
        ),
        import_run_results=tuple(
            replace(
                run,
                review_item_ids=tuple(reversed(run.review_item_ids)),
            )
            for run in base.import_run_results
        ),
        review_items=tuple(
            replace(item, payload_ids=tuple(reversed(item.payload_ids)))
            for item in base.review_items
        ),
    )
    currencies = {"joint-savings": "EUR", "joint-current": "DKK"}
    reversed_currencies = dict(reversed(tuple(currencies.items())))

    assert result_fingerprint(ordered, currencies=currencies) == result_fingerprint(
        reordered, currencies=reversed_currencies
    )


def test_duplicate_records_are_preserved_by_the_fingerprint() -> None:
    base = _every_record()
    duplicated = replace(
        base,
        transactions=(*base.transactions, *base.transactions),
    )
    currencies = {"joint-current": "DKK"}

    assert result_fingerprint(base, currencies=currencies) != result_fingerprint(
        duplicated, currencies=currencies
    )
