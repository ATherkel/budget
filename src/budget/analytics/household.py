# Copyright 2026 Therkel
"""The production household-report adapter over Gold publications."""

from dataclasses import replace
from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from budget.analytics.overview import monthly_overview as build_monthly_overview
from budget.analytics.overview import selection_options as build_selection_options
from budget.analytics.reports import (
    MonthlyOverview,
    ReportContext,
    ReportPublication,
    SelectionOptions,
)
from budget.gold import (
    GoldPublication,
    GoldPublications,
)
from budget.gold import (
    PublicationUnavailableError as GoldPublicationUnavailableError,
)


class NothingPublishedError(LookupError):
    """Gold has no current publication whose result is retained."""

    def __init__(self) -> None:
        """Say that no publication exists."""
        super().__init__("nothing is published: Gold has no current publication")


class PublicationUnavailableError(GoldPublicationUnavailableError):
    """A report read names a publication whose retained result is unavailable."""

    def __init__(self, publication_id: int, current_publication_id: int | None) -> None:
        """Keep the failed id and the current id a page may offer instead."""
        super().__init__(publication_id)
        self.publication_id = publication_id
        self.current_publication_id = current_publication_id
        if current_publication_id is not None:
            self.add_note(f"current publication: {current_publication_id}")


_COPENHAGEN: Final = ZoneInfo("Europe/Copenhagen")


def _copenhagen_date(moment: datetime) -> date:
    """Return the Copenhagen date of a recorded UTC moment."""
    return moment.astimezone(_COPENHAGEN).date()


def _reference_date(publication: GoldPublication, requested: date) -> date:
    """Use a past view's known date in Copenhagen; keep a page's pipeline date."""
    if publication.kind == "as_known_at":
        return _copenhagen_date(publication.known_at)
    return requested


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


def _is_current(publication: GoldPublication, current: GoldPublication | None) -> bool:
    """Whether `publication` is current at the moment the report is read."""
    return current is not None and current.publication_id == publication.publication_id


class HouseholdReports:
    """Reports resolved from and pinned to one request's Gold publications.

    A report adapter borrows the publications object and never owns its
    connection. Open, use, and close that object on one thread within one
    synchronous request. The returned report DTOs carry the pinned context and
    remain usable after the store closes; lifecycle errors are not translated
    into `NothingPublishedError` or `PublicationUnavailableError`.
    """

    def __init__(self, publications: GoldPublications) -> None:
        """Read reports from `publications`."""
        self._publications = publications

    def _unavailable(self, publication_id: int) -> PublicationUnavailableError:
        """Build the explicit failure from Gold's current state."""
        current = self._publications.current()
        current_id = None if current is None else current.publication_id
        return PublicationUnavailableError(publication_id, current_id)

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
        try:
            gold = self._publications.open(publication_id)
            publication = gold.publication()
            current = self._publications.current()
            return build_selection_options(
                gold,
                _reference_date(publication, reference_date),
                is_current=_is_current(publication, current),
            )
        except GoldPublicationUnavailableError as error:
            raise self._unavailable(publication_id) from error

    def monthly_overview(self, context: ReportContext) -> MonthlyOverview:
        """Return the overview from the publication pinned in `context`."""
        try:
            gold = self._publications.open(context.publication_id)
            publication = gold.publication()
            context = replace(
                context,
                reference_date=_reference_date(publication, context.reference_date),
            )
            return build_monthly_overview(
                gold,
                context,
                is_current=_is_current(publication, self._publications.current()),
            )
        except GoldPublicationUnavailableError as error:
            raise self._unavailable(context.publication_id) from error
