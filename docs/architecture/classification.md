# Gold Classification

## Purpose

Classification gives every Gold transaction its household interpretation: a
`transaction_type`, a `category_id` where the type needs one, and a
`transfer_group_id` for a matched transfer. This document is the policy Gold
applies. The fields it produces are defined in the
[Gold contract](gold-contract.md), and the decisions behind it are
[ADR-009](../decisions/ADR-009-classification-precedence.md) and
[ADR-010](../decisions/ADR-010-transfer-evidence.md).

Status: proposed with Gold contract 0.2.

Two principles run through every rule below:

- **A visible unknown beats a silent guess.** When the evidence is weak,
  conflicting, or ambiguous, the transaction stays `unknown`. It then shows in
  the unclassified total and raises a review item, instead of quietly moving
  money between income, expense, and transfer totals.
- **Classification is a pure function of its inputs.** The same inputs give the
  same result, whatever the import order and whatever an earlier publication
  said.

## Inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Booked Silver transactions for every Gold account | Silver | Including the bank's own category labels, carried verbatim as provenance. |
| Account registry | Household configuration | Only the accounts inside the reporting boundary. |
| Category taxonomy | Household configuration | Category groups and categories. |
| Classification rules | Household configuration | See [Classification Rules](#classification-rules). |
| Manual decisions | Household configuration | See [Manual Decisions](#manual-decisions). |
| Transfer matching policy | This document | Maximum date gap: 3 calendar days. |

File formats and CLI commands for these inputs belong to issue #10. How a
change to any of them is versioned belongs to issue #8.

## Outputs

- `transaction_type`, `category_id`, and `transfer_group_id` on each
  `GoldTransaction`.
- Classification lineage and transfer evidence for each transaction, through
  `GoldLineageRepository`.
- The open classification review items, through `GoldLineageRepository`.

Analytics sees only the first. Review and audit tooling reads the rest.

## Taxonomy

The household defines its own taxonomy in configuration. The platform ships no
built-in categories. `transfer`, `adjustment`, and `unknown` are transaction
types, not categories.

- The hierarchy has exactly two levels: category group → category. Only a
  category is assigned to a transaction.
- Every category has a direction, `income` or `expense`. All categories in a
  group share one direction, so a group rollup never mixes income and expense.
- Category and group identifiers are durable and household-assigned, such as
  `groceries`.
- The taxonomy needs at least one income and one expense category. It also
  needs categories for money that leaves or enters the reporting boundary
  without being ordinary spending or pay. Examples are money moved to a
  savings account that is not imported, and contributions from a household
  member's account that is not imported. These can never be transfers.

Taxonomy changes:

| Change | Effect |
| --- | --- |
| Rename a category or group | All reports restate. Nothing is reclassified. |
| Move a category to another group | Group rollups restate for every month. |
| Split a category | Add the new category and a rule or decision that assigns it. Matching past transactions move on the next build. |
| Merge or delete a category | Repoint every rule and decision that references it first. Deleting a referenced category is a validation error. |
| Change a group's direction | Every derived type in its categories is re-derived. A transaction whose sign no longer fits becomes a `sign-mismatch` review item. |

Every change restates history, because dimensions are Type 1
([ADR-007](../decisions/ADR-007-dimensional-gold-model.md)). Reproducing an
earlier report as it was is issue #8's concern.

## Classification Rules

A classification rule is a household-authored pattern over one transaction's
own facts. It never looks at other transactions. Transfer matching is the only
step that relates transactions to each other.

### What a rule may test

- `account_id`
- the description text: contains, starts with, or a regular expression,
  always case-insensitive
- the amount: sign, or an inclusive range
- the booking date: an inclusive range, for rules that apply only to a period
- the bank's category labels, where the source supplies them

Bank category labels are provenance. A rule may test them like any other
source text. They never become Gold categories on their own, and there is no
fallback that copies them. The Danske exports file transfers under the bank's
income and expense groups, and returned goods under income, so the labels do
not match household meaning.

### What a rule may assign

A rule assigns exactly one of:

- **a category.** The type follows from the category's direction and the sign
  of the amount:

  | Category direction | Amount | Type |
  | --- | --- | --- |
  | `expense` | negative | `expense` |
  | `expense` | positive | `refund` |
  | `income` | positive | `income` |
  | `income` | negative or zero | none: `sign-mismatch` |
  | `expense` | zero | none: `sign-mismatch` |

  A reimbursed outlay or returned purchase that matches an expense-category
  rule therefore becomes a refund in that category, and nets against it.
- **a transfer claim.** The rule states that the transaction is one leg of a
  transfer. The claim alone never makes a transfer: the leg must be paired
  (see [Transfer Matching](#transfer-matching)).
- **an adjustment**, with a short reason that lineage keeps as its
  explanation.

A rule never assigns `unknown`. Leaving a transaction unmatched does that.

### Priority and conflicts

Every rule has an integer `priority`, 0 by default. For each transaction, the
matching rules with the highest priority decide.

- If they all assign the same outcome, that outcome is the rule result.
- If they disagree, there is no rule result. The transaction is `unknown`,
  with a `rule-conflict` review item that names the rules.

Rules are not applied in file order, so a broad rule can never silently shadow
a narrower one. To let a specific rule win, give it a higher priority. To make
a fallback, give it a lower one.

## Transfer Matching

A transfer moves money between two accounts inside the reporting boundary.
Money to or from any other account is income or expense, even when a household
member owns that account but the household does not import it.

### Candidates

Two booked transactions are transfer candidates when all of these hold:

- they are on different Gold accounts;
- their amounts cancel exactly: one is negative, the other its positive
  counterpart;
- their booking dates are at most 3 days apart;
- neither is targeted by a manual decision;
- if the dates differ, at least one leg carries a transfer claim from its rule
  result. A same-day candidate needs no claim.

### Stages

Matching runs in stages by date gap: stage *n* considers only candidates whose
booking dates are exactly *n* days apart, for *n* = 0, 1, 2, 3 in that order.
Each stage skips legs already paired or held for review. Within a stage, Gold
groups the candidates into connected sets, and settles each set as follows:

| Set | Result | Evidence basis |
| --- | --- | --- |
| Exactly one outgoing and one incoming leg | One pair | `same_day` or `date_gap` |
| Each side's legs are repeated transactions of one another (same account, date, amount, and text) | Pairs in `account_sequence` order. Leftover legs stay available for later stages. | `repeated_legs` |
| Anything else | No pairs. Every leg in the set is `unknown`, and the set raises one `ambiguous-transfer` review item. These legs skip later stages. | none |

Repeated legs are interchangeable, so which outgoing leg pairs with which
incoming leg changes no total. Any other competition is a real ambiguity, and
Gold does not guess.

Both legs of a pair are `transfer`. Their shared `transfer_group_id` derives
from the two legs' `transaction_id`s, so it stays stable across rebuilds while
the same legs pair.

### Legs without a pair

A transaction whose rule result is a transfer claim but which is not paired is
`unknown`, with an `unmatched-transfer` review item. The item carries a
reason:

- `counterpart-may-not-be-imported`: some other Gold account has no booked
  transaction on or after the leg's last candidate date (booking date plus 3
  days). The other leg may arrive with the next import. This is a hint, and a
  quiet account also triggers it.
- `no-candidate`: otherwise.

A **one-sided transfer**, a transfer whose other leg can never be in Gold,
comes only from a manual decision. It names the counterpart Gold account, and
the booking date must fall outside that account's managed period. A typical
case is a transfer into a savings account from before its history was
imported.

### Across month boundaries

A pair may span two reporting months. Each leg stays in its own month for
account activity. Household income and expenses change in neither month.
The household's summed month-end balance is lower by the amount in flight, and
that is correct.

## Manual Decisions

A manual decision is a recorded human ruling. Classification uses three kinds:

| Kind | Targets | Result | Not applicable when |
| --- | --- | --- | --- |
| `classify` | one transaction | a category, with the type derived as for rules, or `adjustment` | the target is missing, or the derived type cannot fit the amount's sign |
| `pair` | two transactions | both `transfer`, sharing one group | a target is missing, the amounts do not cancel, or both are on one account |
| `one-sided-transfer` | one transaction and a counterpart account | `transfer` with no group | the target is missing, or the booking date falls inside the counterpart's managed period |

- A decision targets `transaction_id`s. Transaction identity
  ([issue #5](https://github.com/ATherkel/budget/issues/5)) survives
  re-imports, overlapping exports, and rebuilds, so a decision keeps its
  target. When the bank rewords a transaction's text, Silver's *same
  transaction* decision keeps the existing identifier.
- Each decision has a durable `decision_id` and a short reason.
- A transaction is targeted by at most one decision. A pair decision counts
  for both of its transactions.
- A decision that is not applicable changes nothing: the transaction is
  classified as if the decision did not exist, and a `decision-not-applicable`
  review item names the decision. Gold never moves a decision to a similar
  transaction.

A classification decision does not settle a review item by being marked
resolved. It removes the cause, and the item disappears on the next build.

## Precedence

For each transaction, the first step that applies decides:

1. **Manual decision.** An applicable decision targeting the transaction.
2. **Transfer pair.** The transaction was paired by transfer matching.
3. **Ambiguity.** The transaction is in an ambiguous candidate set: `unknown`.
4. **Rule result.**
   - A category gives the derived type, or `unknown` with a `sign-mismatch`
     item.
   - An adjustment gives `adjustment`.
   - A transfer claim gives `unknown` with an `unmatched-transfer` item.
   - A conflict gives `unknown` with a `rule-conflict` item.
5. **Nothing matched:** `unknown`, with an `unclassified` item.

A transfer pair beats a rule result. Both legs appear in the household's own
accounts on the same day or, with a transfer claim, within 3 days, which is
stronger evidence than a text pattern. Broad rules, such as one on a bank's
"other income" label, would otherwise swallow incoming transfers.

## Validation and Review

### Configuration errors

Problems visible in the configuration alone fail the Gold build before
anything is published. The error lists every offending entry:

- duplicate category, group, rule, or decision identifiers;
- a category without a group, or a group whose categories differ in direction;
- a rule or decision that references a category that does not exist;
- a rule with no outcome, several outcomes, or an unparseable pattern;
- an adjustment without a reason, or a decision without a reason;
- two decisions targeting the same transaction;
- a one-sided transfer whose counterpart is not in the account registry;
- deleting a category that a rule or decision still references.

### Review items

Problems that depend on the data become review items. Gold derives them afresh
on every build, so an item exists exactly while its cause does. Its
`review_item_id` derives from its kind and the transaction or decision
identifiers involved, so the same situation keeps the same identifier across
rebuilds.

| Kind | Raised when | Transaction is | Settled by |
| --- | --- | --- | --- |
| `unclassified` | no rule matches | `unknown` | a new rule or a `classify` decision |
| `rule-conflict` | the highest-priority matching rules disagree | `unknown` | a priority change, a narrower rule, or a decision |
| `sign-mismatch` | the winning rule's category direction cannot fit the amount's sign | `unknown` | a narrower rule or a decision |
| `ambiguous-transfer` | a candidate set is neither a single pair nor repeated legs | `unknown` (every leg in the set) | a `pair` or `classify` decision |
| `unmatched-transfer` | a transfer claim finds no pair | `unknown` | the next import, a `pair`, `one-sided-transfer`, or `classify` decision, or a rule fix |
| `decision-not-applicable` | a decision's target or conditions no longer hold | classified as if the decision did not exist | editing or removing the decision |

These are Gold's classification review items. Silver's review items for
imports (issue #5) are separate.

### What the review workflow shows

After each Gold build, the CLI review workflow (issue #10) shows:

- a summary: transactions by classification source, the unclassified total per
  account and month, and open review items by kind;
- each open review item, with what a person needs to decide it: the
  transactions (account, booking date, amount, description, and bank category
  label), the rules or candidate legs involved, and the decision kinds that
  would settle it;
- every transfer pair formed on a date gap, and every pair where a leg's own
  rule result is something other than a transfer claim, so a coincidental
  match can be spotted and undone with a `classify` decision.

This output contains financial values. It goes to the operator's terminal or a
private report, never to routine logs.

## Synthetic Examples

These examples are synthetic. Balances are omitted because they do not affect
classification.

### Setup

All accounts are in DKK. Bo, a household member, has an account that the
household does not import, so it is outside the reporting boundary.

| Account | Type | Ownership | Managed period starts |
| --- | --- | --- | --- |
| `joint-current` | current | household | 2025-11 |
| `joint-savings` | savings | household | 2026-01 |
| `anna-current` | current | person | 2026-01 |

| Group (direction) | Categories |
| --- | --- |
| `income` (income) | `salary`, `interest`, `contribution` |
| `housing` (expense) | `rent`, `utilities` |
| `food` (expense) | `groceries`, `eating-out` |
| `home` (expense) | `household-goods` |
| `personal` (expense) | `health`, `gifts` |
| `saving` (expense) | `external-saving` |

| Rule | Priority | When | Assigns |
| --- | --- | --- | --- |
| `r-salary` | 0 | text contains `ACME PAYROLL` | `salary` |
| `r-interest` | 0 | account `joint-savings` and text contains `INTEREST` | `interest` |
| `r-contribution-bo` | 0 | text contains `FROM BO` | `contribution` |
| `r-netto` | 0 | text contains `NETTO` | `groceries` |
| `r-mobilepay` | 0 | text starts with `MOBILEPAY` | `eating-out` |
| `r-home` | 0 | text contains `IKEA` | `household-goods` |
| `r-dentist` | 0 | text contains `DENTIST` | `health` |
| `r-savings-transfer` | 0 | text contains `TO SAVINGS` or `FROM CURRENT` | transfer claim |
| `r-budget-transfer` | 0 | text contains `BUDGET` | transfer claim |
| `r-bank-groceries` | −10 | bank category label is `Groceries` | `groceries` |

| Decision | Kind | Target | Result | Reason |
| --- | --- | --- | --- | --- |
| `d-0001` | `classify` | `joint-current` 2026-02-07 −2,400.00 `IKEA 551` | `gifts` | Wedding present |
| `d-0002` | `pair` | the two `TO SAVINGS` / `FROM CURRENT` legs of 2026-03-05 (scenario 12) | transfer | Settles an ambiguous transfer |
| `d-0003` | `one-sided-transfer` | `joint-current` 2025-12-15 −10,000.00 `TO SAVINGS` | counterpart `joint-savings` | Savings history before 2026 is not imported |
| `d-0004` | `classify` | a transaction the bank later withdrew (scenario 17) | `groceries` | — |

### Scenarios

| # | Situation | Transactions | Result | Evidence or review item |
| --- | --- | --- | --- | --- |
| 1 | A rule assigns an expense | `joint-current` 2026-02-02 −640.00 `NETTO 0412` | `expense`, `groceries` | rule `r-netto` |
| 2 | The same rule meets a positive amount | `joint-current` 2026-02-12 +120.00 `NETTO 0412` | `refund`, `groceries` | rule `r-netto`. February groceries net to 520.00. |
| 3 | A bank label used through a rule | `joint-current` 2026-02-14 −310.00 `FOETEX 88`, bank label `Groceries` | `expense`, `groceries` | rule `r-bank-groceries`, the only match |
| 4 | Equal-priority rules disagree | `joint-current` 2026-02-20 −85.00 `MOBILEPAY NETTO` | `unknown` | `rule-conflict`: `r-mobilepay` says `eating-out`, `r-netto` says `groceries` |
| 5 | The conflict settled by priority | Scenario 4 after adding `r-mobilepay-netto` (priority 10, text contains `MOBILEPAY NETTO`, assigns `groceries`) | `expense`, `groceries` | rule `r-mobilepay-netto`. The conflict item disappears. |
| 6 | A category that cannot fit the sign | `joint-savings` 2026-03-31 −3.50 `INTEREST ADJ` | `unknown` | `sign-mismatch`: `r-interest` gives an income category to a negative amount |
| 7 | A manual decision beats a rule | `joint-current` 2026-02-07 −2,400.00 `IKEA 551` | `expense`, `gifts` | decision `d-0001`. Lineage also records `r-home` as the rule that matched. |
| 8 | Same-day transfer | `joint-current` 2026-01-20 −3,000.00 `TO SAVINGS`; `joint-savings` 2026-01-20 +3,000.00 `FROM CURRENT` | `transfer` ×2, one group | `same_day` |
| 9 | Transfer across a month boundary | `joint-current` Fri 2026-01-30 −5,000.00 `TO SAVINGS`; `joint-savings` Mon 2026-02-02 +5,000.00 `FROM CURRENT` | `transfer` ×2, one group | `date_gap` of 3 days, with the claim from `r-savings-transfer`. January shows the outgoing leg and February the incoming one. Neither month's income or expenses change. |
| 10 | A coincidence with a date gap | `joint-current` 2026-03-10 −250.00 `IKEA 551`; `anna-current` 2026-03-12 +250.00 `MOBILEPAY CARL` | `expense`, `household-goods`; `refund`, `eating-out` | Not candidates: the dates differ and neither leg has a transfer claim. |
| 11 | Repeated same-amount legs | `anna-current` 2026-03-02 −2,000.00 `BUDGET JOINT` twice (occurrences 1 and 2); `joint-current` 2026-03-02 +2,000.00 `BUDGET FROM ANNA` twice | `transfer` ×4, two groups | `repeated_legs`, paired in `account_sequence` order |
| 12 | Competing legs | `joint-current` 2026-03-05 −1,500.00 `TO SAVINGS` and −1,500.00 `DENTIST 7`; `joint-savings` 2026-03-05 +1,500.00 `FROM CURRENT` | `unknown` ×3 | One `ambiguous-transfer` item, because the two outgoing legs have different text. After `d-0002` pairs the savings legs, the dentist leg falls back to `r-dentist`: `expense`, `health`. |
| 13 | A leg waiting for the next import | `joint-current` 2026-04-29 −800.00 `TO SAVINGS`; the latest `joint-savings` transaction is from 2026-04-20 | `unknown` | `unmatched-transfer`, reason `counterpart-may-not-be-imported`. Once the next export adds +800.00 on 2026-04-29, the rebuild pairs them (`same_day`). |
| 14 | A transfer claim with no candidate | `joint-current` 2026-02-16 −1,000.00 `TO SAVINGS`; both other accounts have transactions after 2026-02-19, and none is +1,000.00 within 3 days | `unknown` | `unmatched-transfer`, reason `no-candidate`. If the money went to a savings account that is not imported, a `classify` decision to `external-saving` settles it. |
| 15 | Money from a member's account that is not imported | `joint-current` 2026-02-01 +4,000.00 `FROM BO` | `income`, `contribution` | rule `r-contribution-bo`. Bo's account is outside the boundary, so this is never a transfer. |
| 16 | One-sided transfer | `joint-current` 2025-12-15 −10,000.00 `TO SAVINGS` | `transfer`, no group | decision `d-0003`. It applies because `joint-savings`' managed period starts in 2026-01. Without it: `unmatched-transfer`, `no-candidate`. |
| 17 | A decision whose target disappeared | The bank withdraws the transaction `d-0004` targets, and Silver records *withdrawn*. | no transaction | `decision-not-applicable`, reason `target-missing`. The decision is never moved to a similar transaction. |
| 18 | Invalid configuration | A decision assigns `food-out`, which does not exist. | Nothing is published | The build fails, and the error names the decision. |
| 19 | A new account turns income into transfers | Bo's account is later imported as a `person` account. Its −4,000.00 `BUDGET` leg on 2026-02-01 matches scenario 15. | `transfer` ×2 | `same_day`. The pair beats `r-contribution-bo`, and every report restates. Before Bo's managed period starts, `FROM BO` stays `contribution`. |

### Taxonomy changes

| # | Change | Result |
| --- | --- | --- |
| T1 | Rename `eating-out` to "Restaurants and takeaway" | Every report shows the new name. Nothing is reclassified. |
| T2 | Move `household-goods` from `home` to `housing` | The `housing` and `home` rollups restate for every month. |
| T3 | Split: add `furniture` to `home`, and `r-furniture` (priority 10, text contains `IKEA`, amount at most −1,000.00, assigns `furniture`) | IKEA purchases of 1,000.00 or more move to `furniture` in every month. Scenario 10's −250.00 stays in `household-goods`. Scenario 7 stays `gifts`, because `d-0001` beats every rule. |
| T4 | Delete `gifts` while `d-0001` references it | Configuration error naming `d-0001`. Nothing is published. |

## Left to Other Tickets

- **Issue #8:** versioning of rules, decisions, the taxonomy, and the matching
  policy; as-of reports; reproducing a report as it was before a change.
- **Issue #10:** file formats for rules and decisions, CLI command names, and
  how review output is presented.
- **Issue #12:** whether money moved to savings, investment, or loan accounts
  that are not imported should count differently in the savings measure. It is
  an expense today.
