# Copyright 2026 Therkel
"""One card, the view model the `summary_card` macro in `report/card.html` renders.

A card is a label and its figures and, when it expands, the table behind them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Figure:
    """One figure in a card's head, with its direction in words when it has one."""

    name: str
    value: str
    direction: str = ""

    @property
    def attributes(self) -> dict[str, str]:
        """Return the attributes of the figure's value."""
        return {"id": self.name}

    @property
    def row_attributes(self) -> dict[str, str | None]:
        """Return the attributes of the figure with its direction."""
        return {"id": f"{self.name}-row" if self.direction else None}


@dataclass(frozen=True)
class Column:
    """One column of a card's table; amounts align right."""

    label: str
    numeric: bool = False

    @property
    def attributes(self) -> dict[str, str | None]:
        """Return the attributes of the column's heading."""
        return {"class": "detail-amount" if self.numeric else None}


@dataclass(frozen=True)
class Cell:
    """One cell, labelled by its column where a phone stacks the row."""

    column: Column
    text: str

    @property
    def attributes(self) -> dict[str, str | None]:
        """Return the attributes of the cell."""
        return {"data-label": self.column.label, **self.column.attributes}


@dataclass(frozen=True)
class Table:
    """The rows behind a card, or one line saying why there are none."""

    label: str
    columns: tuple[Column, ...]
    rows: tuple[tuple[Cell, ...], ...]
    empty: str

    @property
    def no_rows(self) -> tuple[str, ...]:
        """Return the line shown in place of rows when there are none."""
        return () if self.rows else (self.empty,)

    @property
    def width(self) -> int:
        """Return how many columns the line in place of rows spans."""
        return len(self.columns)


@dataclass(frozen=True)
class Card:
    """One card: closed by default, and it expands only when it has a table.

    A card with one figure marks that figure by its name; one with several
    marks its head by the card's name instead.
    """

    name: str
    label: str
    figures: tuple[Figure, ...]
    tables: tuple[Table, ...] = ()

    @property
    def attributes(self) -> dict[str, str]:
        """Return the attributes of the card."""
        return {"id": f"{self.name}-card"}

    @property
    def head_attributes(self) -> dict[str, str | None]:
        """Return the attributes of the head that holds the label and figures."""
        return {"id": self.name if len(self.figures) > 1 else None}

    @property
    def element(self) -> str:
        """Return the card's element: a disclosure when it has a table."""
        return "details" if self.tables else "div"

    @property
    def head(self) -> str:
        """Return the head's element: the disclosure's summary when it expands."""
        return "summary" if self.tables else "div"
