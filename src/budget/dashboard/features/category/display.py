# Copyright 2026 Therkel
"""What the category page prints, prepared so its template only loops and prints."""

from dataclasses import dataclass

from budget.analytics import SpendingDetail, SpendingDetailRow
from budget.dashboard.display.notices import Notice, shown

# A group's rows name the Category each one belongs to.
_CATEGORY_COLUMN = "Kategori"


@dataclass(frozen=True)
class DetailRow:
    """One row of the detail table and the cells only a group's table has."""

    row: SpendingDetailRow
    category_cells: tuple[str, ...]


def subject_notices(detail: SpendingDetail) -> tuple[Notice, ...]:
    """Return the link from a Category to its whole group; a group has none."""
    return shown(
        (detail.subject.kind != "group", Notice("category/group_link.html")),
    )


def trust_notices(detail: SpendingDetail) -> tuple[Notice, ...]:
    """Return the notes on how far the detail's figures can be trusted, in order."""
    return shown(
        (detail.provisional is not None, Notice("category/provisional_note.html")),
        (detail.coverage.status != "complete", Notice("category/coverage_note.html")),
    )


def category_column(detail: SpendingDetail) -> tuple[str, ...]:
    """Return the heading of the Category column, which only a group's table has."""
    return (_CATEGORY_COLUMN,) if detail.subject.kind == "group" else ()


def detail_rows(detail: SpendingDetail) -> tuple[DetailRow, ...]:
    """Return the detail's rows in its order, with a group's Category cell."""
    is_group = detail.subject.kind == "group"
    return tuple(
        DetailRow(row, (row.category_name,) if is_group else ()) for row in detail.rows
    )
