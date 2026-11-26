# Copyright 2026 Therkel
"""The monthly overview and the selection options of one opened publication.

The caller opens the publication and says whether it is current; analytics
never decides which publication a page reads.
"""

from collections.abc import Collection, Sequence
from datetime import date

from budget.analytics.measures import UNKNOWN, ZERO, Figures, figures
from budget.analytics.reports import (
    SUMMARY_GROUPS,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyOverview,
    OverviewContributor,
    OverviewGroup,
    OverviewMovements,
    ReportContext,
    ReportPublication,
    SelectableAccount,
    SelectableOwner,
    SelectionOptions,
    SelectionRule,
    SummaryGroup,
)
from budget.analytics.trust import trust
from budget.gold import (
    GoldAccount,
    GoldRepository,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    first_day,
    last_day,
)


def every_row(
    gold: GoldRepository, account_ids: Collection[str] | None = None
) -> Sequence[MonthlyBalanceSnapshot]:
    """Return every snapshot row of `account_ids`, whatever its month.

    An account's rows after the selected month still tell whether it has a
    managed period at all.
    """
    return gold.monthly_balances(
        start_month=ReportingMonth(1, 1),
        end_month=ReportingMonth(9999, 12),
        account_ids=account_ids,
    )


def _selectable_months(
    gold: GoldRepository, reference_date: date
) -> tuple[ReportingMonth, ReportingMonth]:
    """Return the first and last selectable month, whichever accounts are selected.

    From the earliest snapshot month, or the reference month when there is
    none, through the reference month.
    """
    reference_month = ReportingMonth.of(reference_date)
    first_month = min((row.month for row in every_row(gold)), default=reference_month)
    return first_month, reference_month


def report_publication(gold: GoldRepository, *, is_current: bool) -> ReportPublication:
    """Return the report identity of the publication `gold` reads."""
    publication = gold.publication()
    return ReportPublication(
        publication_id=publication.publication_id,
        kind=publication.kind,
        label=publication.label,
        known_at=publication.known_at,
        is_current=is_current,
    )


def _figures(
    gold: GoldRepository, month: ReportingMonth, account_ids: Collection[str]
) -> Figures:
    """Return the figures of `month`'s transactions on `account_ids`."""
    start, end = first_day(month), last_day(month)
    return figures(
        gold.transactions(start_date=start, end_date=end, account_ids=account_ids),
        gold.category_allocations(
            start_date=start, end_date=end, account_ids=account_ids
        ),
        gold.categories(),
    )


def _contributor_rows(
    transactions: Sequence[GoldTransaction],
    names: dict[str, str],
    *,
    flip: bool = False,
) -> tuple[OverviewContributor, ...]:
    """Return overview contributors newest first, with their displayed contribution."""
    ordered = sorted(
        transactions,
        key=lambda transaction: (
            transaction.transaction_date,
            transaction.account_id,
            transaction.account_sequence,
        ),
        reverse=True,
    )
    return tuple(
        OverviewContributor(
            transaction_date=transaction.transaction_date,
            description=transaction.description,
            account_id=transaction.account_id,
            account_display_name=names[transaction.account_id],
            amount=transaction.amount,
            contribution=-transaction.amount if flip else transaction.amount,
        )
        for transaction in ordered
    )


def _overview_group(
    group: SummaryGroup,
    transactions: Sequence[GoldTransaction],
    names: dict[str, str],
) -> OverviewGroup:
    """Return one group's rows; Expenses count money out as a positive amount."""
    rows = _contributor_rows(transactions, names, flip=group == "expenses")
    amounts = [row.amount for row in rows]
    return OverviewGroup(
        group=group,
        rows=rows,
        total=sum((row.contribution for row in rows), ZERO),
        flows=MoneyInOut(
            money_in=sum((amount for amount in amounts if amount > 0), ZERO),
            money_out=sum((amount for amount in amounts if amount < 0), ZERO),
            count=len(amounts),
        ),
    )


def _movements(
    known: Figures,
    accounts: Sequence[GoldAccount],
) -> OverviewMovements:
    """Return the signed rows behind every summary group, in card order."""
    names = {account.account_id: account.display_name for account in accounts}
    return OverviewMovements(
        groups=tuple(
            _overview_group(group, known.grouped[group], names)
            for group in SUMMARY_GROUPS
        )
    )


def selected_accounts(
    gold: GoldRepository,
    context: ReportContext,
    also_broken: Collection[SelectionRule] = (),
) -> list[GoldAccount]:
    """Return the accounts `context` selects, or name every rule it breaks.

    `also_broken` names rules the caller's own arguments break, so one
    `InvalidSelectionError` names them together with the context's.
    """
    by_id = {account.account_id: account for account in gold.accounts()}
    unknown = context.account_ids - by_id.keys()
    selected = [by_id[account_id] for account_id in context.account_ids - unknown]
    first_month, last_month = _selectable_months(gold, context.reference_date)
    broken: dict[SelectionRule, bool] = {
        "no_accounts": not context.account_ids,
        "unknown_account": bool(unknown),
        # Gold contract invariant 13: never aggregate across currencies.
        "mixed_currencies": len({account.currency for account in selected}) > 1,
        "month_out_of_range": not first_month <= context.month <= last_month,
    }
    reasons = [rule for rule, is_broken in broken.items() if is_broken]
    reasons.extend(also_broken)
    if reasons:
        raise InvalidSelectionError(reasons, unknown)
    return selected


def monthly_overview(
    gold: GoldRepository, context: ReportContext, *, is_current: bool
) -> MonthlyOverview:
    """Return the monthly overview `context` selects from the publication `gold` reads.

    `is_current` says whether that publication is current; the caller decides.
    Raise `InvalidSelectionError` for a context that breaks a selection rule,
    and `ValueError` when `gold` reads another publication than `context` names.
    """
    opened = gold.publication().publication_id
    if opened != context.publication_id:
        message = (
            f"context names publication {context.publication_id}, "
            f"but publication {opened} is open"
        )
        raise ValueError(message)
    accounts = selected_accounts(gold, context)
    judged = trust(
        accounts,
        every_row(gold, context.account_ids),
        context.month,
        context.reference_date,
    )
    known = (
        UNKNOWN
        if judged.coverage.status == "no_data"
        else _figures(gold, context.month, context.account_ids)
    )
    return MonthlyOverview(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        income=known.income,
        expenses=known.expenses,
        net_cash_flow=known.net_cash_flow,
        savings_rate=known.savings_rate,
        categories=known.categories,
        unclassified=known.unclassified,
        adjustments=known.adjustments,
        movements=(
            None if judged.coverage.status == "no_data" else _movements(known, accounts)
        ),
        coverage=judged.coverage,
        provisional=judged.provisional,
    )


def selection_options(
    gold: GoldRepository, reference_date: date, *, is_current: bool
) -> SelectionOptions:
    """Return what a page may select in the publication `gold` reads."""
    first_month, last_month = _selectable_months(gold, reference_date)
    return SelectionOptions(
        publication=report_publication(gold, is_current=is_current),
        accounts=tuple(
            SelectableAccount(
                account_id=account.account_id,
                display_name=account.display_name,
                account_type=account.account_type,
                owner_id=account.owner_id,
                currency=account.currency,
            )
            for account in sorted(gold.accounts(), key=lambda a: a.account_id)
        ),
        first_month=first_month,
        last_month=last_month,
        owners=tuple(
            SelectableOwner(owner_id=owner.owner_id, display_name=owner.display_name)
            for owner in sorted(gold.owners(), key=lambda o: o.display_order)
        ),
    )
