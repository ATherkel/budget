# Copyright 2026 Therkel
"""Silver is the same whether exports arrive month by month or all at once.

Production's Bronze grows one month at a time, over many `budget import`
runs; a development reset imports every export in one. `silver-layer.md`
promises both end in the same Silver: it is a function of the set of import
runs, admitted in `exported_on` order. These tests import one household's
exports both ways and compare the two persisted results.

Identifiers that depend on when a run started, `import_run_id` and the review
item ids hashed from it, are compared by the run they belong to: its account
and filename. Every account, date, text and amount is synthetic.
"""

import unittest
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date
from decimal import Decimal
from itertools import zip_longest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore
from budget.profiles import Profile
from budget.silver import ReviewItem, SilverResult, SilverStore
from tests.cli.commands import import_, migrate
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import drop

EXIT_OK = 0
_HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'
_STATUS = {"booked": "Udført", "pending": "Venter", "cancelled": "Slettet"}


@dataclass(frozen=True)
class _Row:
    """One row of an account's history, as every export of it shows it."""

    day: date
    text: str
    amount: Decimal
    status: str = "booked"
    # The bank-stated balance after the row; only a booked row states one.
    balance: Decimal | None = None


def _history(opening: str, *rows: _Row) -> tuple[_Row, ...]:
    """Give each booked row the balance that follows from `opening`."""
    balance = Decimal(opening)
    stated = []
    for each in rows:
        if each.status == "booked":
            balance += each.amount
            stated.append(replace(each, balance=balance))
        else:
            stated.append(each)
    return tuple(stated)


def _row(day: str, text: str, amount: str, status: str = "booked") -> _Row:
    """One row: an ISO date, a text, an amount with a decimal point."""
    return _Row(date.fromisoformat(day), text, Decimal(amount), status)


def _danish(value: Decimal | None) -> str:
    """A Danske decimal: two places and a decimal comma; empty for none."""
    return "" if value is None else f"{value:.2f}".replace(".", ",")


def _csv(rows: Iterable[_Row]) -> bytes:
    """A `danske-csv-v1` export holding `rows`, oldest first."""
    lines = [
        f'"{each.day:%d.%m.%Y}"," Mad "," Dagligvarer ","{each.text}",'
        f'"{_danish(each.amount)}","{_danish(each.balance)}",'
        f'"{_STATUS[each.status]}","Nej"'
        for each in rows
    ]
    return "\r\n".join([_HEADER, *lines]).encode("cp1252")


def _between(rows: Iterable[_Row], first: str, last: str) -> list[_Row]:
    """The rows dated from `first` through `last`, ISO dates."""
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [each for each in rows if start <= each.day <= end]


@dataclass(frozen=True)
class _Export:
    """One export file, the range declared for it, and the batch it arrives in."""

    batch: int
    account_id: str
    name: str
    content: bytes
    covers_from: str
    covers_through: str


