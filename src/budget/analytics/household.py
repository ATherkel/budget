# Copyright 2026 Therkel
"""The production household-report adapter over Gold publications."""

from typing import Final

from budget.analytics.reports import ReportPublication
from budget.gold import GoldPublications


class NothingPublishedError(LookupError):
    """Gold has no current publication whose result is retained."""

    def __init__(self) -> None:
        """Say that no publication exists."""
        super().__init__("nothing is published: Gold has no current publication")


NOTHING_PUBLISHED: Final = NothingPublishedError()


class HouseholdReports:
    """Reports resolved from and pinned to the publications in one Gold store."""

    def __init__(self, publications: GoldPublications) -> None:
        """Read reports from `publications`."""
        self._publications = publications

    def current_publication(self) -> ReportPublication:
        """Return the current publication's report identity."""
        raise NotImplementedError(NOTHING_PUBLISHED)
