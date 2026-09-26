# Copyright 2026 Therkel
"""Merging one account's exports, verified by their balances (ADR-009)."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from budget.silver.identity import transaction_id
from budget.silver.reading import Key, ReadRun, Row


@dataclass(frozen=True)
class Verdict:
    """What admitting a run would drop, and where its balances disagree."""

    dropped: tuple[tuple[Key, int], ...]  # (key, occurrence) of each drop
    # Each disagreeing date, with the admitted payload it was compared to.
    disagreements: tuple[tuple[date, str], ...]

    @property
    def clean(self) -> bool:
        """Whether the run can be admitted without a person's decision."""
        return not self.dropped and not self.disagreements


@dataclass
class Ledger:
    """One account's admitted transactions and each date's selected export."""

    account_id: str
    counts: dict[Key, int] = field(default_factory=dict)
    selected: dict[date, ReadRun] = field(default_factory=dict)
    admitted: list[ReadRun] = field(default_factory=list)
    # Transactions a *withdrawn* decision removed, as (key, occurrence).
    withdrawn: set[tuple[Key, int]] = field(default_factory=set)

    def verdict(self, run: ReadRun) -> Verdict:
        """Check `run` against what is admitted, without admitting it."""
        shown = Counter(row.key for row in run.booked)
        dropped = tuple(
            (key, k)
            for key, admitted in sorted(self.counts.items())
            if run.covers(key[0])
            for k in range(shown[key] + 1, admitted + 1)
            if (key, k) not in self.withdrawn
        )
        changes = self._added(shown)
        for key, _ in dropped:
            changes[key[0]] = changes.get(key[0], Decimal(0)) - key[1]
        return Verdict(dropped=dropped, disagreements=self._disagreements(run, changes))

    def admit(self, run: ReadRun, withdrawn: Iterable[tuple[Key, int]] = ()) -> None:
        """Keep the highest count per key; `run` becomes its dates' export.

        `run` shows every transaction kept on the dates it covers, so it is
        the selected export for each of them, including a date whose
        transactions it all dropped (ADR-017). `withdrawn` leave the ledger.
        """
        for key, shown in Counter(row.key for row in run.booked).items():
            self.counts[key] = max(self.counts.get(key, 0), shown)
        covered = [day for day in self.selected if run.covers(day)]
        for day in [*covered, *run.end_of_day]:
            self.selected[day] = run
        self.withdrawn.update(withdrawn)
        self.admitted.append(run)

    def is_kept(self, key: Key, occurrence: int) -> bool:
        """Whether the transaction is admitted and not withdrawn."""
        return (
            occurrence <= self.counts.get(key, 0)
            and (key, occurrence) not in self.withdrawn
        )

    def _added(self, shown: Counter[Key]) -> dict[date, Decimal]:
        """Sum, per date, the amounts `shown` adds to what is admitted."""
        changes: dict[date, Decimal] = {}
        for key, count in shown.items():
            extra = count - self.counts.get(key, 0)
            if extra > 0:
                changes[key[0]] = changes.get(key[0], Decimal(0)) + key[1] * extra
        return changes

    def _disagreements(
        self, run: ReadRun, changes: dict[date, Decimal]
    ) -> tuple[tuple[date, str], ...]:
        """Dates both sides state a balance whose difference is unexplained.

        The difference on a date must equal every change on or before it:
        *explained growth*. A null balance states none (ADR-016).
        """
        stated = run.end_of_day
        cumulative = Decimal(0)
        found: list[tuple[date, str]] = []
        for day in sorted(changes.keys() | stated.keys()):
            cumulative += changes.get(day, Decimal(0))
            theirs = stated.get(day)
            selected = self.selected.get(day)
            ours = None if selected is None else selected.end_of_day.get(day)
            if theirs is None or ours is None or selected is None:
                continue
            if theirs - ours != cumulative:
                found.append((day, selected.run.payload_id))
        return tuple(found)

    def kept(self) -> list[tuple[str, Row, int]]:
        """Every admitted transaction in order: identifier, row, day sequence.

        Each date's order and values come from its selected export. A kept
        transaction that export does not show is appended after the date's
        rows in `transaction_id` order, with the row of the latest admitted
        export that shows it (`silver-layer.md`, *Canonical Transaction*).
        """
        return [
            entry
            for day, run in sorted(self.selected.items())
            for entry in self._kept_on(day, run)
        ]

    def _kept_on(self, day: date, run: ReadRun) -> list[tuple[str, Row, int]]:
        rows = [
            row
            for row in run.booked
            if row.key[0] == day and self.is_kept(row.key, row.occurrence)
        ]
        shown = {(row.key, row.occurrence) for row in rows}
        unshown = sorted(
            (self.identify(key, k), self._latest_row(key, k))
            for key, count in self.counts.items()
            if key[0] == day
            for k in range(1, count + 1)
            if (key, k) not in shown and self.is_kept(key, k)
        )
        return [
            (self.identify(row.key, row.occurrence), row, row.position) for row in rows
        ] + [
            (identifier, row, len(rows) + n)
            for n, (identifier, row) in enumerate(unshown, start=1)
        ]

    def identify(self, key: Key, occurrence: int) -> str:
        """Identify the `occurrence`th transaction with `key`."""
        transaction_date, amount, description = key
        return transaction_id(
            self.account_id, transaction_date, amount, description, occurrence
        )

    def _latest_row(self, key: Key, occurrence: int) -> Row:
        return next(
            row
            for run in reversed(self.admitted)
            for row in run.booked
            if (row.key, row.occurrence) == (key, occurrence)
        )
