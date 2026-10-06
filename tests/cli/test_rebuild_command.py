# Copyright 2026 Therkel
"""`budget rebuild --from silver`: rebuild Silver from the profile's Bronze.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. The Bronze inputs are real: the test
seeds them through the documented `import_inbox_file` operation, because the
`import` command does not exist yet.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload
from tests.silver.exports import identity

EXIT_OK = 0

HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'
# Two rows whose stated balances chain, and one row the bank later drops.
ACCEPTED_ROWS = (
    ("01.03.2026", "NETTO", "-45,00", "955,00"),
    ("05.03.2026", "BOG", "-25,00", "930,00"),
)
REPEATED_FILE = "danske-20260310.csv"
DROPPED_FILE = "danske-20260309.csv"
BROKEN_FILE = "danske-20260403.csv"
REFUSED_FILE = "danske-20260502.csv"
FIRST_MARCH = date(2026, 3, 1)


def _migrated_profile_with_accounts(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _import_one_export(profile: Profile) -> None:
    """Seed Bronze with one stored import run, as `budget import` will."""
    source = drop(
        profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
    )
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )


def _export_bytes(*rows: tuple[str, str, str, str]) -> bytes:
    """A synthetic `danske-csv-v1` export with one booked row per tuple.

    Each tuple is the source's transaction date, text, amount and balance.
    """
    lines = [
        f'"{dato}"," Mad "," Dagligvarer ","{text}","{amount}","{balance}",'
        '"Udført","Nej"'
        for dato, text, amount, balance in rows
    ]
    return "\r\n".join([HEADER, *lines]).encode("cp1252")


def _import_run_id(
    profile: Profile, name: str, content: bytes, coverage: Coverage
) -> str:
    """Import one export and return the run id Bronze recorded for it."""
    source = drop(profile, "joint-current", name, content)
    with writer_lock(profile) as lock:
        imported = import_inbox_file(lock, source, coverage)
    return imported.import_run.import_run_id


class RebuildFromSilverTests(unittest.TestCase):
    def test_rebuild_from_silver_stores_the_result_from_bronze(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _migrated_profile_with_accounts(profile_file, folder)
            _import_one_export(profile)

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_OK
            assert stderr == ""
            with SilverStore(profile) as store:
                result = store.read()
            assert [(t.account_id, t.description) for t in result.transactions] == [
                ("joint-current", "Café")
            ]
            assert [r.status for r in result.import_run_results] == ["accepted"]
            assert "1 admitted" in stdout


class RebuildSummaryTests(unittest.TestCase):
    def test_rebuild_summarises_each_account_and_run_without_payloads(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _migrated_profile_with_accounts(profile_file, folder)
            accepted_bytes = _export_bytes(*ACCEPTED_ROWS)

            accepted = _import_run_id(
                profile,
                "danske-20260306.csv",
                accepted_bytes,
                Coverage(FIRST_MARCH, date(2026, 3, 5)),
            )
            broken = _import_run_id(
                profile,
                BROKEN_FILE,
                _export_bytes(
                    ("01.04.2026", "NETTO", "-45,00", "955,00"),
                    ("02.04.2026", "BIO", "-100,00", "955,00"),
                ),
                Coverage(date(2026, 4, 1), date(2026, 4, 2)),
            )
            refused = _import_run_id(
                profile,
                REFUSED_FILE,
                _export_bytes(("01.05.2026", "NETTO", "-45,00", "955,00")),
                # Through the day after the export date: Bronze refuses it.
                Coverage(date(2026, 5, 1), date(2026, 5, 3)),
            )
            repeated = _import_run_id(
                profile,
                REPEATED_FILE,
                accepted_bytes,
                Coverage(FIRST_MARCH, date(2026, 3, 9)),
            )
            dropped = _import_run_id(
                profile,
                DROPPED_FILE,
                _export_bytes(("05.03.2026", "BOG", "-25,00", "975,00")),
                Coverage(FIRST_MARCH, date(2026, 3, 8)),
            )

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_OK
            assert stderr == ""
            assert stdout.splitlines() == [
                "Bronze   5 import runs: 3 stored, 1 repeat, 1 refused",
                (
                    "Account  joint-current: 1 admitted, 2 quarantined,"
                    " 1 refused, 1 repeat, 1 dropped"
                ),
                f"Run  {accepted}  joint-current  accepted",
                (
                    f"Run  {broken}  joint-current  quarantined"
                    "  balance-break, balance-chain-break"
                ),
                f"Run  {refused}  joint-current  refused",
                # A repeat names the result of the canonical original it
                # repeats, rather than assuming that run was admitted.
                f"Run  {repeated}  joint-current  repeat accepted",
                f"Run  {dropped}  joint-current  quarantined  dropped-transaction",
            ]
            # Only identifiers and existing codes reach the terminal: no
            # amount, description, original filename, transaction id, or
            # validation message.
            dropped_transaction = identity(FIRST_MARCH, "-45.00", "NETTO", 1)
            for leaked in (
                "-45,00",
                "955,00",
                "975,00",
                "NETTO",
                "BOG",
                "BIO",
                "danske-20260306.csv",
                "balance does not follow the previous",
                dropped_transaction,
            ):
                assert leaked not in stdout


if __name__ == "__main__":
    unittest.main()
