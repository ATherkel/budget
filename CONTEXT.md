# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

**Refund**:
An Adjustment that carries a `category_id`. It nets against that category
instead of counting as income or vanishing from spending. A reversed fee is a
Refund against the fee's category.
_Avoid_: Reversal, chargeback (not yet a distinct concept)

**Adjustment**:
A transaction that breaks the income/expense sign convention. With a
`category_id` it is a Refund; without one it is a correction, kept out of
Income and Expenses and reported on its own line.

**Transfer-eligible account**:
An account inside the household reporting boundary — `ownership_scope` of
`household` or `person` — whose movements can be matched as an internal
Transfer. An `external` account can never be presumed the other leg of a
Transfer.
_Avoid_: Household account (too narrow; excludes person-owned accounts that are
still transfer-eligible)

**Coverage**:
A per-account, per-reporting-period status (`complete` / `partial` / `no_data`)
saying whether that account's balance evidence shows the period's data is
whole. It is judged over the whole period, not only the rows inside it; the
rules are in
[`docs/architecture/analytics-layer.md`](docs/architecture/analytics-layer.md#coverage).
Tracked per account, not for the whole household, so a gap points at the
account that needs attention.

**Balance chain**:
The reconciliation evidence for an account: each transaction carries the
bank-stated balance immediately after it, and each link between consecutive
transactions checks that the later balance equals the earlier one plus the
later amount. A broken link, or a missing balance, is a discrepancy, never
silently corrected.

**Evidence through**:
The last date an account's imported exports are known to cover: the day
before its latest export date.
_Avoid_: last import date (the export date, not the import date, bounds the
evidence)

**Booked transaction**:
A transaction whose source marked it completed/settled. A pending or
unsettled source row is retained in Bronze and Silver as provenance but never
becomes a Gold transaction.
_Avoid_: Transaction, in Bronze/Silver context (too broad — those layers may
hold unsettled rows that aren't Transactions yet)

**Unclassified money**:
Money on `unknown` transactions, reported as money in, money out, and a count,
so opposite amounts can't cancel to zero and read as "nothing unclassified".
_Avoid_: Unclassified total (a single sum hides offsetting amounts)

**Provisional period**:
A reporting period that includes the current, still-accumulating calendar
month. Must be visibly labeled wherever it's displayed, not just documented.
