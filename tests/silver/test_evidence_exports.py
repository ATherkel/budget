# Copyright 2026 Therkel
"""Silver passes on each run counted in evidence: its export date and range.

Gold settles late bookings from these (`gold-layer.md`, *Late bookings
settled*), so it never reads Bronze. Every export here is synthetic.
"""

from datetime import date

from budget.silver import EvidenceExport
from tests.silver.exports import ACCOUNT, build_from, export, repeat, row


def test_exactly_the_runs_behind_the_evidence_ranges_are_passed_on() -> None:
    admitted = export(
        [row("02.03.2026", "NETTO", "-45,00", "955,00")],
        run_id="run-a",
        exported_on=date(2026, 3, 5),
    )
    quiet_again = repeat(
        admitted,
        run_id="run-a2",
        exported_on=date(2026, 4, 10),
        covers_through=date(2026, 4, 3),
    )
    broken = export(
        [row("04.03.2026", "FOETEX", "-12,00", "x")],
        run_id="run-x",
        exported_on=date(2026, 3, 6),
    )
    broken_again = repeat(broken, run_id="run-x2", exported_on=date(2026, 4, 11))

    result = build_from(admitted, quiet_again, broken, broken_again)

    # The quarantined run and its repeat are no evidence, so neither is passed on.
    assert result.evidence_exports == (
        EvidenceExport(
            account_id=ACCOUNT,
            exported_on=date(2026, 3, 5),
            covers_from=date(2026, 3, 2),
            covers_through=date(2026, 3, 5),
        ),
        EvidenceExport(
            account_id=ACCOUNT,
            exported_on=date(2026, 4, 10),
            covers_from=date(2026, 3, 2),
            covers_through=date(2026, 4, 3),
        ),
    )
