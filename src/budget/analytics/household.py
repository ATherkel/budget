# Copyright 2026 Therkel
"""The production household-report adapter over Gold publications."""

from datetime import date

from budget.analytics.reports import ReportPublication, SelectionOptions
from budget.gold import GoldPublications


class NothingPublishedError(LookupError):
    """Gold has no current publication whose result is retained."""

    def __init__(self) -> None:
        """Say that no publication exists."""
        super().__init__("nothing is published: Gold has no current publication")


class HouseholdReports:
    """Reports resolved from and pinned to the publications in one Gold store."""

    def __init__(self, publications: GoldPublications) -> None:
        """Read reports from `publications`."""
        self._publications = publications

    def current_publication(self) -> ReportPublication:
        """Return the current publication's report identity."""
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
        """Return what can be selected in the requested publication."""
        raise NotImplementedError