def _exports() -> tuple[_Export, ...]:
    """Three months of exports for two accounts.

    `joint-current`'s January export shows a purchase on 31 January as
    pending; February's export, which overlaps January, shows it booked, and
    shows a cancelled row. April's batch brings January's export again, byte
    for byte. `joint-savings`'s February export breaks its own balance chain,
    so Silver quarantines it.
    """
    current = _history(
        "10000.00",
        _row("2026-01-05", "Supermarket", "-450.00"),
        _row("2026-01-12", "Salary", "20000.00"),
        _row("2026-01-20", "Café", "-45.00"),
        _row("2026-01-25", "Café", "-45.00"),
        _row("2026-01-31", "Bookshop", "-199.00"),
        _row("2026-02-03", "Pharmacy", "-120.00"),
        _row("2026-02-10", "Cinema", "-150.00", status="cancelled"),
        _row("2026-02-15", "Supermarket", "-600.00"),
        _row("2026-03-02", "Salary", "20000.00"),
        _row("2026-03-14", "Café", "-45.00"),
    )
    *january, bookshop = _between(current, "2026-01-01", "2026-01-31")
    pending = replace(bookshop, status="pending", balance=None)
    january_current = _csv([*january, pending])
    savings = _history(
        "50000.00",
        _row("2026-01-15", "Transfer", "1000.00"),
        _row("2026-01-28", "Interest", "12.50"),
        _row("2026-02-15", "Transfer", "1000.00"),
        _row("2026-02-20", "Fee", "-10.00"),
        _row("2026-03-15", "Transfer", "1000.00"),
    )
    transfer, fee = _between(savings, "2026-02-01", "2026-02-28")
    # The fee's stated balance does not follow the transfer's.
    broken = replace(fee, balance=Decimal("99999.00"))
    return (
        _Export(
            1,
            "joint-current",
            "danske-20260201.csv",
            january_current,
            "2026-01-01",
            "2026-01-31",
        ),
        _Export(
            1,
            "joint-savings",
            "danske-20260201.csv",
            _csv(_between(savings, "2026-01-01", "2026-01-31")),
            "2026-01-01",
            "2026-01-31",
        ),
        _Export(
            2,
            "joint-current",
            "danske-20260301.csv",
            _csv(_between(current, "2026-01-20", "2026-02-28")),
            "2026-01-20",
            "2026-02-28",
        ),
        _Export(
            2,
            "joint-savings",
            "danske-20260301.csv",
            _csv([transfer, broken]),
            "2026-02-01",
            "2026-02-28",
        ),
        _Export(
            3,
            "joint-current",
            "danske-20260401.csv",
            _csv(_between(current, "2026-03-01", "2026-03-31")),
            "2026-03-01",
            "2026-03-31",
        ),
        # A day after March's export: runs sharing an export date are
        # admitted in import order, which the two paths need not share.
        _Export(
            3,
            "joint-current",
            "danske-20260402.csv",
            january_current,
            "2026-01-01",
            "2026-01-31",
        ),
        _Export(
            3,
            "joint-savings",
            "danske-20260401.csv",
            _csv(_between(savings, "2026-03-01", "2026-03-31")),
            "2026-03-01",
            "2026-03-31",
        ),
    )


def _household(folder: Path) -> tuple[Path, Profile]:
    """A migrated development profile with the synthetic `accounts.toml`."""
    folder.mkdir()
    profile_file = write_profile(folder)
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    write_inputs(profile)
    return profile_file, profile


def _import(profile_file: Path, profile: Profile, exports: Sequence[_Export]) -> None:
    """Drop `exports` into the inbox, then import them all in one command.

    The range of each file is typed at the prompt, in the order the inbox
    lists them, so each file keeps its own range.
    """
    for each in exports:
        drop(profile, each.account_id, each.name, each.content)
    listed = sorted(exports, key=lambda each: (each.account_id, each.name))
    typed = "".join(f"{each.covers_from}\n{each.covers_through}\n" for each in listed)
    status, _, stderr = import_(profile_file, typed=typed + "y\n")
    assert (status, stderr) == (EXIT_OK, "")
    # Answers out of step with the listing import nothing, yet exit 0.
    assert not any(path.is_file() for path in profile.inbox.rglob("*"))


def _run_names(profile: Profile) -> dict[str, str]:
    """Name each import run by its account and filename, not its id."""
    with BronzeStore(profile) as store:
        return {
            run.import_run_id: f"{run.declared_account_id}/{run.original_filename}"
            for run in store.import_runs()
        }


def _item_name(item: ReviewItem, run: str) -> str:
    """Name a review item by its kind, its run's name and its transaction."""
    named = f"{item.kind} of {run}"
    return (
        named if item.transaction_id is None else f"{named} for {item.transaction_id}"
    )


def _comparable(result: SilverResult, runs: Mapping[str, str]) -> SilverResult:
    """`result` with every run-dependent id replaced by its run's name.

    Silver orders runs and review items by id, so they are reordered by name.
    """
    by_id = {item.review_item_id: item for item in result.review_items}
    items = {
        item_id: _item_name(by_id[item_id], runs[run.import_run_id])
        for run in result.import_run_results
        for item_id in run.review_item_ids
    }
    named_runs = (
        replace(
            each,
            import_run_id=runs[each.import_run_id],
            errors=tuple(each.errors),
            review_item_ids=tuple(items[i] for i in each.review_item_ids),
        )
        for each in result.import_run_results
    )
    named_items = (
        replace(
            each,
            review_item_id=items[each.review_item_id],
            payload_ids=tuple(each.payload_ids),
        )
        for each in result.review_items
    )
    return SilverResult(
        transactions=tuple(result.transactions),
        transaction_evidence=tuple(
            replace(each, import_run_id=runs[each.import_run_id])
            for each in result.transaction_evidence
        ),
        unbooked_records=tuple(
            replace(each, import_run_id=runs[each.import_run_id])
            for each in result.unbooked_records
        ),
        balance_observations=tuple(result.balance_observations),
        account_evidence=tuple(result.account_evidence),
        evidence_exports=tuple(
            replace(each, import_run_id=runs[each.import_run_id])
            for each in result.evidence_exports
        ),
        import_run_results=sorted(named_runs, key=lambda run: run.import_run_id),
        review_items=sorted(named_items, key=lambda item: item.review_item_id),
    )


