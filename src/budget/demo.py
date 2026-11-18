# Copyright 2026 Therkel
"""An isolated synthetic dashboard profile for development and review."""

import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from budget.dashboard.passphrase import set_passphrase
from budget.gold import (
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
)
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.inputs import Account, ConfigurationSnapshot, Taxonomy
from budget.profiles import Profile, load_profile_file

DEMO_ACCESS_TEXT = "budget-demo"
DEFAULT_DEMO_PORT = 8765

# Every demo month on Demo current, booked on the 1st so the current month has
# them too: amount, text, type and category.
_MONTHLY_ENTRIES: tuple[tuple[str, str, TransactionType, str], ...] = (
    ("1700.00", "DEMO SALARY", "income", "salary"),
    ("-900.00", "DEMO SUPERMARKET", "expense", "groceries"),
    ("-650.00", "DEMO BAKERY", "expense", "groceries"),
    ("50.00", "DEMO SUPERMARKET REFUND", "refund", "groceries"),
)
_CATEGORIES = (
    GoldCategory("salary", "Salary", "income", "Income", "income"),
    GoldCategory("groceries", "Groceries", "food", "Food", "expense"),
)


class DemoDirectoryExistsError(ValueError):
    """The requested demo target already exists and will not be reused."""

    def __init__(self, directory: Path) -> None:
        """Name the existing path without suggesting it was modified."""
        super().__init__(
            f"the demo directory {directory} already exists; choose a new "
            "--directory or remove that isolated demo first"
        )


def _toml_path(path: Path) -> str:
    """Write an absolute path as a TOML basic string."""
    return json.dumps(path.as_posix(), ensure_ascii=False)


def _accounts() -> tuple[Account, ...]:
    """Return the two synthetic accounts shown by the demo dashboard."""
    return (
        Account(
            account_id="demo-current",
            display_name="Demo current",
            account_type="current",
            ownership_scope="household",
            currency="DKK",
            source_format="synthetic",
        ),
        Account(
            account_id="demo-savings",
            display_name="Demo savings",
            account_type="savings",
            ownership_scope="household",
            currency="DKK",
            source_format="synthetic",
        ),
    )


def _gold_records(accounts: tuple[Account, ...], today: date) -> GoldRecords:
    """Build a short, clearly synthetic reporting history through this month."""
    gold_accounts = tuple(
        GoldAccount(
            account_id=account.account_id,
            display_name=account.display_name,
            account_type=account.account_type,
            ownership_scope=account.ownership_scope,
            currency=account.currency,
            closed_on=None,
            coverage_start=date(today.year, 1, 1),
            evidence_through=today,
        )
        for account in accounts
    )
    months = range(1, today.month + 1)
    balances = tuple(
        MonthlyBalanceSnapshot(
            account_id=account.account_id,
            month=ReportingMonth(today.year, month),
            opening_balance=Decimal("1000.00"),
            closing_balance=Decimal("1200.00"),
            coverage="complete",
            late_bookings_settled=(month != today.month),
        )
        for account in gold_accounts
        for month in months
    )
    entries = [
        _entry(date(today.year, month, 1), month * 10 + sequence, entry)
        for month in months
        for sequence, entry in enumerate(_MONTHLY_ENTRIES)
    ]
    activity = tuple(
        transaction
        for month in months
        for transaction in _advanced_activity(today.year, month)
    )
    return GoldRecords(
        accounts=gold_accounts,
        monthly_balances=balances,
        categories=_CATEGORIES,
        transactions=(
            *(transaction for transaction, _ in entries),
            *activity,
        ),
        category_allocations=tuple(allocation for _, allocation in entries),
    )


def _entry(
    booked: date, sequence: int, entry: tuple[str, str, TransactionType, str]
) -> tuple[GoldTransaction, GoldCategoryAllocation]:
    """Return one demo transaction on Demo current and its single allocation."""
    amount, description, transaction_type, category_id = entry
    transaction = GoldTransaction(
        transaction_id=f"demo-{sequence}",
        account_id="demo-current",
        transaction_date=booked,
        account_sequence=sequence,
        amount=Decimal(amount),
        description=description,
        transaction_type=transaction_type,
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )
    allocation = GoldCategoryAllocation(
        allocation_id=f"{transaction.transaction_id}/{category_id}",
        transaction_id=transaction.transaction_id,
        account_id=transaction.account_id,
        transaction_date=booked,
        category_id=category_id,
        amount=transaction.amount,
    )
    return transaction, allocation


@dataclass(frozen=True)
class _AdvancedEntry:
    """One synthetic demo transaction that carries no Category allocation."""

    transaction_id: str
    account_id: str
    booked: date
    sequence: int
    amount: str
    description: str
    transaction_type: TransactionType
    transfer_group_id: str | None


