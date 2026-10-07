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
from tests.cli.commands import import_, migrate
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, log_entries, payload

EXIT_OK = 0


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


if __name__ == "__main__":
    unittest.main()
