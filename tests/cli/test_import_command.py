# Copyright 2026 Therkel
"""`budget import`: every inbox export into Bronze, then Silver and a backup.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. Every account, date, text and amount
is synthetic.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from budget.silver import SilverStore
from tests.backups.sets import run_ids
from tests.cli.commands import import_, migrate
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, log_entries, payload

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3


def _household(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _ranges(
    folder: Path,
    default: tuple[str, str] | None = None,
    accounts: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Write a ranges file: a default range and per-account ranges."""
    lines = ["format = 1"]
    if default is not None:
        lines += ["", "[default]", f"from = {default[0]}", f"through = {default[1]}"]
    for account_id, (start, end) in (accounts or {}).items():
        lines += ["", f"[account.{account_id}]", f"from = {start}", f"through = {end}"]
    path = folder / "ranges.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class ImportCommandTests(unittest.TestCase):
    def test_an_inbox_export_is_imported_then_silver_is_rebuilt(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            source = drop(profile, "joint-current", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert not source.exists()
            archived = profile.exports / "joint-current" / "danske-20260305.csv"
            assert archived.read_bytes() == content
            [entry] = log_entries(profile)
            assert entry["outcome"] == "stored"
            assert (entry["covers_from"], entry["covers_through"]) == (
                "2026-03-01",
                "2026-03-04",
            )
            with SilverStore(profile) as store:
                [result] = store.read().import_run_results
            assert result.import_run_id == entry["import_run_id"]
            assert result.status == "accepted"
            assert "[1] joint-current  stored\n" in stdout
            assert "Silver   1 admitted, 0 quarantined, 0 dropped\n" in stdout

    def test_a_refused_export_stays_while_the_others_are_stored(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            # The declared range starts after the file's first transaction.
            refused = drop(
                profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
            )
            stored = drop(
                profile, "joint-savings", "danske-20260305.csv", payload("02.03.2026")
            )
            ranges = _ranges(
                folder,
                accounts={
                    "joint-current": ("2026-03-02", "2026-03-04"),
                    "joint-savings": ("2026-03-01", "2026-03-04"),
                },
            )

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            assert refused.exists()
            assert not stored.exists()
            outcomes = {
                entry["account_id"]: entry["outcome"] for entry in log_entries(profile)
            }
            assert outcomes == {"joint-current": "refused", "joint-savings": "stored"}
            [copy] = (profile.exports / "joint-current" / "refused").rglob("*.csv")
            assert copy.read_bytes() == refused.read_bytes()
            assert (
                "[1] joint-current  refused: the file has transactions before the"
                " declared range starts; it stays in the inbox\n"
            ) in stdout
            assert "[2] joint-savings  stored\n" in stdout
            assert "Silver   1 admitted, 0 quarantined, 0 dropped\n" in stdout

    def test_misfiled_exports_stay_while_the_others_are_stored(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            # The filename names another bank account than joint-current's.
            other_number = drop(
                profile, "joint-current", "Konto-0099999999-20260305.csv", content
            )
            stored = drop(profile, "joint-savings", "danske-20260305.csv", content)
            # A folder accounts.toml does not name declares no account.
            no_account = drop(profile, "lost-folder", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            assert other_number.read_bytes() == content
            assert no_account.read_bytes() == content
            assert not stored.exists()
            [entry] = log_entries(profile)
            assert (entry["account_id"], entry["outcome"]) == (
                "joint-savings",
                "stored",
            )
            lines = stdout.splitlines()
            assert lines[0].startswith(
                '[1] joint-current  misfiled: account "joint-current": the export\'s'
                " filename carries another bank account number"
            )
            assert lines[0].endswith("; it stays in the inbox")
            assert lines[1] == "[2] joint-savings  stored"
            assert lines[2].startswith(
                "[3] (no account)  misfiled: an inbox folder names no account"
            )
            assert lines[2].endswith("; it stays in the inbox")
            assert "0099999999" not in stdout
            assert "lost-folder" not in stdout

    def test_an_account_without_a_range_stops_before_anything_is_stored(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            first = drop(profile, "joint-current", "danske-20260305.csv", content)
            second = drop(profile, "joint-savings", "danske-20260305.csv", content)
            ranges = _ranges(
                folder, accounts={"joint-current": ("2026-03-01", "2026-03-04")}
            )

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert stderr == (
                'budget: the ranges file: account "joint-savings" has no range,'
                " and there is no [default]; nothing was imported\n"
            )
            assert first.read_bytes() == content
            assert second.read_bytes() == content
            assert not profile.import_log_file.exists()
            assert run_ids(profile.bronze_store) == []

    def test_a_ranges_file_that_breaks_its_rules_stores_nothing(self) -> None:
        cases = {
            "missing": (None, "cannot be read"),
            "not TOML": ("format = 1\n[default\n", "is not valid TOML"),
            "no format": (
                "[default]\nfrom = 2026-03-01\nthrough = 2026-03-04\n",
                "format must be 1",
            ),
            "quoted date": (
                'format = 1\n[default]\nfrom = "2026-03-01"\nthrough = 2026-03-04\n',
                "[default]: from must be a date such as 2026-09-30, without quotes",
            ),
            "date and time": (
                (
                    "format = 1\n[default]\nfrom = 2026-03-01T10:00:00\n"
                    "through = 2026-03-04\n"
                ),
                "[default]: from must be a date such as 2026-09-30, without quotes",
            ),
            "no through": (
                "format = 1\n[default]\nfrom = 2026-03-01\n",
                "[default]: through is missing",
            ),
            "unknown key": (
                (
                    "format = 1\n[default]\nfrom = 2026-03-01\nthrough = 2026-03-04\n"
                    "to = 2026-03-04\n"
                ),
                "[default]: unknown key to",
            ),
            "unknown table": (
                "format = 1\n[defaults]\nfrom = 2026-03-01\nthrough = 2026-03-04\n",
                "unknown key defaults",
            ),
            "unknown account": (
                (
                    "format = 1\n[account.joint-curent]\nfrom = 2026-03-01\n"
                    "through = 2026-03-04\n"
                ),
                '[account.joint-curent]: "joint-curent" is not in accounts.toml',
            ),
        }
        for case, (text, problem) in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder)
                profile = _household(profile_file, folder)
                content = payload("01.03.2026")
                source = drop(profile, "joint-current", "danske-20260305.csv", content)
                ranges = folder / "ranges.toml"
                if text is not None:
                    ranges.write_text(text, encoding="utf-8")

                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

                assert status == EXIT_REFUSED_INPUT
                assert stdout == ""
                assert stderr.startswith("budget: the ranges file: ")
                assert problem in stderr
                assert stderr.endswith("; nothing was imported\n")
                assert source.read_bytes() == content
                assert not profile.import_log_file.exists()


if __name__ == "__main__":
    unittest.main()
