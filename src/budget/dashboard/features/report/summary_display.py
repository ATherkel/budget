# Copyright 2026 Therkel
"""Overview summary cards prepared for display, so one macro renders them all.

Every summary group is the same card: a label, the totals it shows and the
rows behind them. `_CARDS` holds what differs per group, so a new group is one
entry there.
"""

from collections.abc import Callable
from dataclasses import dataclass

from budget.analytics import (
    MonthlyOverview,
    OverviewContributor,
    OverviewGroup,
    SummaryGroup,
)
from budget.dashboard.display.amounts import amount, signed_amount
from budget.dashboard.display.months import danish_date

NO_DATA = "Ingen data endnu; bidrag kan ikke vises."


@dataclass(frozen=True)
class SummaryTotalView:
    """One total on a card, with its direction when it shows one side only."""

    element_id: str
    value: str
    direction: str | None = None

    @property
    def row_id(self) -> str:
        """Return the id of the direction row that holds this total."""
        return f"{self.element_id}-row"


@dataclass(frozen=True)
class SummaryColumnView:
    """One column heading; amount columns align like their cells."""

    label: str
    numeric: bool = False


@dataclass(frozen=True)
class SummaryCellView:
    """One formatted table cell, labelled for the phone layout."""

    label: str
    text: str
    numeric: bool = False
    account: str | None = None


type SummaryRowView = tuple[SummaryCellView, ...]


@dataclass(frozen=True)
class SummaryCardView:
    """One summary card: its totals and, when it expands, the rows behind them.

    A card shows either one `headline` total beside its label, or
    `directions`, money in and money out on rows of their own, never netted.
    """

    label: str
    expandable: bool
    element_id: str | None
    headline: SummaryTotalView | None
    directions: tuple[SummaryTotalView, ...]
    columns: tuple[SummaryColumnView, ...]
    rows: tuple[SummaryRowView, ...]
    empty_message: str


@dataclass(frozen=True)
class SummaryView:
    """The summary cards before the account reconciliations and after them."""

    before_reconciliations: tuple[SummaryCardView, ...]
    after_reconciliations: tuple[SummaryCardView, ...]


type _Cells = Callable[[OverviewContributor, str], SummaryRowView]


def _contributor_cells(row: OverviewContributor, currency: str) -> SummaryRowView:
    return (
        SummaryCellView("Dato", danish_date(row.transaction_date)),
        SummaryCellView("Tekst", row.description, account=row.account_display_name),
        SummaryCellView("Bankbeløb", signed_amount(row.amount, currency), numeric=True),
        SummaryCellView(
            "Bidrag", signed_amount(row.contribution, currency), numeric=True
        ),
    )


def _direction_cells(row: OverviewContributor, currency: str) -> SummaryRowView:
    return (
        SummaryCellView("Dato", danish_date(row.transaction_date)),
        SummaryCellView("Tekst", row.description),
        SummaryCellView("Konto", row.account_display_name),
        SummaryCellView("Retning", "Ind" if row.amount > 0 else "Ud"),
        SummaryCellView("Bankbeløb", signed_amount(row.amount, currency), numeric=True),
    )


_CONTRIBUTOR_COLUMNS = (
    SummaryColumnView("Dato"),
    SummaryColumnView("Tekst"),
    SummaryColumnView("Bankbeløb", numeric=True),
    SummaryColumnView("Bidrag", numeric=True),
)
_DIRECTION_COLUMNS = (
    SummaryColumnView("Dato"),
    SummaryColumnView("Tekst"),
    SummaryColumnView("Konto"),
    SummaryColumnView("Retning"),
    SummaryColumnView("Bankbeløb", numeric=True),
)


@dataclass(frozen=True)
class _Card:
    """What sets one group's card apart.

    A `split` card shows money in and out separately, never netted, and lists
    money in before money out.
    """

    group: SummaryGroup
    label: str
    element_id: str
    empty_message: str
    signed: bool = False
    split: bool = False
    after_reconciliations: bool = False


_CARDS = (
    _Card("income", "Indtægter", "income", "Ingen indtægter i måneden."),
    _Card("expenses", "Udgifter", "expenses", "Ingen udgifter i måneden."),
    _Card(
        "transfers",
        "Overførsler",
        "transfers-summary",
        "Ingen overførsler i måneden.",
        signed=True,
    ),
    _Card(
        "unclassified",
        "Ukategoriseret",
        "unclassified",
        "Ingen ukategoriserede posteringer i måneden.",
        split=True,
        after_reconciliations=True,
    ),
)


def _directions(
    card: _Card, group: OverviewGroup | None, currency: str
) -> tuple[SummaryTotalView, ...]:
    flows = group.flows if group else None
    return (
        SummaryTotalView(
            f"{card.element_id}-in",
            signed_amount(flows.money_in if flows else None, currency),
            "Ind",
        ),
        SummaryTotalView(
            f"{card.element_id}-out",
            signed_amount(flows.money_out if flows else None, currency),
            "Ud",
        ),
    )


def _rows(card: _Card, group: OverviewGroup) -> tuple[OverviewContributor, ...]:
    if not card.split:
        return group.rows
    return tuple(row for row in group.rows if row.amount > 0) + tuple(
        row for row in group.rows if row.amount <= 0
    )


def _card_view(
    card: _Card, group: OverviewGroup | None, currency: str
) -> SummaryCardView:
    """Return one group's card; `group` is None when the month has no data."""
    total = group.total if group else None
    shown = signed_amount(total, currency) if card.signed else amount(total, currency)
    cells: _Cells = _direction_cells if card.split else _contributor_cells
    return SummaryCardView(
        label=card.label,
        expandable=True,
        element_id=card.element_id if card.split else None,
        headline=None if card.split else SummaryTotalView(card.element_id, shown),
        directions=_directions(card, group, currency) if card.split else (),
        columns=_DIRECTION_COLUMNS if card.split else _CONTRIBUTOR_COLUMNS,
        rows=tuple(cells(row, currency) for row in _rows(card, group)) if group else (),
        empty_message=card.empty_message if group else NO_DATA,
    )


def _money_left(overview: MonthlyOverview) -> SummaryCardView:
    """Return Penge tilbage, a figure without rows of its own."""
    return SummaryCardView(
        label="Penge tilbage",
        expandable=False,
        element_id=None,
        headline=SummaryTotalView(
            "money-left", amount(overview.net_cash_flow, overview.currency)
        ),
        directions=(),
        columns=(),
        rows=(),
        empty_message="",
    )


def summary_view(overview: MonthlyOverview) -> SummaryView:
    """Return the overview's summary cards, every one in the same shape."""
    movements = overview.movements

    def view(card: _Card) -> SummaryCardView:
        group = movements.group(card.group) if movements else None
        return _card_view(card, group, overview.currency)

    return SummaryView(
        before_reconciliations=tuple(
            view(card) for card in _CARDS if not card.after_reconciliations
        ),
        after_reconciliations=(
            _money_left(overview),
            *(view(card) for card in _CARDS if card.after_reconciliations),
        ),
    )
