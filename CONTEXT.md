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
stating whether that account's data is trustworthy enough to report on for that
period. `complete` requires an unbroken balance chain across every row in the
period _and_ that the account was already under management before the period
began; a first, partial-month import is always `partial`. Tracked at the
account grain, not the whole household, so a gap points at the account that
needs attention.

**Balance chain**:
The reconciliation evidence for an account: each transaction carries the
bank-stated balance immediately after it, which must equal the previous
transaction's balance plus its amount. The account's first transaction is
trusted as its opening balance. A break, or a missing balance, is a
discrepancy — reflected in Coverage, never silently corrected.

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