def _advanced_activity(year: int, month: int) -> tuple[GoldTransaction, ...]:
    """Return the demo month's paired Transfer, Unclassified money and Adjustment."""
    booked = date(year, month, 1)
    group = f"demo-transfer-{year}-{month:02d}"
    base = month * 10
    return (
        _plain_transaction(
            _AdvancedEntry(
                f"demo-current-transfer-{month}",
                "demo-current",
                booked,
                base + 4,
                "-250.00",
                "DEMO TRANSFER OUT",
                "transfer",
                group,
            )
        ),
        _plain_transaction(
            _AdvancedEntry(
                f"demo-savings-transfer-{month}",
                "demo-savings",
                booked,
                base + 4,
                "250.00",
                "DEMO TRANSFER IN",
                "transfer",
                group,
            )
        ),
        _plain_transaction(
            _AdvancedEntry(
                f"demo-current-unknown-{month}",
                "demo-current",
                booked,
                base + 5,
                "-25.00",
                "DEMO UNCLASSIFIED",
                "unknown",
                None,
            )
        ),
        _plain_transaction(
            _AdvancedEntry(
                f"demo-current-adjustment-{month}",
                "demo-current",
                booked,
                base + 6,
                "100.00",
                "DEMO ADJUSTMENT",
                "adjustment",
                None,
            )
        ),
    )


def _plain_transaction(entry: _AdvancedEntry) -> GoldTransaction:
    """Return one synthetic transaction that carries no Category allocation."""
    return GoldTransaction(
        transaction_id=entry.transaction_id,
        account_id=entry.account_id,
        transaction_date=entry.booked,
        account_sequence=entry.sequence,
        amount=Decimal(entry.amount),
        description=entry.description,
        transaction_type=entry.transaction_type,
        transfer_group_id=entry.transfer_group_id,
        balance_after=None,
        balance_check="missing_balance",
    )


def _configuration(accounts: tuple[Account, ...]) -> ConfigurationSnapshot:
    """Return the matching synthetic account and empty-taxonomy snapshot."""
    return ConfigurationSnapshot(
        accounts={account.account_id: account for account in accounts},
        taxonomy=Taxonomy(groups={}, categories={}),
        rules={},
    )


def _publish(profile: Profile, accounts: tuple[Account, ...]) -> None:
    """Publish synthetic records as the first current publication."""
    now = datetime.now(UTC)
    configuration = _configuration(accounts)
    recipe = Recipe(
        import_runs=frozenset(
            {RecipeImportRun("synthetic-dashboard-demo", "a" * 64, "demo-current")}
        ),
        configuration_fingerprint=configuration.fingerprint,
        decision_log_position=0,
        decision_log_prefix_sha256="b" * 64,
        code_version=None,
        contract_version="0.2",
        silver_identity_version="1",
        late_booking_days=7,
        python_version=sys.version.split()[0],
        sqlite_version=sqlite3.sqlite_version,
        silver_fingerprint_scheme="1",
        silver_result_fingerprint="c" * 64,
        silver_code_version=None,
        silver_decision_log_position=0,
        silver_decision_log_prefix_sha256=sha256(b"").hexdigest(),
        silver_bronze_parser_provenance="unknown",
        silver_currencies=frozenset(
            (account.account_id, account.currency) for account in accounts
        ),
        silver_decisions=(),
    )
    publication = GoldPublication(
        publication_id=1,
        kind="pipeline",
        label="Synthetic dashboard demo",
        known_at=now,
        built_at=now,
        replayed_at=None,
        contract_version="0.2",
        fingerprint_scheme="synthetic-demo",
        result_fingerprint="0" * 64,
    )
    records = _gold_records(accounts, now.date())
    with GoldStore(profile) as store:
        store.publish(GoldResult(publication, records), recipe, configuration)


def create_demo_profile(directory: Path | None, *, port: int) -> Profile:
    """Create, populate and return a fresh isolated development profile."""
    if directory is None:
        root = Path(tempfile.mkdtemp(prefix="budget-demo-")).resolve()
    else:
        root = directory.expanduser().resolve()
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise DemoDirectoryExistsError(root) from None
    profile_file = root / "profile.toml"
    profile_file.write_text(
        "\n".join(
            (
                "format = 1",
                'profile = "development"',
                "",
                "[paths]",
                f"stores = {_toml_path(root / 'stores')}",
                f"inputs = {_toml_path(root / 'inputs')}",
                f"inbox = {_toml_path(root / 'inbox')}",
                f"exports = {_toml_path(root / 'exports')}",
                "",
                "[dashboard]",
                f"passphrase_file = {_toml_path(root / 'dashboard-passphrase')}",
                'bind = "127.0.0.1"',
                f"port = {port}",
                "",
            )
        ),
        encoding="utf-8",
    )
    profile = load_profile_file(profile_file)
    migrate_gold(profile)
    accounts = _accounts()
    set_passphrase(profile, DEMO_ACCESS_TEXT)
    _publish(profile, accounts)
    return profile
