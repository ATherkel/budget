# Copyright 2026 Therkel
"""An isolated synthetic dashboard profile for development and review."""

import json
import sqlite3
import sys
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from budget.dashboard.passphrase import set_passphrase
from budget.gold import (
    GoldAccount,
    GoldPublication,
    GoldRecords,
    GoldResult,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.inputs import Account, ConfigurationSnapshot, Taxonomy
from budget.profiles import Profile, load_profile_file

DEMO_ACCESS_TEXT = "budget-demo"
DEFAULT_DEMO_PORT = 8765


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
    return GoldRecords(accounts=gold_accounts, monthly_balances=balances)


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
        import_runs=frozenset({RecipeImportRun("synthetic-dashboard-demo", "a" * 64)}),
        configuration_fingerprint=configuration.fingerprint,
        decision_log_position=0,
        decision_log_prefix_sha256="b" * 64,
        code_version=None,
        contract_version="0.2",
        silver_identity_version="1",
        python_version=sys.version.split()[0],
        sqlite_version=sqlite3.sqlite_version,
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
