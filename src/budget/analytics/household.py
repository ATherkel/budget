# Copyright 2026 Therkel
"""`HouseholdReports`: the report interface of `report-contract.md` over Gold."""

from datetime import date

from budget.analytics import overview
from budget.analytics.reports import (
    MonthlyOverview,
    NothingPublishedError,
    ReportContext,
    ReportPublication,
    SelectionOptions,
)
from budget.gold import GoldPublications


class HouseholdReports:
    """Household reports from the publications of one Gold store."""

    def __init__(self, publications: GoldPublications) -> None:
        """Answer from `publications`, opening one publication per report."""
        self._publications = publications

    def current_publication(self) -> ReportPublication:
        """Return the current publication."""
        publication = self._publications.current()
        if publication is None:
            raise NothingPublishedError
        return ReportPublication(
            publication_id=publication.publication_id,
            kind=publication.kind,
            label=publication.label,
            known_at=publication.known_at,
            is_current=True,
        )

    def selection_options(
        self, publication_id: int, reference_date: date
    ) -> SelectionOptions:
        """Return what a page may select in one publication on one date."""
        gold = self._publications.open(publication_id)
        return overview.selection_options(
            gold, reference_date, is_current=self._is_current(publication_id)
        )

    def _is_current(self, publication_id: int) -> bool:
        current = self._publications.current()
        return current is not None and current.publication_id == publication_id

    def monthly_overview(self, context: ReportContext) -> MonthlyOverview:
        """Return the monthly overview of the publication `context` names.

        Whether that publication is current is judged on every call, so a page
        pinned to it learns when a newer build has become current.
        """
        gold = self._publications.open(context.publication_id)
        return overview.monthly_overview(
            gold, context, is_current=self._is_current(context.publication_id)
        )
