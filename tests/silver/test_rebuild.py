# Copyright 2026 Therkel
"""Rebuilding Silver from Bronze inputs into the profile's store.

The build itself is `tests/silver/`'s existing subject; this module covers the
step that puts its result in `silver.db`: the writer lock, one replacement, and
the `SilverResult` the caller gets back.
"""

import unittest
from datetime import date
from tempfile import TemporaryDirectory

from budget.profiles import test_profile as make_test_profile
from budget.silver import (
    SilverBuildInputs,
    SilverResult,
    SilverStore,
    build,
    rebuild_silver,
)
from budget.silver.storage import migrate_silver
from tests.silver.exports import Export, export, row

# A quiet first export, then one that adds a late booking the balances explain.
FIRST = export(
    [row("01.03.2026", "NETTO", "-45,00", "955,00")],
    run_id="run-a",
    exported_on=date(2026, 3, 5),
    covers_through=date(2026, 3, 4),
)
LATER = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "BIO", "-100,00", "855,00"),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
    covers_through=date(2026, 3, 8),
)


def _inputs(*exports: Export) -> SilverBuildInputs:
    """The one value a rebuild names its Bronze inputs in."""
    return SilverBuildInputs(
        runs=[each.run for each in exports],
        source_records={each.run.payload_id: each.records for each in exports},
        format_failures={each.run.payload_id: each.failures for each in exports},
        currencies={each.run.declared_account_id: "DKK" for each in exports},
    )


def _pure_build(inputs: SilverBuildInputs) -> SilverResult:
    """The same inputs through the unchanged pure `budget.silver.build`."""
    return build(
        runs=inputs.runs,
        source_records=inputs.source_records,
        format_failures=inputs.format_failures,
        currencies=inputs.currencies,
        decisions=inputs.decisions,
    )


class SilverRebuildTests(unittest.TestCase):
    def test_rebuild_silver_stores_what_the_pure_build_produces(self) -> None:
        inputs = _inputs(FIRST, LATER)
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            result = rebuild_silver(profile, inputs=inputs)

            assert result == _pure_build(inputs)
            with SilverStore(profile) as store:
                assert store.read() == result


if __name__ == "__main__":
    unittest.main()
