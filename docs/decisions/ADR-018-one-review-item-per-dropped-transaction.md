# ADR-018: Raise One Review Item per Dropped Transaction

**Status:** Accepted. Amends [ADR-017](ADR-017-dropped-transactions.md): a run
raises one `dropped-transaction` review item for each transaction it drops, not
one `dropped-transactions` item for all of them.

## Context

`ReviewItem.resolved_by` names one manual decision. ADR-017 has a run raise one
`dropped-transactions` review item for everything it drops, settled once each
dropped transaction has its own *withdrawn* or *same transaction* decision. An
item that drops two transactions therefore needs two decisions, possibly of
different kinds, and `resolved_by` can name only one of them.

For example, the export of 1 October drops two admitted transactions: `NETTO`
−45,00 on 3 September, which the bank removed, and `REMA` −120,00 on
5 September, which now reads `REMA 1000` −120,00. Settling the one item takes
*withdrawn* `d-0007` and *same transaction* `d-0008`:

- `resolved_by` cannot hold both.
- After `d-0007` alone the item is half settled, and nothing in the record says
  so.
- The item names only a date range and payloads, not the transactions, so
  `budget review` has to work out again which transactions were dropped before
  it can say what to decide.

Issue #115 found this while resolving issue #74.

## Decision

A run raises one `dropped-transaction` review item for each transaction it
drops:

- `ReviewItem` gains `transaction_id: str | None`: the dropped transaction, and
  null for every other kind.
- `review_item_id` hashes `[kind, import_run_id, transaction_id]` for a
  `dropped-transaction` item, so two drops on one date give two items.
- The item's `date_from` and `date_to` are both the dropped transaction's date.
- One *withdrawn* or *same transaction* decision settles the item, and
  `resolved_by` names it. The run is admitted once every review item it raised
  is settled.

Everything else in ADR-017 stands: what counts as a drop, the explained
difference, and that Silver never picks the decision.

## Considered Options

- **One item per run, with `resolved_by: Sequence[str]`** (issue #115,
  option B). Whether the item is settled would depend on whether the list
  covers every drop, which the record alone cannot show, unless the list stays
  empty until the last decision arrives. Rejected.
- **No `resolved_by`: derive review items afresh on each build, as Gold does**
  (option C). ADR-010 relies on a settled `balance-break` staying listed, so
  that an accepted discrepancy stays visible, and that would need another
  record. Rejected.

## Consequences

- Each review item is settled by exactly one decision, the model ADR-010
  describes: the item is what the decision "is prompted by and attaches to
  through `resolved_by`". *Withdrawn* and *same transaction* each already
  target one transaction.
- Each item names the transaction a person has to decide about.
- The kind reads `dropped-transaction`. Issue #5's scenarios 7 and 9 expect a
  `dropped-transaction` review item for each dropped transaction.
- `silver-layer.md` (`ReviewItem`, *Identity and merging*, *Merge
  verification*), `agents/silver-agent.md` and the `danske-csv-v1` data map
  follow.
- Resolves [issue #115](https://github.com/ATherkel/budget/issues/115).
