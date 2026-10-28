# Copyright 2026 Therkel
"""`budget rebuild` publishes Gold from the stored Silver and the household inputs.

Every test passes `main` an explicit environment. The Gold publication is read
back through `GoldStore`, so a test sees what a dashboard would.
"""

import json
import re
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.store import GoldStore
from budget.inputs import load_configuration
from budget.locking import WriterLock, writer_lock
from budget.rebuilding import GoldRebuild, HouseholdInputs, rebuild_from_gold
from budget.silver import SameTransaction, SilverResult, SilverStore, result_fingerprint
from budget.silver.currencies import UnknownCurrencyError
from tests.cli.commands import rebuild
from tests.cli.pipelines import (
    EXPORT,
    household,
    present_again,
    rebuild_silver_with,
)

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class FirstPublicationTests(unittest.TestCase):
    def test_the_gold_recipe_copies_the_exact_silver_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "synthetic withdrawal",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                json.dumps(decision) + "\n",
                encoding="utf-8",
            )
            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
                provenance = context.provenance
                assert provenance is not None
                silver_store.replace(
                    context.result,
                    currencies=context.currencies,
                    provenance=replace(provenance, code_version="silver-producer"),
                )
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            provenance = context.provenance
            assert provenance is not None

            # `rebuild --from silver` published 1; the Gold rebuild publishes 2.
            with GoldStore(built.profile) as gold:
                recipe = gold.recipe(2)

            assert recipe.silver_fingerprint_scheme == provenance.fingerprint_scheme
            assert recipe.silver_result_fingerprint == provenance.result_fingerprint
            assert recipe.silver_code_version == provenance.code_version
            assert (
                recipe.silver_decision_log_position == provenance.decision_log_position
            )
            assert (
                recipe.silver_decision_log_prefix_sha256
                == provenance.decision_log_prefix_sha256
            )
            assert (
                recipe.silver_bronze_parser_provenance
                == provenance.bronze_parser_provenance
            )
            assert recipe.silver_identity_version == provenance.identity_version
            assert recipe.silver_currencies == frozenset(provenance.currencies.items())
            assert recipe.silver_decisions == provenance.decisions
            assert recipe.code_version is None
            assert recipe.silver_code_version == "silver-producer"
            assert recipe.silver_code_version != recipe.code_version
            assert recipe.silver_decision_log_position == 1
            assert recipe.silver_decision_log_prefix_sha256 != sha256(b"").hexdigest()

    def test_rebuild_publishes_the_first_publication_from_silver(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 1" in stdout
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            provenance = context.provenance
            assert provenance is not None
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert (current.publication_id, current.kind) == (1, "pipeline")
                assert gold.recipe(1) == Recipe(
                    import_runs=frozenset(
                        {
                            RecipeImportRun(
                                built.import_run_id, sha256(EXPORT).hexdigest()
                            )
                        }
                    ),
                    configuration_fingerprint=load_configuration(
                        built.profile
                    ).fingerprint,
                    decision_log_position=0,
                    decision_log_prefix_sha256=sha256(b"").hexdigest(),
                    code_version=None,
                    contract_version="0.2",
                    silver_identity_version="1",
                    late_booking_days=7,
                    python_version="",
                    sqlite_version="",
                    silver_fingerprint_scheme=provenance.fingerprint_scheme,
                    silver_result_fingerprint=provenance.result_fingerprint,
                    silver_code_version=provenance.code_version,
                    silver_decision_log_position=provenance.decision_log_position,
                    silver_decision_log_prefix_sha256=(
                        provenance.decision_log_prefix_sha256
                    ),
                    silver_bronze_parser_provenance=(
                        provenance.bronze_parser_provenance
                    ),
                    silver_currencies=frozenset(provenance.currencies.items()),
                    silver_decisions=provenance.decisions,
                )
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
                assert [t.description for t in transactions] == ["Café"]


class UnchangedRecipeTests(unittest.TestCase):
    def test_gold_only_audit_advance_in_silver_does_not_force_publication(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "classify",
                "targets": [transaction_id],
                "category": "groceries",
                "reason": "synthetic classification",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                json.dumps(decision) + "\n",
                encoding="utf-8",
            )
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                before = gold.pointer_history()
                current = gold.current()
            assert current is not None
            assert current.publication_id == 1

            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == before
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1

    def test_a_second_rebuild_with_nothing_changed_publishes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                moves = gold.pointer_history()

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == moves
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2


class ClockTests(unittest.TestCase):
    def test_two_builds_of_one_recipe_at_different_times_share_a_fingerprint(
        self,
    ) -> None:
        first_run = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)
        second_run = datetime(2026, 9, 1, 17, 30, tzinfo=UTC)
        published = []
        for name, now in (("early", first_run), ("late", second_run)):
            with TemporaryDirectory() as directory:
                built = household(Path(directory) / name)
                with writer_lock(built.profile) as lock:
                    published.append(rebuild_from_gold(lock, now=now).publication)

        early, late = published
        assert (early.built_at, late.built_at) == (first_run, second_run)
        assert re.fullmatch("[0-9a-f]{64}", early.result_fingerprint)
        assert early.result_fingerprint == late.result_fingerprint


