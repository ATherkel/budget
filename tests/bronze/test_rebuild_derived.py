# Copyright 2026 Therkel
"""Bronze regenerates its derived records from the payloads it retained.

A parser fix changes what a payload's bytes derive to, so these tests present
the same payload to a store with another version of a real, tiny format
(`LineParser`) and rebuild. The bytes, every import run and the other derived
records are read back through the store's public reads.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast, override

import pytest

from budget.bronze import BronzeStore, ImportDeclaration, ImportRun
from budget.bronze.parsers.base import ParserResult
from budget.bronze.store import ConflictingDeclaredFormatsError
from budget.profiles import Profile
from tests.bronze.lines import LineParser, migrated_profile

FORMAT = LineParser.source_format
FIRST_EXPORT = b"12.09.2026\n05.09.2026\n"
SECOND_EXPORT = b"01.09.2026\n"


def _declaration() -> ImportDeclaration:
    """One account's declaration, wide enough for every payload here."""
    return ImportDeclaration(
        declared_account_id="daily-account",
        source_format=FORMAT,
        exported_on=date(2026, 9, 14),
        covers_from=date(2026, 9, 1),
        covers_through=date(2026, 9, 13),
    )


def _import(store: BronzeStore, folder: Path, name: str, content: bytes) -> ImportRun:
    """Save one export under `name` and import it into `store`."""
    source = folder / name
    source.write_bytes(content)
    return store.import_file(source, _declaration())


class RebuildDerivedRecordsTests(unittest.TestCase):
    def test_changed_parser_output_replaces_the_earlier_records(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
                run = _import(store, root, "synthetic-20260914.csv", FIRST_EXPORT)
            source_gone = root / "synthetic-20260914.csv"
            source_gone.unlink()

            # A later version reads one field under another name and stops
            # after the first line, so a record disappears.
            with BronzeStore(
                profile, parsers={FORMAT: LineParser("only", limit=1)}
            ) as store:
                store.rebuild_derived_records()

                records = store.get_source_records(run.payload_id)
                assert [(r.record_ordinal, dict(r.fields)) for r in records] == [
                    (1, {"only": "12.09.2026"})
                ]
                assert store.get_payload(run.payload_id).content == FIRST_EXPORT
                assert store.get_import_run(run.import_run_id) == run

    def test_a_payload_that_no_longer_parses_loses_its_records_and_gains_a_verdict(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
                run = _import(store, root, "synthetic-20260914.csv", FIRST_EXPORT)

            with BronzeStore(
                profile, parsers={FORMAT: LineParser(None, failure="no lines")}
            ) as store:
                store.rebuild_derived_records()

                assert store.get_source_records(run.payload_id) == ()
                assert [
                    (f.source_format, f.reason)
                    for f in store.get_format_failures(run.payload_id)
                ] == [(FORMAT, "no lines")]
                assert store.get_import_run(run.import_run_id) == run

    def test_a_payload_that_parses_again_loses_its_stale_verdict(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            with BronzeStore(
                profile, parsers={FORMAT: LineParser(None, failure="no lines")}
            ) as store:
                run = _import(store, root, "synthetic-20260914.csv", FIRST_EXPORT)
                assert len(store.get_format_failures(run.payload_id)) == 1

            with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
                store.rebuild_derived_records()

                assert store.get_format_failures(run.payload_id) == ()
                assert len(store.get_source_records(run.payload_id)) == 2


class _RaisingParser(LineParser):
    """A version of the format whose parser fails on one payload."""

    @override
    def parse(self, content: bytes) -> ParserResult:
        """Raise for the second export, as a defect in a new version would."""
        if content == SECOND_EXPORT:
            message = "parser defect"
            raise RuntimeError(message)
        return super().parse(content)


class _UnstorableParser(LineParser):
    """A version whose record for one payload SQLite's JSON column cannot hold."""

    @override
    def parse(self, content: bytes) -> ParserResult:
        """Present a field value that is not text, for the second export."""
        if content == SECOND_EXPORT:
            unstorable = cast("Any", {"only": {1, 2}})
            return ParserResult.matched((unstorable,), None, None)
        return super().parse(content)


class AtomicityTests(unittest.TestCase):
    def _two_payloads(self, root: Path) -> tuple[Profile, ImportRun, ImportRun]:
        """Import two exports with the first version of the format."""
        profile = migrated_profile(root)
        with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
            first = _import(store, root, "synthetic-20260914.csv", FIRST_EXPORT)
            second = _import(store, root, "synthetic-20260915.csv", SECOND_EXPORT)
        return profile, first, second

    def _unchanged_after(self, parser: LineParser) -> None:
        """Rebuild with `parser`, which fails, and expect the earlier state."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, first, second = self._two_payloads(root)
            with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
                before = [
                    store.get_source_records(each.payload_id)
                    for each in (first, second)
                ]
                runs = store.import_runs()

            with (
                BronzeStore(profile, parsers={FORMAT: parser}) as store,
                pytest.raises((RuntimeError, TypeError)),
            ):
                store.rebuild_derived_records()

            with BronzeStore(profile, parsers={FORMAT: LineParser("datum")}) as store:
                after = [
                    store.get_source_records(each.payload_id)
                    for each in (first, second)
                ]
                assert (after, store.import_runs()) == (before, runs)
                assert len(after[0]) == 2

    def test_a_parser_that_raises_leaves_the_committed_state_as_it_was(self) -> None:
        self._unchanged_after(_RaisingParser("only"))

    def test_a_record_that_cannot_be_stored_rolls_the_whole_rebuild_back(self) -> None:
        self._unchanged_after(_UnstorableParser("only"))


class _SecondFormat(LineParser):
    """Another declared format, which happens to read the same bytes."""

    source_format = "synthetic-lines-v2"


class ConflictingFormatsTests(unittest.TestCase):
    def test_a_payload_declared_as_two_formats_is_refused_not_guessed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = migrated_profile(root)
            parsers = {
                FORMAT: LineParser("datum"),
                _SecondFormat.source_format: _SecondFormat("other"),
            }
            with BronzeStore(profile, parsers=parsers) as store:
                run = _import(store, root, "synthetic-20260914.csv", FIRST_EXPORT)
                other = ImportDeclaration(
                    declared_account_id="daily-account",
                    source_format=_SecondFormat.source_format,
                    exported_on=date(2026, 9, 14),
                    covers_from=date(2026, 9, 1),
                    covers_through=date(2026, 9, 13),
                )
                store.import_file(root / "synthetic-20260914.csv", other)
                before = store.get_source_records(run.payload_id)

                with pytest.raises(ConflictingDeclaredFormatsError) as refusal:
                    store.rebuild_derived_records()

                assert run.payload_id in str(refusal.value)
                assert store.get_source_records(run.payload_id) == before
                assert store.get_format_failures(run.payload_id) == ()


if __name__ == "__main__":
    unittest.main()
