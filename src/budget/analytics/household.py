# Copyright 2026 Therkel
"""The production household-report adapter over Gold publications."""

from datetime import date

from budget.analytics.overview import selection_options as build_selection_options
from budget.analytics.reports import ReportPublication, SelectionOptions
from budget.gold import GoldPublication, GoldPublications


class NothingPublishedError(LookupError):
    """Gold has no current publication whose result is retained."""

    def __init__(self) -> None:
        """Say that no publication exists."""
        super().__init__("nothing is published: Gold has no current publication")


def _report_publication(
    publication: GoldPublication, *, is_current: bool
) -> ReportPublication:
    """Map Gold's publication metadata to the report contract."""
    return ReportPublication(
        publication_id=publication.publication_id,
        kind=publication.kind,
        label=publication.label,
        known_at=publication.known_at,
        is_current=is_current,
    )


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
        return _report_publication(publication, is_current=True)

    def selection_options(
        self, publication_id: int, reference_date: date
    ) -> SelectionOptions:
        """Return what can be selected in the requested publication."""
        gold = self._publications.open(publication_id)
        publication = gold.publication()
        current = self._publications.current()
        return build_selection_options(
            gold,
            reference_date,
            is_current=(
                current is not None
                and current.publication_id == publication.publication_id
            ),
        )
