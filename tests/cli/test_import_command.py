# Copyright 2026 Therkel
"""`budget import`: every inbox export into Bronze, then Silver and a backup.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. Every account, date, text and amount
is synthetic.
"""

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.bronze.parsers.registry import source_parser
from budget.profiles import Profile, load_profile_file
from budget.routine_logging import LOG_FILE, LOG_FOLDER
from budget.silver import SilverStore
from tests.backups.sets import manifest, run_ids
from tests.cli.commands import import_, migrate
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, log_entries, payload

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3
EXIT_REFUSED_ENVIRONMENT = 4
NOW = datetime(2026, 3, 5, 18, 5, 11, 120731, tzinfo=UTC)


def _household(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _set_names(profile: Profile) -> list[str]:
    """The backup sets the profile's backups folder holds, by name."""
    folder = profile.backup_path(".")
    return sorted(child.name for child in folder.iterdir()) if folder.is_dir() else []


def _clean_git() -> mock.Mock:
    """A finished Git call reporting a clean, tracked checkout."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = ""
    completed.stderr = ""
    return completed


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

    def test_a_file_that_cannot_be_read_stays_while_the_others_are_stored(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            locked = drop(profile, "joint-current", "danske-20260305.csv", content)
            stored = drop(profile, "joint-savings", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))
            # Windows refuses every read of a file another program holds
            # without sharing it.
            read_bytes = Path.read_bytes

            def held(path: Path) -> bytes:
                if path == locked:
                    raise PermissionError(13, "Permission denied", str(path))
                return read_bytes(path)

            with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=held):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.startswith(
                "[1] joint-current  unreadable: the file cannot be read "
                "(Permission denied): close the program that holds it, then "
                "rerun import; it stays in the inbox\n"
                "[2] joint-savings  stored\n"
            )
            assert str(locked) not in stdout
            assert locked.read_bytes() == content
            assert not stored.exists()

    def test_a_file_outside_every_account_folder_is_misfiled(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            profile.inbox.mkdir(parents=True)
            stray = profile.inbox / "danske-20260305.csv"
            stray.write_bytes(content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.startswith(
                "[1] (no account)  misfiled: only a file directly inside "
                "inbox/<account_id>/ can be imported; it stays in the inbox\n"
            )
            assert stray.read_bytes() == content
            assert not profile.import_log_file.exists()

    def test_a_file_in_a_folder_inside_an_account_folder_is_misfiled(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = payload("01.03.2026")
            nested = profile.inbox / "joint-current" / "old" / "danske-20260305.csv"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.startswith(
                "[1] (no account)  misfiled: only a file directly inside "
                "inbox/<account_id>/ can be imported; it stays in the inbox\n"
            )
            assert nested.read_bytes() == content
            assert not profile.import_log_file.exists()

    def test_a_format_failure_is_stored_and_reported_with_its_reason(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            content = b'"Not","A","Danske","Export"\r\n"1","2","3","4"'
            source = drop(profile, "joint-current", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))
            reason = source_parser("danske-csv-v1").parse(content).failure_reason
            assert reason is not None

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert f"[1] joint-current  format failure: {reason}\n" in stdout
            assert "Silver   0 admitted, 1 quarantined, 0 dropped\n" in stdout
            assert not source.exists()
            [entry] = log_entries(profile)
            assert entry["outcome"] == "stored"

    def test_the_log_and_summary_carry_counts_and_no_bank_content(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            stored_name = "danske-20260305.csv"
            misfiled_name = "Konto-0099999999-20260305.csv"
            drop(profile, "joint-current", misfiled_name, payload("01.03.2026"))
            drop(profile, "joint-current", stored_name, payload("01.03.2026"))
            # Refused: a transaction falls after the declared range ends.
            drop(profile, "joint-savings", stored_name, payload("05.03.2026"))
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            status, summary, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            log = (profile.stores / LOG_FOLDER / LOG_FILE).read_text(encoding="utf-8")
            [record] = [json.loads(line) for line in log.splitlines()]
            assert record["command"] == "import"
            assert record["counts"] == {
                "stored": 1,
                "repeat": 0,
                "refused": 1,
                "misfiled": 1,
                "unreadable": 0,
                "format_failure": 0,
                "admitted": 1,
                "quarantined": 0,
                "dropped": 0,
            }
            # The fixture's amounts, balance, texts, filenames and numbers.
            fixture = (
                "-45,00",
                "955,00",
                "Café",
                "Mad",
                "Dagligvarer",
                stored_name,
                misfiled_name,
                "0099999999",
                "0012345678",
            )
            for value in fixture:
                assert value not in log, value
                assert value not in summary, value

    def test_a_rerun_finishes_a_file_another_program_held_and_adds_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            source = drop(
                profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
            )
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))
            # Windows refuses to delete a file another program holds open.
            unlink = Path.unlink

            def held(path: Path, *, missing_ok: bool = False) -> None:
                if path == source:
                    raise PermissionError(13, "held by another program")
                unlink(path, missing_ok=missing_ok)

            with mock.patch.object(Path, "unlink", autospec=True, side_effect=held):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert (
                "[1] joint-current  stored; it stays in the inbox because another"
                " program holds it: close that program, then rerun import\n"
            ) in stdout
            assert source.exists()

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert "[1] joint-current  stored\n" in stdout
            assert not source.exists()
            assert len(log_entries(profile)) == 1
            assert len(run_ids(profile.bronze_store)) == 1

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


class InteractiveImportTests(unittest.TestCase):
    def test_the_prompt_asks_each_files_range_then_imports_on_yes(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            source = drop(
                profile,
                "joint-current",
                "danske-20260305.csv",
                payload("01.03.2026", "02.03.2026"),
            )
            # The first answer is not a date, so `from` is asked again.
            typed = "1 March\n2026-03-01\n2026-03-04\ny\n"

            status, stdout, stderr = import_(profile_file, typed=typed)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.startswith(
                "[1] joint-current  danske-20260305.csv\n"
                "    exported on    2026-03-05 (from filename)\n"
                "    transactions   2026-03-01..2026-03-02, 2 source records\n"
                "    Enter the range you asked the bank for.\n"
                "    from: "
                "    not a date: type it as 2026-09-30\n"
                "    from: "
                "    through: "
                "Import 1 file? [y/N] "
            )
            assert "[1] joint-current  stored\n" in stdout
            assert not source.exists()
            [entry] = log_entries(profile)
            assert (entry["covers_from"], entry["covers_through"]) == (
                "2026-03-01",
                "2026-03-04",
            )

    def test_enter_repeats_the_range_typed_for_the_file_before(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _household(profile_file, folder)
            # Each account its own bytes: one payload belongs to one account.
            drop(profile, "joint-current", "danske-20260305.csv", payload("01.03.2026"))
            drop(profile, "joint-savings", "danske-20260305.csv", payload("02.03.2026"))
            # The second file's range is two presses of Enter.
            typed = "2026-03-01\n2026-03-04\n\n\ny\n"

            status, stdout, stderr = import_(profile_file, typed=typed)

            assert (status, stderr) == (EXIT_OK, "")
            assert (
                "    from [2026-03-01]: "
                "    through [2026-03-04]: "
                "Import 2 files? [y/N] "
            ) in stdout
            ranges = {
                entry["account_id"]: (entry["covers_from"], entry["covers_through"])
                for entry in log_entries(profile)
            }
            assert ranges == {
                "joint-current": ("2026-03-01", "2026-03-04"),
                "joint-savings": ("2026-03-01", "2026-03-04"),
            }

    def test_nothing_is_stored_unless_the_person_confirms(self) -> None:
        answers = {
            "no": "2026-03-01\n2026-03-04\nn\n",
            "just enter": "2026-03-01\n2026-03-04\n\n",
            "input ends at the confirmation": "2026-03-01\n2026-03-04\n",
            "input ends at a range": "2026-03-01\n",
        }
        for case, typed in answers.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder)
                profile = _household(profile_file, folder)
                content = payload("01.03.2026")
                source = drop(profile, "joint-current", "danske-20260305.csv", content)

                status, stdout, stderr = import_(profile_file, typed=typed)

                assert (status, stderr) == (EXIT_OK, "")
                assert stdout.endswith("Nothing was imported.\n")
                assert source.read_bytes() == content
                assert not profile.import_log_file.exists()
                assert run_ids(profile.bronze_store) == []


class ProductionImportTests(unittest.TestCase):
    def test_a_production_import_ends_with_a_backup_set_holding_it(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
            profile = load_profile_file(profile_file)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            sets_before = _set_names(profile)
            drop(profile, "joint-current", "danske-20260305.csv", payload("01.03.2026"))
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            # Production builds only from committed code; Git is the boundary.
            with mock.patch("subprocess.run", return_value=_clean_git()):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            [entry] = log_entries(profile)
            [written] = sorted(set(_set_names(profile)) - set(sets_before))
            assert stdout.endswith(f"Backup   backup set {written} written\n")
            backup_set = profile.backup_path(written)
            stores = manifest(backup_set)["stores"]
            assert isinstance(stores, dict)
            assert set(stores) == {"bronze", "silver"}
            assert run_ids(backup_set / "bronze.db") == [entry["import_run_id"]]

    def test_a_backup_that_fails_after_the_imports_says_what_was_done(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
            profile = load_profile_file(profile_file)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            source = drop(
                profile, "joint-current", "danske-20260305.csv", payload("01.03.2026")
            )
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))
            # The clock names the set after a folder that already exists, and
            # a set never replaces another, so it cannot be written.
            profile.backup_path(NOW.strftime("%Y-%m-%dT%H-%M-%S.%fZ")).mkdir()
            clock = mock.Mock(wraps=datetime)
            clock.now.return_value = NOW

            with (
                mock.patch("subprocess.run", return_value=_clean_git()),
                mock.patch("budget.inbox.datetime", clock),
            ):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "[1] joint-current  stored\n" in stdout
            assert "Silver   1 admitted, 0 quarantined, 0 dropped\n" in stdout
            assert "Backup" not in stdout
            assert stderr.startswith(
                "budget: the exports were imported and Silver rebuilt, but no "
                "backup set could be written after them: "
            )
            assert stderr.endswith("Put that right, then run `budget backup`\n")
            assert not source.exists()
            [entry] = log_entries(profile)
            assert entry["outcome"] == "stored"

    def test_an_empty_inbox_imports_nothing_and_writes_no_set(self) -> None:
        for mode in ((), ("--ranges", "ranges.toml")):
            with self.subTest(mode), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder, name="production")
                assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
                profile = load_profile_file(profile_file)
                profile.inputs.mkdir(parents=True, exist_ok=True)
                profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
                (profile.inbox / "joint-current").mkdir(parents=True)
                _ranges(folder, default=("2026-03-01", "2026-03-04"))
                sets_before = _set_names(profile)
                options = [
                    str(folder / option) if option.endswith(".toml") else option
                    for option in mode
                ]

                with mock.patch("subprocess.run", return_value=_clean_git()):
                    status, stdout, stderr = import_(profile_file, *options)

                assert (status, stderr) == (EXIT_OK, "")
                assert stdout == "The inbox holds no exports; nothing was imported.\n"
                assert _set_names(profile) == sets_before

    def test_when_no_file_reaches_bronze_nothing_is_rebuilt_or_backed_up(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
            profile = load_profile_file(profile_file)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            sets_before = _set_names(profile)
            content = payload("01.03.2026")
            drop(profile, "lost-folder", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            with mock.patch("subprocess.run", return_value=_clean_git()):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_REFUSED_INPUT, "")
            lines = stdout.splitlines()
            assert lines[0].startswith("[1] (no account)  misfiled: ")
            assert lines[1:] == ["Nothing was imported."]
            assert _set_names(profile) == sets_before

    def test_an_account_silver_cannot_build_refuses_before_storing(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
            profile = load_profile_file(profile_file)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            # accounts.toml takes any currency text; Silver's build does not.
            profile.accounts_file.write_text(
                ACCOUNTS.replace('currency = "DKK"', 'currency = "ZZZ"', 1),
                encoding="utf-8",
            )
            sets_before = _set_names(profile)
            content = payload("01.03.2026")
            source = drop(profile, "joint-current", "danske-20260305.csv", content)
            ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))

            with mock.patch("subprocess.run", return_value=_clean_git()):
                status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert 'account "joint-current": currency is not supported' in stderr
            assert "ZZZ" not in stderr
            assert source.read_bytes() == content
            assert run_ids(profile.bronze_store) == []
            assert _set_names(profile) == sets_before

    def test_what_would_refuse_the_build_or_backup_refuses_first(self) -> None:
        # Each case breaks something the rebuild or the backup after the
        # Bronze writes would refuse, so nothing may be stored before it.
        cases = {
            "uncommitted code": (EXIT_REFUSED_ENVIRONMENT, "uncommitted"),
            "a decision": (EXIT_REFUSED_INPUT, "decisions.jsonl"),
            "a store no set covers": (EXIT_REFUSED_ENVIRONMENT, "gold.db"),
        }
        for case, (expected, named) in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder, name="production")
                assert migrate(profile_file, "--new-store") == (EXIT_OK, "")
                profile = load_profile_file(profile_file)
                profile.inputs.mkdir(parents=True, exist_ok=True)
                profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
                sets_before = _set_names(profile)
                content = payload("01.03.2026")
                source = drop(profile, "joint-current", "danske-20260305.csv", content)
                ranges = _ranges(folder, default=("2026-03-01", "2026-03-04"))
                git = _clean_git()
                if case == "uncommitted code":
                    git.stdout = " M src/budget/cli.py\n"
                if case == "a decision":
                    profile.input_file("decisions.jsonl").write_text(
                        '{"decision_id": "d-0001"}\n', encoding="utf-8"
                    )
                if case == "a store no set covers":
                    (profile.stores / "gold.db").write_bytes(b"")

                with mock.patch("subprocess.run", return_value=git):
                    status, stdout, stderr = import_(
                        profile_file, "--ranges", str(ranges)
                    )

                assert status == expected
                assert stdout == ""
                assert named in stderr
                assert source.read_bytes() == content
                assert not profile.import_log_file.exists()
                assert run_ids(profile.bronze_store) == []
                assert _set_names(profile) == sets_before


if __name__ == "__main__":
    unittest.main()
