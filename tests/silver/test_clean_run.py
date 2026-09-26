# Copyright 2026 Therkel
"""One clean `danske-csv-v1` import run through the Silver build (#90).

Issue #5's scenarios 1, 4 (within one export) and 11, and the data map's
Date, Decimal, Booking status, Identity text and Label rules for valid input.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from budget.silver import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
)
from tests.silver.exports import ACCOUNT, build_from, export, identity, row

MARCH_1 = date(2026, 3, 1)
MARCH_2 = date(2026, 3, 2)
MARCH_3 = date(2026, 3, 3)
MARCH_4 = date(2026, 3, 4)

# Opening balance 1000,00. Two identical coffees on 2 March with a deleted third
# between them, whitespace-padded texts and labels, and a label that is blank.
CLEAN = export(
    [
        row("01.03.2026", "NETTO", "-45,0", "955,00"),
        row("02.03.2026", "KAFFE", "-30,00", "925,00", Kategori=" Fritid "),
        row("02.03.2026", "KAFFE", "-30,00", "", Status="Slettet"),
        row("02.03.2026", "KAFFE", "-30,00", "895,00", Kategori=" Fritid "),
        row(
            "03.03.2026",
            "\xa0LØN  MARTS\xa0",
            "1.234,56",
            "2.129,56",
            Kategori=" Indkomst ",
            Underkategori="\xa0 Løn \xa0",
        ),
        row(
            "04.03.2026",
            " MOBILEPAY  TIL\tANNA ",
            "-9,50",
            "2.120,06",
            Kategori="   ",
            Underkategori="",
        ),
    ],
    exported_on=date(2026, 3, 5),
    covers_through=MARCH_4,
)
PAYLOAD = CLEAN.run.payload_id
RUN = CLEAN.run.import_run_id


def _transaction(
    transaction_date: date,
    amount: str,
    description: str,
    balance: str,
    labels: tuple[str | None, str | None],
) -> Transaction:
    """The expected first occurrence, first in its day; `replace` adjusts both."""
    return Transaction(
        transaction_id=identity(transaction_date, amount, description, 1),
        account_id=ACCOUNT,
        transaction_date=transaction_date,
        amount=Decimal(amount),
        currency="DKK",
        description=description,
        source_system="danske-csv-v1",
        balance=Decimal(balance),
        source_status="Udført",
        booking_status="booked",
        occurrence=1,
        day_sequence=1,
        identity_version="1",
        bank_category=labels[0],
        bank_subcategory=labels[1],
    )


def test_each_booked_row_becomes_one_transaction() -> None:
    result = build_from(CLEAN)

    assert result.transactions == (
        _transaction(MARCH_1, "-45.00", "NETTO", "955.00", ("Mad", "Dagligvarer")),
        _transaction(MARCH_2, "-30.00", "KAFFE", "925.00", ("Fritid", "Dagligvarer")),
        replace(
            _transaction(
                MARCH_2, "-30.00", "KAFFE", "895.00", ("Fritid", "Dagligvarer")
            ),
            transaction_id=identity(MARCH_2, "-30.00", "KAFFE", 2),
            occurrence=2,
            day_sequence=2,
        ),
        _transaction(MARCH_3, "1234.56", "LØN MARTS", "2129.56", ("Indkomst", "Løn")),
        _transaction(MARCH_4, "-9.50", "MOBILEPAY TIL ANNA", "2120.06", (None, None)),
    )


def test_identity_is_pinned_to_the_documented_hash() -> None:
    # SHA-256 of ["1","joint-current","2026-03-01","-45.00","NETTO",1]. Changing
    # it needs a new identity version (ADR-009), so the digest is a literal.
    result = build_from(CLEAN)

    assert result.transactions[0].transaction_id == (
        "641b439adca6e82100ed1db661624eb347a2f5ade07b986b81d240779ea811ec"
    )


def test_identical_coffees_are_two_transactions_with_different_identifiers() -> None:
    coffees = [t for t in build_from(CLEAN).transactions if t.description == "KAFFE"]

    assert [t.occurrence for t in coffees] == [1, 2]
    assert coffees[0].transaction_id != coffees[1].transaction_id


def test_every_booked_record_is_evidence_for_its_transaction() -> None:
    result = build_from(CLEAN)

    assert result.transaction_evidence == tuple(
        TransactionEvidence(
            transaction_id=transaction.transaction_id,
            payload_id=PAYLOAD,
            record_ordinal=ordinal,
            import_run_id=RUN,
        )
        for transaction, ordinal in zip(
            result.transactions, (1, 2, 4, 5, 6), strict=True
        )
    )


def test_a_deleted_row_is_an_unbooked_record_and_not_a_transaction() -> None:
    result = build_from(CLEAN)

    assert result.unbooked_records == (
        UnbookedRecord(
            payload_id=PAYLOAD,
            record_ordinal=3,
            import_run_id=RUN,
            account_id=ACCOUNT,
            transaction_date=MARCH_2,
            amount=Decimal("-30.00"),
            source_status="Slettet",
            booking_status="cancelled",
        ),
    )


def test_each_date_with_a_booked_row_states_its_last_balance() -> None:
    result = build_from(CLEAN)

    assert result.balance_observations == tuple(
        BalanceObservation(
            account_id=ACCOUNT,
            balance_date=balance_date,
            end_of_day_balance=Decimal(balance),
            payload_id=PAYLOAD,
        )
        for balance_date, balance in (
            (MARCH_1, "955.00"),
            (MARCH_2, "895.00"),
            (MARCH_3, "2129.56"),
            (MARCH_4, "2120.06"),
        )
    )


def test_a_clean_run_is_accepted_with_the_dates_it_covers() -> None:
    result = build_from(CLEAN)

    assert result.import_run_results == (
        ImportRunResult(
            import_run_id=RUN,
            status="accepted",
            covered_from=MARCH_1,
            covered_to=MARCH_4,
            errors=(),
            review_item_ids=(),
        ),
    )
    assert result.review_items == ()


def test_covered_from_counts_unbooked_rows() -> None:
    deleted_first = export(
        [
            row("28.02.2026", "BIO", "-100,00", "", Status="Slettet"),
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
        ]
    )

    [result] = build_from(deleted_first).import_run_results

    assert result.covered_from == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("exported_on", "covers_through", "evidence_through"),
    [
        # An export whose range ended earlier proves its whole range.
        (date(2026, 3, 10), date(2026, 3, 6), date(2026, 3, 6)),
        # An export reaching its own production day proves nothing about it.
        (date(2026, 3, 10), date(2026, 3, 10), date(2026, 3, 9)),
    ],
)
def test_evidence_through_follows_the_per_run_formula(
    exported_on: date, covers_through: date, evidence_through: date
) -> None:
    run = export(
        [row("01.03.2026", "NETTO", "-45,00", "955,00")],
        exported_on=exported_on,
        covers_through=covers_through,
    )

    assert build_from(run).account_evidence == (
        AccountEvidence(account_id=ACCOUNT, evidence_through=evidence_through),
    )


@pytest.mark.parametrize(
    ("belob", "amount"),
    [
        ("-45,0", "-45.00"),
        ("-45,00", "-45.00"),
        ("12", "12.00"),
        ("-0,05", "-0.05"),
        ("1.234.567,5", "1234567.50"),
    ],
)
def test_amounts_carry_exactly_the_currency_places(belob: str, amount: str) -> None:
    run = export([row("01.03.2026", "NETTO", belob, "1.000,00")])

    [transaction] = build_from(run).transactions

    assert transaction.amount == Decimal(amount)
    assert str(transaction.amount) == amount
