# Copyright 2026 Therkel
"""`budget rebuild` through the lifecycle of `publications.md`, step by step.

The household's exports and inputs are `tests/cli/lifecycle.py`; each change
the lifecycle names is made as the household would make it, and the
publication it gives is read back through `GoldStore`.
"""

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.lifecycle import (
    at_second_publication,
    correct_ikea_to_gifts,
    february_by_category,
    import_run_2,
    lifecycle,
    retract_the_correction,
)

EXIT_OK = 0
# The lifecycle's rule change: `NET` also means groceries, at the same priority
# as `r-streaming`, which disagrees about NETFLIX.
R_NET = """
[[rule]]
id = "r-net"
when.description_contains = "NET"
then.category = "groceries"
"""


class FirstTwoPublicationsTests(unittest.TestCase):
    def test_the_lifecycles_first_two_publications_have_their_figures(self) -> None:
        with TemporaryDirectory() as directory:
            household = lifecycle(Path(directory))
            assert rebuild(household.profile_file)[0] == EXIT_OK
            import_run_2(household.profile)
            assert rebuild(household.profile_file)[0] == EXIT_OK

            with GoldStore(household.profile) as gold:
                assert [each.publication_id for each in gold.available()] == [1, 2]
                assert february_by_category(gold.open(1)) == {
                    "groceries": Decimal("-520.00"),
                    "household-goods": Decimal("-2400.00"),
                    "streaming": Decimal("-129.00"),
                }
                assert february_by_category(gold.open(2)) == {
                    "groceries": Decimal("-820.00"),
                    "household-goods": Decimal("-2400.00"),
                    "streaming": Decimal("-129.00"),
                }


class CategoryCorrectionTests(unittest.TestCase):
    def test_a_category_correction_publishes_the_lifecycles_third_publication(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            household = at_second_publication(Path(directory))
            correct_ikea_to_gifts(household.profile)

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 3" in stdout
            with GoldStore(household.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 3
                assert gold.recipe(3).decision_log_position == 1
                assert february_by_category(gold.open(3)) == {
                    "groceries": Decimal("-820.00"),
                    "gifts": Decimal("-2400.00"),
                    "streaming": Decimal("-129.00"),
                }


class RuleChangeTests(unittest.TestCase):
    def test_a_rule_change_publishes_the_lifecycles_fourth_publication(self) -> None:
        with TemporaryDirectory() as directory:
            household = at_second_publication(Path(directory))
            correct_ikea_to_gifts(household.profile)
            assert rebuild(household.profile_file)[0] == EXIT_OK
            rules = household.profile.input_file("rules.toml")
            rules.write_text(
                rules.read_text(encoding="utf-8") + R_NET, encoding="utf-8"
            )

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 4" in stdout
            with GoldStore(household.profile) as gold:
                february = gold.open(4)
                assert february_by_category(february) == {
                    "groceries": Decimal("-820.00"),
                    "gifts": Decimal("-2400.00"),
                }
                (netflix,) = [
                    each
                    for each in february.transactions(
                        start_date=date(2026, 2, 1), end_date=date(2026, 2, 28)
                    )
                    if each.description == "NETFLIX.COM"
                ]
                assert netflix.transaction_type == "unknown"


class RetractedDecisionTests(unittest.TestCase):
    def test_a_decision_added_and_retracted_gives_the_earlier_result(self) -> None:
        with TemporaryDirectory() as directory:
            household = at_second_publication(Path(directory))
            with GoldStore(household.profile) as gold:
                second = gold.current()
            assert second is not None
            correct_ikea_to_gifts(household.profile)
            assert rebuild(household.profile_file)[0] == EXIT_OK
            retract_the_correction(household.profile)

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 4" in stdout
            with GoldStore(household.profile) as gold:
                third, fourth = gold.available()
                assert (third.publication_id, fourth.publication_id) == (3, 4)
                assert gold.recipe(4).decision_log_position == 2
                assert gold.recipe(4) != gold.recipe(2)
                assert third.result_fingerprint != second.result_fingerprint
                assert fourth.result_fingerprint == second.result_fingerprint


if __name__ == "__main__":
    unittest.main()
