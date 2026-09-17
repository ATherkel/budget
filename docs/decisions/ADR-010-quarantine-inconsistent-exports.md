# ADR-010: Quarantine Exports Whose Stated Balances Are Inconsistent

**Status:** Accepted. Supersedes part of ADR-006.

## Context

ADR-006 admits a transaction with a missing balance or a broken balance chain
and demotes the account's coverage to `partial`. Issue #5 made Silver's
duplicate handling depend on bank-stated balances. For a source format that
states a balance on every booked row, a missing balance or an internal break
means the export itself cannot be trusted as evidence, whatever caused it.

## Decision

For source formats that state a balance on every booked row, including the
Danske CSV export, the whole import run is quarantined, with the offending
source records listed, when either of these holds:

- a booked row lacks a balance;
- consecutive booked rows within one export break the balance chain.

Nothing from that export reaches Silver until the cause is resolved. A parser
fix is picked up on rebuild.

A break also raises a `balance-break` review item for the run, alongside the
validation errors that name the offending rows. The errors are a verdict on the
file; the review item is the entry in the operator's work list that the decision
below is prompted by and attaches to through `resolved_by`. Review item
identifiers are deterministic, so replaying the same imports raises the same
item rather than a new one each time.

Where the source itself is inconsistent, a fourth manual decision, *accept
discrepancy*, names the import run and admits it with the break recorded. The
break is never repaired: the affected links stay unverified, so analytics
reports every period they span as `partial`. Without it there is no way back,
because the Danske export recalculates `Saldo` at export time: a chain break
means the bank counts a row it does not export, and every later export covering
that date breaks in the same way. Only exports starting after the offending
date could be admitted, and the window between would be lost for good.

ADR-006 still applies to the rest:

- coverage demotion for gaps between admitted exports;
- first imports;
- sources that do not state balances, where `balance` is null by design.

## Consequences

- For balance-stating sources, Silver and Gold never hold a booked
  transaction with a null balance.
- One inconsistent row blocks its whole export. Because exports overlap, only
  the export's new dates are delayed — unless the source keeps stating the same
  inconsistency, which is what *accept discrepancy* exists for.
- An accepted discrepancy is visible downstream rather than hidden: the import
  run lists it, and the periods its links span are `partial`.
- Silver's `ReviewItem.kind` gains `balance-break`. Each of the three decisions
  that settle a quarantine — *same transaction*, *withdrawn*, *accept
  discrepancy* — is now raised by a review item, so none of them depends on the
  operator already knowing it exists. *Void import run* is the exception by
  design: it answers a `refused` run, which states its own reason.
- Resolves part of [issue #5](https://github.com/ATherkel/budget/issues/5).
