# Copyright 2026 Therkel
"""The versioned fingerprint of one stored Silver result."""

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Final

from budget.inputs.snapshot import canonical_amount
from budget.silver.models import (
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
)

SILVER_FINGERPRINT_SCHEME: Final = "1"
type SilverRecord = (
    AccountEvidence
    | BalanceObservation
    | EvidenceExport
    | ImportRunResult
    | ReviewItem
    | Transaction
    | TransactionEvidence
    | UnbookedRecord
    | ValidationError
)


def result_fingerprint(result: SilverResult, *, currencies: Mapping[str, str]) -> str:
    """Return the result and currency snapshot's lowercase hexadecimal hash."""
    document = {
        "scheme": SILVER_FINGERPRINT_SCHEME,
        "currencies": _currencies(currencies),
        "transactions": _rows(result.transactions),
        "transaction_evidence": _rows(result.transaction_evidence),
        "unbooked_records": _rows(result.unbooked_records),
        "balance_observations": _rows(result.balance_observations),
        "account_evidence": _rows(result.account_evidence),
        "evidence_exports": _rows(result.evidence_exports),
        "import_run_results": _import_runs(result),
        "review_items": _review_items(result),
    }
    text = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _currencies(currencies: Mapping[str, str]) -> list[dict[str, str]]:
    """Write the currency snapshot in account order."""
    return [
        {"account_id": account_id, "currency": currency}
        for account_id, currency in sorted(currencies.items())
    ]


def _rows(records: Sequence[SilverRecord]) -> list[dict[str, object]]:
    """Write records in canonical order, keeping every duplicate."""
    return _sorted_documents(_document(each) for each in records)


def _import_runs(result: SilverResult) -> list[dict[str, object]]:
    """Write run results with their unordered nested identifier lists canonical."""
    documents = []
    for run in result.import_run_results:
        document = _document(run)
        document["errors"] = _sorted_documents(_document(each) for each in run.errors)
        document["review_item_ids"] = sorted(run.review_item_ids)
        documents.append(document)
    return _sorted_documents(documents)


def _review_items(result: SilverResult) -> list[dict[str, object]]:
    """Write review items with their unordered payload lists canonical."""
    documents = []
    for item in result.review_items:
        document = _document(item)
        document["payload_ids"] = sorted(item.payload_ids)
        documents.append(document)
    return _sorted_documents(documents)


def _document(record: SilverRecord) -> dict[str, object]:
    """Turn one dataclass into a canonical JSON-compatible document."""
    if isinstance(
        record,
        Transaction | TransactionEvidence | UnbookedRecord | BalanceObservation,
    ):
        return _transaction_document(record)
    return _supporting_document(record)


def _transaction_document(
    record: Transaction | TransactionEvidence | UnbookedRecord | BalanceObservation,
) -> dict[str, object]:
    """Encode one transaction-family record."""
    match record:
        case Transaction():
            return {
                "transaction_id": record.transaction_id,
                "account_id": record.account_id,
                "transaction_date": record.transaction_date.isoformat(),
                "amount": canonical_amount(record.amount),
                "currency": record.currency,
                "description": record.description,
                "source_system": record.source_system,
                "balance": _optional_amount(record.balance),
                "source_status": record.source_status,
                "booking_status": record.booking_status,
                "occurrence": record.occurrence,
                "day_sequence": record.day_sequence,
                "identity_version": record.identity_version,
                "bank_category": record.bank_category,
                "bank_subcategory": record.bank_subcategory,
            }
        case TransactionEvidence():
            return {
                "transaction_id": record.transaction_id,
                "payload_id": record.payload_id,
                "record_ordinal": record.record_ordinal,
                "import_run_id": record.import_run_id,
            }
        case UnbookedRecord():
            return {
                "payload_id": record.payload_id,
                "record_ordinal": record.record_ordinal,
                "import_run_id": record.import_run_id,
                "account_id": record.account_id,
                "transaction_date": record.transaction_date.isoformat(),
                "amount": canonical_amount(record.amount),
                "source_status": record.source_status,
                "booking_status": record.booking_status,
            }
        case BalanceObservation():
            return {
                "account_id": record.account_id,
                "balance_date": record.balance_date.isoformat(),
                "end_of_day_balance": _optional_amount(record.end_of_day_balance),
                "payload_id": record.payload_id,
            }
        case _:
            message = f"no transaction-family form for {type(record).__name__}"
            raise TypeError(message)


def _supporting_document(
    record: (
        AccountEvidence
        | EvidenceExport
        | ImportRunResult
        | ReviewItem
        | ValidationError
    ),
) -> dict[str, object]:
    """Encode one lineage, run, review or validation record."""
    match record:
        case AccountEvidence():
            return {
                "account_id": record.account_id,
                "covers_from": record.covers_from.isoformat(),
                "covers_through": record.covers_through.isoformat(),
            }
        case EvidenceExport():
            return {
                "import_run_id": record.import_run_id,
                "payload_id": record.payload_id,
                "account_id": record.account_id,
                "exported_on": record.exported_on.isoformat(),
                "covers_from": record.covers_from.isoformat(),
                "covers_through": record.covers_through.isoformat(),
            }
        case ImportRunResult():
            return {
                "import_run_id": record.import_run_id,
                "payload_id": record.payload_id,
                "account_id": record.account_id,
                "status": record.status,
                "covered_from": record.covered_from.isoformat(),
                "covered_to": record.covered_to.isoformat(),
                "errors": [],
                "review_item_ids": [],
            }
        case ReviewItem():
            return {
                "review_item_id": record.review_item_id,
                "kind": record.kind,
                "account_id": record.account_id,
                "date_from": record.date_from.isoformat(),
                "date_to": record.date_to.isoformat(),
                "payload_ids": [],
                "resolved_by": record.resolved_by,
                "transaction_id": record.transaction_id,
            }
        case ValidationError():
            return {
                "payload_id": record.payload_id,
                "record_ordinal": record.record_ordinal,
                "code": record.code,
                "message": record.message,
            }
        case _:
            message = f"no canonical Silver record for {type(record).__name__}"
            raise TypeError(message)


def _sorted_documents(documents: Iterable[object]) -> list[dict[str, object]]:
    """Sort encoded records by their complete canonical text."""
    values = list(documents)
    if not all(isinstance(value, dict) for value in values):
        message = "a Silver record did not encode as an object"
        raise TypeError(message)
    objects = [value for value in values if isinstance(value, dict)]
    return sorted(objects, key=_sort_key)


def _sort_key(document: object) -> str:
    """Return a complete deterministic key for one encoded record."""
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _optional_amount(amount: Decimal | None) -> str | None:
    """Write an optional exact amount canonically."""
    return None if amount is None else canonical_amount(amount)
