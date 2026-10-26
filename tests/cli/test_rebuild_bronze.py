# Copyright 2026 Therkel
"""`budget rebuild --from bronze` regenerates Bronze's derived records.

The retained payloads are the only input it needs: the inbox files are gone
before every test here runs it. Every test passes `main` an explicit
environment, and Bronze is read back through its public reads.
"""

import unittest
from collections.abc import Callable
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore, ImportDeclaration
from budget.bronze.parsers.base import ParserResult
from budget.bronze.parsers.registry import source_parser
from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverStore
from tests.bronze.lines import LineParser, SecondLineParser
from tests.cli.commands import rebuild
from tests.cli.pipelines import EXPORT, Prepared, household, prepared, write_inputs
from tests.importing.households import ACCOUNTS, drop

EXIT_OK = 0
EXPORT_FIELDS = {
    "Dato": "01.03.2026",
    "Kategori": " Mad ",
    "Underkategori": " Dagligvarer ",
    "Tekst": "Café",
    "Beløb": "-45,00",
    "Saldo": "955,00",
    "Status": "Udført",
    "Afstemt": "Nej",
}


class RebuildFromBronzeTests(unittest.TestCase):
    def test_retained_payloads_rebuild_bronze_silver_and_gold_without_the_inbox(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            inbox = built.profile.inbox / "joint-current"
            for leftover in inbox.glob("*"):
                leftover.unlink()

            status, stdout, stderr = rebuild(built.profile_file, "--from", "bronze")

            assert (status, stderr) == (EXIT_OK, "")
            assert "1 admitted" in stdout
            assert "published publication 1" in stdout
            with BronzeStore(built.profile) as bronze:
                (run,) = bronze.import_runs()
                records = bronze.get_source_records(run.payload_id)
            assert [dict(record.fields) for record in records] == [EXPORT_FIELDS]
            with SilverStore(built.profile) as silver:
                assert [t.description for t in silver.read().transactions] == ["Café"]
            with GoldStore(built.profile) as gold:
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
            assert [t.description for t in transactions] == ["Café"]


class ProvenanceTests(unittest.TestCase):
    def test_a_rebuild_is_not_an_import_and_keeps_every_run_and_the_log(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            profile = built.profile
            # The same bytes presented again, and a declaration Bronze refuses.
            for name, through in (
                ("danske-20260310.csv", date(2026, 3, 9)),
                ("danske-20260312.csv", date(2026, 3, 20)),
            ):
                source = drop(profile, "joint-current", name, EXPORT)
                with writer_lock(profile) as lock:
                    import_inbox_file(lock, source, Coverage(date(2026, 3, 1), through))
            with BronzeStore(profile) as bronze:
                runs_before = bronze.import_runs()
            log_before = profile.import_log_file.read_bytes()
            assert [run.outcome for run in runs_before] == [
                "stored",
                "repeat",
                "refused",
            ]

            status, _, stderr = rebuild(built.profile_file, "--from", "bronze")

            assert (status, stderr) == (EXIT_OK, "")
            with BronzeStore(profile) as bronze:
                assert bronze.import_runs() == runs_before
            assert profile.import_log_file.read_bytes() == log_before


DANSKE = "danske-csv-v1"
LINES = b"12.03.2026\n"
EXIT_REFUSED_INPUT = 3


class _StaleDanske:
    """An older version of the Danske reader, which got the text field wrong."""

    source_format = DANSKE

    def parse(self, content: bytes) -> ParserResult:
        """Read the payload as the current reader does, then spoil its text."""
        current = source_parser(DANSKE).parse(content)
        return ParserResult.matched(
            tuple({**record, "Tekst": "STALE"} for record in current.records),
            current.first_transaction_date,
            current.last_transaction_date,
        )

    def exported_on_from_filename(self, filename: str) -> date | None:
        """Read the export date as the current reader does."""
        return source_parser(DANSKE).exported_on_from_filename(filename)

    def account_number_from_filename(self, filename: str) -> str | None:
        """Read the account number as the current reader does."""
        return source_parser(DANSKE).account_number_from_filename(filename)

    def is_account_number(self, value: str) -> bool:
        """Judge an account number as the current reader does."""
        return source_parser(DANSKE).is_account_number(value)


def _declaration(source_format: str = DANSKE) -> ImportDeclaration:
    """The household's one declaration, for whichever format the run names."""
    return ImportDeclaration(
        declared_account_id="joint-current",
        source_format=source_format,
        covers_from=date(2026, 3, 1),
        covers_through=date(2026, 3, 4),
    )


def _stale_household(folder: Path) -> tuple[Prepared, str]:
    """Import the export through the older reader; return its payload id."""
    base = prepared(folder)
    source = drop(base.profile, "joint-current", "danske-20260305.csv", EXPORT)
    with BronzeStore(base.profile, parsers={DANSKE: _StaleDanske()}) as bronze:
        run = bronze.import_file(source, _declaration())
        assert [
            r.fields["Tekst"] for r in bronze.get_source_records(run.payload_id)
        ] == ["STALE"]
    return base, run.payload_id


def _texts(profile: Profile, payload_id: str) -> list[str]:
    """The text field of each source record Bronze holds for a payload."""
    with BronzeStore(profile) as bronze:
        return [r.fields["Tekst"] for r in bronze.get_source_records(payload_id)]


class StaleRecordsTests(unittest.TestCase):
    def test_records_an_older_reader_derived_are_regenerated_by_the_current_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base, payload_id = _stale_household(Path(directory))

            status, stdout, stderr = rebuild(base.profile_file, "--from", "bronze")

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            assert _texts(base.profile, payload_id) == ["Café"]
            with SilverStore(base.profile) as silver:
                assert [t.description for t in silver.read().transactions] == ["Café"]


def _delete_taxonomy(profile: Profile) -> None:
    profile.input_file("taxonomy.toml").unlink()


def _close_early(profile: Profile) -> None:
    write_inputs(
        profile,
        ACCOUNTS.replace(
            'bank_account_number = "0012345678"\n',
            'bank_account_number = "0012345678"\nclosed_on = 2026-02-20\n',
        ),
    )


def _drop_the_account(profile: Profile) -> None:
    write_inputs(profile, ACCOUNTS.split("[account.joint-current]")[0] + SAVINGS_ONLY)


SAVINGS_ONLY = """\
[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
"""


class RefusedRebuildTests(unittest.TestCase):
    def _leaves_bronze_and_silver_untouched(
        self, ruin: Callable[[Profile], object], named: str
    ) -> None:
        with TemporaryDirectory() as directory:
            base, payload_id = _stale_household(Path(directory))
            ruin(base.profile)

            status, stdout, stderr = rebuild(base.profile_file, "--from", "bronze")

            assert status == EXIT_REFUSED_INPUT
            assert stdout == ""
            assert named in stderr
            assert _texts(base.profile, payload_id) == ["STALE"]
            with SilverStore(base.profile) as silver:
                assert not silver.is_built()
            with GoldStore(base.profile) as gold:
                assert gold.current() is None

    def test_a_missing_taxonomy_changes_no_store(self) -> None:
        self._leaves_bronze_and_silver_untouched(_delete_taxonomy, "taxonomy.toml")

    def test_an_account_closed_before_its_transaction_changes_no_store(self) -> None:
        self._leaves_bronze_and_silver_untouched(_close_early, "closed_on")

    def test_an_undeclared_account_changes_no_store_and_says_so(self) -> None:
        self._leaves_bronze_and_silver_untouched(
            _drop_the_account, "nothing was written"
        )


class FormatRefusalTests(unittest.TestCase):
    def test_a_payload_declared_as_two_formats_is_refused_with_exit_3(self) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory))
            source = drop(base.profile, "joint-current", "danske-20260305.csv", LINES)
            parsers = {
                LineParser.source_format: LineParser("line"),
                SecondLineParser.source_format: SecondLineParser("other"),
            }
            with BronzeStore(base.profile, parsers=parsers) as bronze:
                first = bronze.import_file(
                    source, _declaration(LineParser.source_format)
                )
                bronze.import_file(source, _declaration(SecondLineParser.source_format))

            status, stdout, stderr = rebuild(base.profile_file, "--from", "bronze")

            assert (status, stdout) == (EXIT_REFUSED_INPUT, "")
            assert "more than one source format" in stderr
            assert first.payload_id in stderr

    def test_a_retained_payload_whose_format_is_no_longer_registered_is_refused(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base = prepared(Path(directory))
            source = drop(base.profile, "joint-current", "danske-20260305.csv", LINES)
            with BronzeStore(
                base.profile, parsers={LineParser.source_format: LineParser("line")}
            ) as bronze:
                bronze.import_file(source, _declaration(LineParser.source_format))

            status, stdout, stderr = rebuild(base.profile_file, "--from", "bronze")

            assert (status, stdout) == (EXIT_REFUSED_INPUT, "")
            assert LineParser.source_format in stderr
            assert "Traceback" not in stderr


if __name__ == "__main__":
    unittest.main()
