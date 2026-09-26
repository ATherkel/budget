# Copyright 2026 Therkel
"""Synthetic `danske-csv-v1` exports as Bronze presents them to Silver.

Every account, date, text and amount here is invented. A test describes an
export as rows of source fields, exactly as Bronze would decode them, and runs
Silver over one or more such exports through `budget.silver.build`.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver import SilverDecision, SilverResult, build

ACCOUNT = "joint-current"
FORMAT = "danske-csv-v1"


def row(
    dato: str, tekst: str, belob: str, saldo: str, **overrides: str
) -> dict[str, str]:
    """One `danske-csv-v1` row, with every field as Bronze decodes it.

    `overrides` replaces other fields by their source name, such as
    `Status="Slettet"` or `Kategori=" Bolig "`.
    """
    fields = {
        "Dato": dato,
        "Kategori": " Mad ",
        "Underkategori": " Dagligvarer ",
        "Tekst": tekst,
        "Beløb": belob,
        "Saldo": saldo,
        "Status": "Udført",
        "Afstemt": "Nej",
    }
    return fields | overrides


@dataclass(frozen=True)
class Export:
    """One stored import run and what Bronze derived from its payload."""

    run: ImportRun
    records: tuple[SourceRecord, ...]
    failures: tuple[FormatFailure, ...] = ()


def export(
    rows: list[dict[str, str]],
    *,
    run_id: str = "run-0001",
    exported_on: date = date(2026, 3, 5),
    covers_through: date | None = None,
) -> Export:
    """Present `rows` as the payload of one stored import run."""
    payload_id = f"payload-{run_id}"
    run = ImportRun(
        import_run_id=run_id,
        payload_id=payload_id,
        declared_account_id=ACCOUNT,
        source_format=FORMAT,
        original_filename=f"export-{exported_on:%Y%m%d}.csv",
        exported_on=exported_on,
        exported_on_source="filename",
        covers_through=covers_through or exported_on,
        covers_through_source="exported_on" if covers_through is None else "declared",
        started_at=datetime.combine(exported_on, datetime.min.time(), UTC),
        outcome="stored",
        repeat_of=None,
    )
    records = tuple(
        SourceRecord(payload_id=payload_id, record_ordinal=ordinal, fields=fields)
        for ordinal, fields in enumerate(rows, start=1)
    )
    return Export(run=run, records=records)


def build_from(
    *exports: Export, decisions: Sequence[SilverDecision] = ()
) -> SilverResult:
    """Run Silver over `exports`, for one DKK account."""
    return build(
        runs=[each.run for each in exports],
        source_records={each.run.payload_id: each.records for each in exports},
        format_failures={each.run.payload_id: each.failures for each in exports},
        currencies={ACCOUNT: "DKK"},
        decisions=decisions,
    )


def _hash(inputs: list[str | int]) -> str:
    written = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(written.encode()).hexdigest()


def review_item_id(kind: str, import_run_id: str) -> str:
    """The `review_item_id` `silver-layer.md` defines for a run's item."""
    return _hash([kind, import_run_id])


def identity(
    transaction_date: date, amount: str, description: str, occurrence: int
) -> str:
    """The `transaction_id` `silver-layer.md` defines, for this module's account."""
    return _hash(
        ["1", ACCOUNT, transaction_date.isoformat(), amount, description, occurrence]
    )
