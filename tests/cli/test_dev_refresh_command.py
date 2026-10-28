# Copyright 2026 Therkel
"""`budget dev refresh`: give development production's newest backup set.

Each test writes a synthetic production profile and a development profile
whose `upstream_backups` names production's backups folder, both in one
temporary folder. Every test passes `main` an explicit environment.
"""

import stat
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import BackupSet, back_up
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import checksum, import_one
from tests.cli.commands import dev_refresh, migrate
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0


def _production_with_a_set(folder: Path) -> tuple[Profile, BackupSet]:
    """Start production in `folder`, import one run, and back it up."""
    folder.mkdir()
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir()
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    with writer_lock(production) as lock:
        import_one(lock)
        written = back_up(lock, now=datetime.now(UTC))
    return production, written


def _development(folder: Path, production: Profile) -> tuple[Path, Profile]:
    """Write a development profile in `folder` reading production's sets."""
    folder.mkdir()
    profile_file = write_profile(folder, upstream_backups=production.backups)
    return profile_file, load_profile_file(profile_file)


class DevRefreshTests(unittest.TestCase):
    def test_dev_refresh_restores_the_newest_set_into_upstream_read_only(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            development.inputs.mkdir()
            own_accounts = b"# development's own working copy\n"
            development.accounts_file.write_bytes(own_accounts)

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {written.name} into upstream (read-only)\n"
            )
            upstream = development.stores / "upstream"
            for store in ("bronze.db", "silver.db", "gold.db"):
                copy = upstream / store
                assert checksum(copy) == checksum(written.path / store)
                assert not copy.stat().st_mode & stat.S_IWRITE
            assert development.accounts_file.read_bytes() == own_accounts
            assert not development.bronze_store.exists()
