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
EXIT_REFUSED_ENVIRONMENT = 4


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

    def test_dev_refresh_with_inputs_replaces_developments_inputs(self) -> None:
        # Development's inputs become production's, as the set holds them:
        # a file only development had is not kept.
        with TemporaryDirectory() as directory:
            production, written = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            development.inputs.mkdir()
            development.accounts_file.write_bytes(b"# a development edit\n")
            development.input_file("rules.toml").write_bytes(b"# draft rules\n")

            status, stdout, stderr = dev_refresh(profile_file, "--inputs")

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {written.name} into upstream (read-only)\n"
                f"replaced development's inputs with backup set {written.name}'s\n"
            )
            sets_inputs = written.path / "inputs"
            assert sorted(path.name for path in development.inputs.iterdir()) == (
                sorted(path.name for path in sets_inputs.iterdir())
            )
            assert (
                development.accounts_file.read_bytes()
                == (sets_inputs / "accounts.toml").read_bytes()
            )

    def test_dev_refresh_refuses_a_profile_that_reads_no_upstream_sets(
        self,
    ) -> None:
        # Production never refreshes from itself, and development without
        # `upstream_backups` has no sets to read.
        with TemporaryDirectory() as directory:
            production, _ = _production_with_a_set(Path(directory) / "prod")
            (Path(directory) / "dev").mkdir()
            cases = {
                "production": Path(directory) / "prod" / "production.toml",
                "development without upstream_backups": write_profile(
                    Path(directory) / "dev"
                ),
            }
            for case, profile_file in cases.items():
                with self.subTest(case):
                    status, stdout, stderr = dev_refresh(profile_file)

                    assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
                    assert "dev refresh needs a development profile" in stderr
            assert not (production.stores / "upstream").exists()

    def test_dev_refresh_replaces_upstream_with_a_newer_set(self) -> None:
        with TemporaryDirectory() as directory:
            production, _ = _production_with_a_set(Path(directory) / "prod")
            profile_file, development = _development(
                Path(directory) / "dev", production
            )
            assert dev_refresh(profile_file)[0] == EXIT_OK
            with writer_lock(production) as lock:
                import_one(lock, "export-20260509.csv")
                newer = back_up(lock, now=datetime.now(UTC))

            status, stdout, stderr = dev_refresh(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == (
                f"restored backup set {newer.name} into upstream (read-only)\n"
            )
            upstream = development.stores / "upstream" / "bronze.db"
            assert checksum(upstream) == checksum(newer.path / "bronze.db")
