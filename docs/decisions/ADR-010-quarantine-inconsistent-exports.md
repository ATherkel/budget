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
fix is picked up on rebuild, and a manual decision is recorded where needed.

ADR-006 still applies to the rest:

- coverage demotion for gaps between admitted exports;
- first imports;
- sources that do not state balances, where `balance` is null by design.

## Consequences

- For balance-stating sources, Silver and Gold never hold a booked
  transaction with a null balance.
- One inconsistent row blocks its whole export. Because exports overlap, only
  the export's new dates are delayed.
- Resolves part of [issue #5](https://github.com/ATherkel/budget/issues/5).
