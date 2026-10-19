# Copyright 2026 Therkel
"""`HouseholdReports`: the report interface of `report-contract.md` over Gold."""

from budget.analytics.reports import ReportPublication
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
            raise NotImplementedError
        return ReportPublication(
            publication_id=publication.publication_id,
            kind=publication.kind,
            label=publication.label,
            known_at=publication.known_at,
            is_current=True,
        )