def _silver(profile: Profile) -> SilverResult:
    """The profile's persisted Silver, comparable across profiles."""
    with SilverStore(profile) as store:
        result = store.read()
    return _comparable(result, _run_names(profile))


class SilversDifferError(AssertionError):
    """Two Silvers that should be equal differ; the message names where."""


def _first_difference(monthly: SilverResult, at_once: SilverResult) -> str:
    """Name the first row the two Silvers disagree on; empty when they agree."""
    for table in (field.name for field in fields(SilverResult)):
        pairs = zip_longest(getattr(monthly, table), getattr(at_once, table))
        for position, (left, right) in enumerate(pairs, start=1):
            if left != right:
                return (
                    f"{table} row {position}: month by month {left!r}, "
                    f"all at once {right!r}"
                )
    return ""


def _monthly(
    folder: Path, exports: Sequence[_Export], *, newest_first: bool = False
) -> Profile:
    """A household that imports `exports` one batch at a time.

    The batches arrive oldest first, as in production, or newest first.
    """
    profile_file, profile = _household(folder)
    for batch in sorted({each.batch for each in exports}, reverse=newest_first):
        _import(profile_file, profile, [e for e in exports if e.batch == batch])
    return profile


def _at_once(folder: Path, exports: Sequence[_Export]) -> Profile:
    """A household that imports every one of `exports` in one command."""
    profile_file, profile = _household(folder)
    _import(profile_file, profile, exports)
    return profile


class ImportEquivalenceTests(unittest.TestCase):
    def test_monthly_imports_end_in_the_silver_one_import_builds(self) -> None:
        exports = _exports()
        with TemporaryDirectory() as directory:
            monthly = _monthly(Path(directory) / "monthly", exports)
            at_once = _at_once(Path(directory) / "at-once", exports)

            difference = _first_difference(_silver(monthly), _silver(at_once))

        assert not difference, difference

    # Only the Silvers' difference is expected: a failure while importing
    # still fails the test.
    @pytest.mark.xfail(
        raises=SilversDifferError,
        strict=True,
        reason="#282: Bronze stores whichever copy of a repeated export arrives "
        "first, and Silver admits the payload at that copy's date",
    )
    def test_months_imported_newest_first_end_in_the_same_silver(self) -> None:
        exports = _exports()
        with TemporaryDirectory() as directory:
            monthly = _monthly(Path(directory) / "monthly", exports)
            newest_first = _monthly(
                Path(directory) / "newest-first", exports, newest_first=True
            )

            difference = _first_difference(_silver(monthly), _silver(newest_first))

        if difference:
            raise SilversDifferError(difference)

    def test_the_exports_hold_every_case_the_comparison_must_cover(self) -> None:
        with TemporaryDirectory() as directory:
            silver = _silver(_monthly(Path(directory) / "monthly", _exports()))

        statuses = {run.import_run_id: run.status for run in silver.import_run_results}
        # The overlapping February export is admitted; February's savings
        # export breaks its balance chain and is quarantined.
        assert statuses == {
            "joint-current/danske-20260201.csv": "accepted",
            "joint-current/danske-20260301.csv": "accepted",
            "joint-current/danske-20260401.csv": "accepted",
            "joint-savings/danske-20260201.csv": "accepted",
            "joint-savings/danske-20260301.csv": "quarantined",
            "joint-savings/danske-20260401.csv": "accepted",
        }
        [item] = silver.review_items
        assert item.review_item_id == (
            "balance-break of joint-savings/danske-20260301.csv"
        )
        # The repeat of January's export counts in the account's evidence.
        assert "joint-current/danske-20260402.csv" in {
            each.import_run_id for each in silver.evidence_exports
        }
        unbooked = {
            (each.transaction_date, each.booking_status)
            for each in silver.unbooked_records
        }
        assert unbooked == {
            (date(2026, 1, 31), "pending"),
            (date(2026, 2, 10), "cancelled"),
        }
        # The purchase pending in January is booked by February's export.
        booked = {
            (each.transaction_date, each.description) for each in silver.transactions
        }
        assert (date(2026, 1, 31), "Bookshop") in booked
