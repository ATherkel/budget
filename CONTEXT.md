# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

**Refund**:
Money returned against a prior purchase. Nets against the originating category's
expense total rather than counting as income or vanishing from spending.
_Avoid_: Reversal (see Adjustment), chargeback (not yet a distinct concept)

**Adjustment**:
A correction, fee reversal, or exceptional entry with no originating purchase to
net against; excluded from income and expense totals. A Refund is not an
Adjustment even though both break the expense-is-negative sign convention.

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

**Unclassified total**:
An explicit reporting measure summing `unknown`-classified transactions for a
period, shown alongside Income/Expenses/Savings so an unclassified amount is a
verified claim, not an artifact of silent exclusion.

**Provisional period**:
A reporting period that includes the current, still-accumulating calendar
month. Must be visibly labeled wherever it's displayed, not just documented.
