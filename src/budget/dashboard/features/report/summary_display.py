# Copyright 2026 Therkel
"""Overview summary cards prepared for display, so one macro renders them all.

Indtægter, Udgifter, Overførsler and Ukategoriseret are the same card: a
label, the totals it shows and the rows behind them. Only the data differs, so
every choice about which rows belong where and how they read is made here.
"""

from collections.abc import Callable
from dataclasses import dataclass

from budget.analytics import MonthlyOverview, OverviewContributor
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
class SummaryCellView:
    """One formatted table cell, labelled for the phone layout."""

    label: str
    text: str
    numeric: bool = False
    account: str | None = None


@dataclass(frozen=True)
class SummaryColumnView:
    """One column heading; amount columns align like their cells."""

    label: str
    numeric: bool = False


type SummaryRowView = tuple[SummaryCellView, ...]


@dataclass(frozen=True)
class SummaryCardView:
    """One expandable summary card: its totals and the rows behind them.

    A card shows either one `headline` total beside its label, or
    `directions`, money in and money out on rows of their own, never netted.
    """

    label: str
    element_id: str | None
    headline: SummaryTotalView | None
    directions: tuple[SummaryTotalView, ...]
    columns: tuple[SummaryColumnView, ...]
    rows: tuple[SummaryRowView, ...]
    empty_message: str


@dataclass(frozen=True)
class SummaryView:
    """The overview's movement cards and its Ukategoriseret card."""

    movements: tuple[SummaryCardView, ...]
    unclassified: SummaryCardView


type _Cells = Callable[[OverviewContributor, str], SummaryRowView]

_CONTRIBUTOR_COLUMNS = (
    SummaryColumnView("Dato"),
    SummaryColumnView("Tekst"),
    SummaryColumnView("Bankbeløb", numeric=True),
    SummaryColumnView("Bidrag", numeric=True),
)
_UNCLASSIFIED_COLUMNS = (
    SummaryColumnView("Dato"),
    SummaryColumnView("Tekst"),
    SummaryColumnView("Konto"),
    SummaryColumnView("Retning"),
    SummaryColumnView("Bankbeløb", numeric=True),
)


def _contributor_cells(row: OverviewContributor, currency: str) -> SummaryRowView:
    return (
        SummaryCellView("Dato", danish_date(row.transaction_date)),
        SummaryCellView("Tekst", row.description, account=row.account_display_name),
        SummaryCellView("Bankbeløb", signed_amount(row.amount, currency), numeric=True),
        SummaryCellView(
            "Bidrag", signed_amount(row.contribution, currency), numeric=True
        ),
    )


def _unclassified_cells(row: OverviewContributor, currency: str) -> SummaryRowView:
    return (
        SummaryCellView("Dato", danish_date(row.transaction_date)),
        SummaryCellView("Tekst", row.description),
        SummaryCellView("Konto", row.account_display_name),
        SummaryCellView("Retning", "Ind" if row.amount > 0 else "Ud"),
        SummaryCellView("Bankbeløb", signed_amount(row.amount, currency), numeric=True),
    )


def _incoming_first(
    rows: tuple[OverviewContributor, ...],
) -> tuple[OverviewContributor, ...]:
    """Return money in before money out, each side keeping its newest-first order."""
    return tuple(row for row in rows if row.amount > 0) + tuple(
        row for row in rows if row.amount <= 0
    )


@dataclass(frozen=True)
class _Card:
    """What sets one card apart; `rows` is None when the month has no data."""

    label: str
    empty_message: str
    rows: tuple[OverviewContributor, ...] | None
    headline: SummaryTotalView | None = None
    directions: tuple[SummaryTotalView, ...] = ()
    element_id: str | None = None
    columns: tuple[SummaryColumnView, ...] = _CONTRIBUTOR_COLUMNS
    cells: _Cells = _contributor_cells


def _card_view(card: _Card, currency: str) -> SummaryCardView:
    return SummaryCardView(
        label=card.label,
        element_id=card.element_id,
        headline=card.headline,
        directions=card.directions,
        columns=card.columns,
        rows=tuple(card.cells(row, currency) for row in card.rows or ()),
        empty_message=NO_DATA if card.rows is None else card.empty_message,
    )


def summary_view(overview: MonthlyOverview) -> SummaryView:
    """Return the overview's summary cards, every one in the same shape."""
    currency = overview.currency
    movements = overview.movements
    unclassified = overview.unclassified
    cards = (
        _Card(
            "Indtægter",
            "Ingen indtægter i måneden.",
            movements.income if movements else None,
            headline=SummaryTotalView("income", amount(overview.income, currency)),
        ),
        _Card(
            "Udgifter",
            "Ingen udgifter i måneden.",
            movements.expenses if movements else None,
            headline=SummaryTotalView("expenses", amount(overview.expenses, currency)),
        ),
        _Card(
            "Overførsler",
            "Ingen overførsler i måneden.",
            movements.transfers if movements else None,
            headline=SummaryTotalView(
                "transfers-summary",
                signed_amount(
                    movements.transfer_total if movements else None, currency
                ),
            ),
        ),
    )
    unclassified_card = _Card(
        "Ukategoriseret",
        "Ingen ukategoriserede posteringer i måneden.",
        _incoming_first(movements.unclassified) if movements else None,
        directions=(
            SummaryTotalView(
                "unclassified-in",
                signed_amount(
                    unclassified.money_in if unclassified else None, currency
                ),
                "Ind",
            ),
            SummaryTotalView(
                "unclassified-out",
                signed_amount(
                    unclassified.money_out if unclassified else None, currency
                ),
                "Ud",
            ),
        ),
        element_id="unclassified",
        columns=_UNCLASSIFIED_COLUMNS,
        cells=_unclassified_cells,
    )
    return SummaryView(
        movements=tuple(_card_view(card, currency) for card in cards),
        unclassified=_card_view(unclassified_card, currency),
    )