class WriterLockTests(unittest.TestCase):
    def test_a_second_writing_command_refuses_while_a_rebuild_holds_the_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            overlapping: list[tuple[int, str, str]] = []

            def rebuild_while_another_command_runs(
                lock: WriterLock, *, now: datetime, inputs: HouseholdInputs
            ) -> GoldRebuild:
                overlapping.append(rebuild(built.profile_file))
                return rebuild_from_gold(lock, now=now, inputs=inputs)

            with mock.patch(
                "budget.cli.rebuild_from_gold", rebuild_while_another_command_runs
            ):
                status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            ((second_status, second_stdout, second_stderr),) = overlapping
            assert (second_status, second_stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "another command is running" in second_stderr
            with GoldStore(built.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]


class FromSilverTests(unittest.TestCase):
    def test_rebuild_from_silver_rebuilds_silver_then_publishes_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)
            with SilverStore(built.profile) as silver:
                assert silver.read().transactions == ()

            status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "1 admitted" in stdout
            assert "published publication 1" in stdout
            with SilverStore(built.profile) as silver:
                assert [t.description for t in silver.read().transactions] == ["Café"]
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                transactions = gold.open(current.publication_id).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
                assert [t.description for t in transactions] == ["Café"]


class RecipeNamesSilversRunsTests(unittest.TestCase):
    def test_a_refused_run_silver_never_consumed_publishes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            # Bronze refuses a declaration that ends after the export date.
            present_again(built.profile, "danske-20260312.csv", date(2026, 3, 20))

            rebuild_silver_with(built.profile)

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(built.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]

    def test_a_repeat_run_with_a_new_export_date_is_named_with_its_payload(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            repeat = present_again(
                built.profile, "danske-20260310.csv", date(2026, 3, 9)
            )

            rebuild_silver_with(built.profile)

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            payload = sha256(EXPORT).hexdigest()
            with GoldStore(built.profile) as gold:
                assert gold.recipe(2).import_runs == {
                    RecipeImportRun(built.import_run_id, payload),
                    RecipeImportRun(repeat, payload),
                }


class SilverChangeTests(unittest.TestCase):
    def test_a_retracted_silver_decision_requires_rebuild_then_publishes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            withdrawal = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "synthetic withdrawal",
                "supersedes": [],
            }
            log = built.profile.input_file("decisions.jsonl")
            log.write_text(json.dumps(withdrawal) + "\n", encoding="utf-8")
            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                before = gold.pointer_history()

            retraction = {
                "format": 1,
                "entry": 2,
                "decision_id": "d-0002",
                "recorded_at": "2026-04-10T17:02:12Z",
                "kind": "retract",
                "targets": [],
                "reason": "synthetic correction",
                "supersedes": ["d-0001"],
            }
            with log.open("a", encoding="utf-8") as decision_log:
                decision_log.write(json.dumps(retraction) + "\n")

            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == before
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1

            status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.recipe(2).silver_decisions == ()

    def test_a_superseding_silver_decision_requires_rebuild_then_publishes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            evidence = next(
                item
                for item in context.result.transaction_evidence
                if item.transaction_id == transaction_id
            )
            withdrawal = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "synthetic withdrawal",
                "supersedes": [],
            }
            log = built.profile.input_file("decisions.jsonl")
            log.write_text(json.dumps(withdrawal) + "\n", encoding="utf-8")
            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK

            same_transaction = {
                "format": 1,
                "entry": 2,
                "decision_id": "d-0002",
                "recorded_at": "2026-04-10T17:02:12Z",
                "kind": "same-transaction",
                "targets": [transaction_id],
                "reason": "synthetic re-presentation",
                "supersedes": ["d-0001"],
                "record": {
                    "payload_id": evidence.payload_id,
                    "record_ordinal": evidence.record_ordinal,
                },
            }
            with log.open("a", encoding="utf-8") as decision_log:
                decision_log.write(json.dumps(same_transaction) + "\n")

            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "rebuild --from silver" in stderr
            # `rebuild --from silver` published 1; the refusal adds nothing.
            with GoldStore(built.profile) as gold:
                history = gold.pointer_history()
                assert [m.to_publication_id for m in history] == [1]

            status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.recipe(2).silver_decisions == (
                    SameTransaction(
                        "d-0002",
                        transaction_id,
                        evidence.payload_id,
                        evidence.record_ordinal,
                    ),
                )

    def test_voided_only_input_still_requires_its_consumed_currency(self) -> None:
        cases = ("changed", "removed")
        for case in cases:
            with self.subTest(case), TemporaryDirectory() as directory:
                built = household(Path(directory))
                decision = {
                    "format": 1,
                    "entry": 1,
                    "decision_id": "d-0001",
                    "recorded_at": "2026-04-10T17:02:11Z",
                    "kind": "void-import-run",
                    "targets": [built.import_run_id],
                    "reason": "synthetic mistaken run",
                    "supersedes": [],
                }
                built.profile.input_file("decisions.jsonl").write_text(
                    json.dumps(decision) + "\n",
                    encoding="utf-8",
                )
                assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
                accounts = built.profile.accounts_file.read_text(encoding="utf-8")
                if case == "changed":
                    changed = accounts.replace(
                        'currency = "DKK"', 'currency = "EUR"', 1
                    )
                else:
                    savings = accounts.index("[account.joint-savings]")
                    changed = "format = 1\n\n" + accounts[savings:]
                built.profile.accounts_file.write_text(changed, encoding="utf-8")

                status, stdout, stderr = rebuild(built.profile_file)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert stdout == ""
                assert "consumed currency" in stderr
                assert "rebuild --from silver" in stderr
                # `rebuild --from silver` published 1; the refusal adds nothing.
                with GoldStore(built.profile) as gold:
                    history = gold.pointer_history()
                    assert [m.to_publication_id for m in history] == [1]

    def test_a_carriage_return_prefix_hashes_the_exact_lf_delimited_entry(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "classify",
                "targets": [context.result.transactions[0].transaction_id],
                "category": "groceries",
                "reason": "synthetic classification",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                "\r" + json.dumps(decision) + "\n",
                encoding="utf-8",
            )

            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK

            # A later Gold rebuild compares the stored prefix with the log's.
            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 1 stays current" in stdout

    def test_retry_after_silver_commits_and_gold_fails(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "synthetic withdrawal",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                json.dumps(decision) + "\n",
                encoding="utf-8",
            )

            with closing(sqlite3.connect(built.profile.gold_store)) as connection:
                connection.execute(
                    "CREATE TRIGGER refuse_result BEFORE INSERT ON results"
                    " BEGIN SELECT RAISE(ABORT, 'synthetic Gold failure'); END"
                )
                connection.commit()
            # Silver commits the withdrawal before Gold's publication fails.
            with pytest.raises(sqlite3.IntegrityError):
                rebuild(built.profile_file, "--from", "silver")
            with SilverStore(built.profile) as silver_store:
                committed = silver_store.read_build().provenance
            assert committed is not None
            assert [d.decision_id for d in committed.decisions] == ["d-0001"]
            with closing(sqlite3.connect(built.profile.gold_store)) as connection:
                connection.execute("DROP TRIGGER refuse_result")
                connection.commit()

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 2

    def test_changed_silver_under_the_same_runs_publishes_a_new_gold_result(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                original_recipe = gold.recipe(1)
            with SilverStore(built.profile) as silver_store:
                original = silver_store.read_build()
                assert original.provenance is not None
                changed_result = replace(
                    original.result,
                    transactions=tuple(
                        replace(transaction, description="CHANGED")
                        for transaction in original.result.transactions
                    ),
                )
                changed = replace(
                    original.provenance,
                    result_fingerprint=result_fingerprint(
                        changed_result,
                        currencies=original.provenance.currencies,
                    ),
                )
                silver_store.replace(
                    changed_result,
                    currencies=original.currencies,
                    provenance=changed,
                )

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                first = gold.recipe(1)
                second = gold.recipe(2)
            assert first == original_recipe
            assert first.import_runs == second.import_runs
            assert first.silver_result_fingerprint != second.silver_result_fingerprint

    def test_changing_a_consumed_account_currency_refuses_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            accounts = built.profile.accounts_file.read_text(encoding="utf-8")
            built.profile.accounts_file.write_text(
                accounts.replace('currency = "DKK"', 'currency = "EUR"', 1),
                encoding="utf-8",
            )

            try:
                result = rebuild(built.profile_file)
            except UnknownCurrencyError:
                result = None

            assert result is not None
            status, stdout, stderr = result
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "consumed currency" in stderr
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2

    def test_a_replaced_consumed_decision_log_prefix_refuses_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "classify",
                "targets": [transaction_id],
                "category": "groceries",
                "reason": "synthetic classification",
                "supersedes": [],
            }
            log = built.profile.input_file("decisions.jsonl")
            log.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
            assert rebuild(built.profile_file)[0] == EXIT_OK

            replacement = json.dumps(decision | {"recorded_at": "2026-04-10T17:02:12Z"})
            log.write_text(replacement + "\n", encoding="utf-8")
            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "decision-log prefix" in stderr
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2

    def test_a_truncated_consumed_decision_log_prefix_refuses_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "classify",
                "targets": [transaction_id],
                "category": "groceries",
                "reason": "synthetic classification",
                "supersedes": [],
            }
            log = built.profile.input_file("decisions.jsonl")
            log.write_text(json.dumps(decision) + "\n", encoding="utf-8")
            assert rebuild(built.profile_file, "--from", "silver")[0] == EXIT_OK
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                before = gold.pointer_history()

            log.write_bytes(log.read_bytes()[:20])
            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "decision-log prefix" in stderr
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == before
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2

    def test_an_unapplied_silver_decision_refuses_gold_before_publishing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with SilverStore(built.profile) as silver_store:
                context = silver_store.read_build()
            transaction_id = context.result.transactions[0].transaction_id
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "synthetic withdrawal",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                json.dumps(decision) + "\n",
                encoding="utf-8",
            )

            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1
                assert gold.next_publication_id() == 2

    def test_a_voided_run_changes_silver_and_publishes_a_new_publication(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            decision = {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "void-import-run",
                "targets": [built.import_run_id],
                "reason": "synthetic mistaken run",
                "supersedes": [],
            }
            built.profile.input_file("decisions.jsonl").write_text(
                json.dumps(decision) + "\n",
                encoding="utf-8",
            )

            status, stdout, stderr = rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.recipe(2).import_runs == frozenset(
                    {RecipeImportRun(built.import_run_id, sha256(EXPORT).hexdigest())}
                )
                transactions = gold.open(2).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
            assert transactions == ()


class NeverBuiltSilverTests(unittest.TestCase):
    def test_future_silver_provenance_is_refused_by_an_older_gold_consumer(
        self,
    ) -> None:
        cases = {
            "fingerprint scheme": (
                "UPDATE silver_builds SET fingerprint_scheme = '999'",
            ),
            "identity contract": ("UPDATE silver_builds SET identity_version = '999'",),
        }
        for name, (statement,) in cases.items():
            with self.subTest(name), TemporaryDirectory() as directory:
                built = household(Path(directory))
                with closing(sqlite3.connect(built.profile.silver_store)) as store:
                    store.execute(statement)
                    store.commit()

                status, stdout, stderr = rebuild(built.profile_file)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert stdout == ""
                assert "Silver provenance" in stderr
                assert "rebuild --from silver" in stderr
                with GoldStore(built.profile) as gold:
                    assert gold.current() is None
                    assert gold.pointer_history() == ()

    def test_unknown_silver_provenance_refuses_gold(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            with SilverStore(built.profile) as store:
                store.replace(
                    SilverResult((), (), (), (), (), (), (), ()),
                    currencies={"joint-current": "DKK"},
                )

            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "no trustworthy build provenance" in stderr
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.current() is None
                assert gold.next_publication_id() == 1

    def test_a_gold_rebuild_over_a_silver_never_built_refuses(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), silver=False)

            status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "rebuild --from silver" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.current() is None


class LateBookingWindowTests(unittest.TestCase):
    def test_a_changed_window_alone_publishes_and_each_recipe_keeps_its_own(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 14\n")

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.recipe(1).late_booking_days == 7
                assert gold.recipe(2).late_booking_days == 14


class EmptyAccountTests(unittest.TestCase):
    def test_adding_an_empty_account_publishes_without_a_silver_rebuild(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            accounts = built.profile.accounts_file.read_text(encoding="utf-8")
            built.profile.accounts_file.write_text(
                accounts
                + """

[account.joint-empty]
display_name = "Joint empty"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
""",
                encoding="utf-8",
            )

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(built.profile) as gold:
                assert {account.account_id for account in gold.open(2).accounts()} >= {
                    "joint-current",
                    "joint-empty",
                }


class RoutineLogTests(unittest.TestCase):
    def test_the_routine_log_counts_whether_the_rebuild_published(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))

            assert rebuild(built.profile_file)[0] == EXIT_OK
            assert rebuild(built.profile_file)[0] == EXIT_OK

            lines = built.profile.log_file("commands.jsonl").read_text(encoding="utf-8")
            records = [json.loads(line) for line in lines.splitlines()]
            assert [(r["command"], r["counts"]) for r in records] == [
                ("rebuild", {"published": 1}),
                ("rebuild", {"published": 0}),
            ]


class EarlierRecipeKeepsItsWindowTests(unittest.TestCase):
    def test_an_earlier_recipe_still_reads_back_the_window_it_was_built_with(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 0\n")
            assert rebuild(built.profile_file)[0] == EXIT_OK

            with GoldStore(built.profile) as gold:
                assert gold.recipe(1).late_booking_days == 7
                assert gold.recipe(2).late_booking_days == 0


if __name__ == "__main__":
    unittest.main()
