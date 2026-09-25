# Gold Classification

Status: accepted (ADR-011, ADR-012). The fields it produces are part of Gold
contract 0.2, which stays proposed until the readiness review (issue #12).

## Purpose

Classification gives every Gold transaction a `transaction_type`, a category
allocation when the type needs one, and a `transfer_group_id` when it is a
paired transfer. A classified transaction has exactly one allocation, for its
whole amount ([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).
The fields are defined in the [Gold contract](gold-contract.md). The decisions
behind this policy are
[ADR-011](../decisions/ADR-011-classification-precedence.md) and
[ADR-012](../decisions/ADR-012-transfer-evidence.md).

Two principles apply throughout:

- **A visible unknown beats a silent guess.** Weak, conflicting, or ambiguous
  evidence leaves a transaction `unknown`. It then counts as unclassified
  money and raises a review item, instead of silently moving money between
  income, expense, and transfer totals.
- **Classification is a pure function of its inputs.** Import order and
  earlier publications do not affect the result.

## Inputs

| Input | Owner | Notes |
| --- | --- | --- |
| Booked Silver transactions for every Gold account | Silver | Including the bank's category labels, as provenance. |
| Account registry | Household configuration | Only accounts inside the reporting boundary. |
| Category taxonomy | Household configuration | Category groups and categories. |
| Classification rules | Household configuration | See [Classification Rules](#classification-rules). |
| Manual decisions | Household configuration | See [Manual Decisions](#manual-decisions). |
| Transfer matching policy | This document | Maximum date gap: 3 calendar days. |

## Outputs

- On `GoldTransaction`: `transaction_type` and `transfer_group_id`, plus one
  `GoldCategoryAllocation` for the whole amount when the type carries a
  category.
- Through `GoldLineageRepository`: classification lineage, transfer evidence,
  and the open classification review items.

Analytics sees only the first. Review and audit tooling reads the rest.

## Taxonomy

The household defines its taxonomy in configuration; the platform ships no
categories. `transfer`, `adjustment`, and `unknown` are transaction types, not
categories.

- Two levels: category group → category. Only a category is allocated to a
  transaction.
- Every category has a direction, `income` or `expense`, shared by every
  category in its group, so a group rollup never mixes the two.
- Identifiers are durable and household-assigned, such as `groceries`.
- The taxonomy needs at least one income and one expense category, plus
  categories for money that crosses the reporting boundary without being pay
  or spending: for example, money moved to a savings account that is not
  imported, or contributions from a member's account that is not imported.
  Such money is never a transfer.

| Change | Effect |
| --- | --- |
| Rename a category or group | All reports restate. Nothing is reclassified. |
| Move a category to another group | Group rollups restate for every month. |
| Split a category | Add the new category and a rule or decision that assigns it. Matching past transactions move on the next build. |
| Merge or delete a category | Repoint every rule and decision that references it first; a dangling reference is a configuration error. |
| Change a group's direction | Types in its categories re-derive: `expense` becomes `refund` and `refund` becomes `income`, or the reverse. |

Every change restates history, because dimensions are Type 1
([ADR-007](../decisions/ADR-007-dimensional-gold-model.md)).

## Classification Rules

A classification rule is a household-authored pattern over one transaction's
own facts. Only transfer matching relates transactions to each other.

### What a rule may test

- `account_id`
- description text: contains, starts with, or a regular expression, always
  case-insensitive
- amount: sign, or an inclusive range
- transaction date: an inclusive range
- the bank's category labels, where the source supplies them

Bank category labels are provenance. A rule may test them, but they never
become Gold categories on their own and no fallback copies them: Danske files
transfers under its income and expense groups, and returned goods under
income.

### What a rule may assign

Exactly one of:

- **A category.** The type follows from the category's direction and the
  amount's sign:

  | Category direction | Amount | Type |
  | --- | --- | --- |
  | `expense` | negative | `expense` |
  | `expense` | positive | `refund` |
  | `income` | positive | `income` |
  | `income` | negative | `refund` |
  | either | zero | none: `sign-mismatch` |

  A returned purchase matched by an expense-category rule therefore becomes a
  refund in that category and nets against it.
- **A transfer claim**: the transaction is one leg of a transfer. It becomes a
  transfer only if paired (see [Transfer Matching](#transfer-matching)).
- **An adjustment**, with a short reason that lineage keeps.

No rule assigns `unknown`; matching no rule does.

### Priority and conflicts

Every rule has an integer `priority`, 0 by default. The highest-priority
matching rules decide. If they agree, that is the rule result. If they
disagree, there is none: the transaction is `unknown`, with a `rule-conflict`
review item naming the rules.

File order never matters, so a broad rule cannot silently shadow a narrower
one. Raise a specific rule's priority to let it win; lower a fallback's.

## Transfer Matching

A transfer moves money between two accounts inside the reporting boundary.
Money to or from any other account is income or expense, even when a household
member owns it.

### Candidates

Two booked transactions are transfer candidates when:

- they are on different Gold accounts;
- their amounts cancel exactly;
- their transaction dates are at most 3 days apart;
- neither is targeted by an applicable manual decision; and
- at least one leg's rule result is a transfer claim, whatever the date gap.

The claim keeps an unrelated same-day coincidence from hiding an expense and
an income. A low-priority rule on the bank's transfer label is the usual way
to claim real transfers.

### Stages

Matching runs in stages by date gap: stage *n* considers only candidates
exactly *n* days apart, for *n* = 0, 1, 2, 3 in that order, and skips legs
already paired or held for review. Within a stage, the candidates form
connected sets, each settled as follows:

| Set | Result | Evidence basis |
| --- | --- | --- |
| Exactly one outgoing and one incoming leg | One pair | `same_day` or `date_gap` |
| Each side's legs are repeated transactions of one another (same account, date, amount, and text) | Pairs in `account_sequence` order. Leftover legs stay available for later stages. | `repeated_legs` |
| Anything else | No pairs. Every leg is `unknown`, the set raises one `ambiguous-transfer` review item, and its legs skip later stages. | none |

Repeated legs are interchangeable, so the pairing changes no total. Any other
competition is a real ambiguity, and Gold does not guess.

Both legs of a pair are `transfer` and share a `transfer_group_id` derived
from their `transaction_id`s.

### Legs without a pair

An unpaired leg whose rule result is a transfer claim is `unknown`, with an
`unmatched-transfer` review item and one of these reasons:

- `counterpart-may-not-be-imported`: some other Gold account has no booked
  transaction on or after the leg's transaction date plus 3 days, so the other
  leg may arrive with the next import. This is only a hint: a quiet account
  also triggers it.
- `no-candidate`: otherwise.

A transfer that loses a fee, such as 1,000.00 out and 995.00 in, never pairs,
because the amounts do not cancel. Each leg is classified on its own until
splits exist ([issue #47](https://github.com/ATherkel/budget/issues/47)).

A **one-sided transfer**, whose other leg can never be in Gold, comes only
from a manual decision naming the counterpart Gold account. The transaction
date must fall outside that account's managed period, as with a transfer into
savings from before the savings history was imported.

### Across month boundaries

A pair may span two reporting months. Each leg stays in its own month for
account activity, and household income and expenses change in neither. The
summed month-end balance is lower by the amount in flight, which is correct.

## Manual Decisions

A manual decision is a recorded human ruling. Classification uses three kinds:

| Kind | Targets | Result | Not applicable when |
| --- | --- | --- | --- |
| `classify` | one transaction | a category, with the type derived as for rules, or `adjustment` | the target is missing, or a category meets a zero amount |
| `pair` | two transactions | both `transfer`, sharing one group | a target is missing, the amounts do not cancel, or both are on one account |
| `one-sided-transfer` | one transaction and a counterpart account | `transfer` with no group | the target is missing, or the transaction date falls inside the counterpart's managed period |

- A decision targets `transaction_id`s, which survive re-imports, overlapping
  exports, and rebuilds ([issue #5](https://github.com/ATherkel/budget/issues/5)).
  When the bank rewords a transaction's text, Silver's *same transaction*
  decision keeps its identifier.
- Each decision has a durable `decision_id` and a short reason.
- Decisions are entries in an append-only decision log. A decision is never
  edited or deleted; a later entry supersedes or retracts it
  ([`publications.md`](publications.md#the-decision-log)).
- A transaction is targeted by at most one decision; a `pair` counts for both
  of its transactions.
- A decision that is not applicable changes nothing: the transaction is
  classified as if the decision did not exist, and a `decision-not-applicable`
  review item names it. Gold never moves a decision to a similar transaction.

Review items are never marked resolved. A decision removes the cause, and the
item disappears on the next build.

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

A pair beats a rule result because a transfer claim confirmed by an opposite
leg in the household's own accounts is stronger evidence than a text pattern
alone. Otherwise a broad rule,
such as one on the bank's "other income" label, would swallow incoming
transfers.

## Validation and Review

### Configuration errors

Problems visible in the configuration alone fail the Gold build before
anything is published, and the error lists every offending entry:

- duplicate category, group, rule, or decision identifiers;
- a category without a group, or a group whose categories differ in direction;
- a rule or decision that references a missing category, including a deleted
  one;
- a rule with no outcome, several outcomes, or an unparseable pattern;
- an adjustment or decision without a reason;
- two decisions targeting the same transaction;
- a one-sided transfer whose counterpart is not in the account registry.

### Review items

Problems that depend on the data become review items. Gold derives them afresh
on every build, so an item exists exactly while its cause does. A
`review_item_id` derives from the kind and the transaction or decision
identifiers involved, so it is stable across rebuilds.

| Kind | Raised when | Transaction is | Settled by |
| --- | --- | --- | --- |
| `unclassified` | no rule matches | `unknown` | a new rule or a `classify` decision |
| `rule-conflict` | the highest-priority matching rules disagree | `unknown` | a priority change, a narrower rule, or a decision |
| `sign-mismatch` | the winning rule assigns a category to a zero amount | `unknown` | a narrower rule or a decision |
| `ambiguous-transfer` | a candidate set is neither a single pair nor repeated legs | `unknown` (every leg in the set) | a `pair` or `classify` decision |
| `unmatched-transfer` | a transfer claim finds no pair | `unknown` | the next import, a `pair`, `one-sided-transfer`, or `classify` decision, or a rule fix |
| `decision-not-applicable` | a decision's target or conditions no longer hold | classified as if the decision did not exist | a decision that supersedes or retracts it |

Silver's import review items (issue #5) are separate.

### What the review workflow shows

After each Gold build, the CLI review workflow (issue #10) shows:

- a summary: transactions by classification source; unclassified money in,
  money out, and count per account and month; and open review items by kind;
- each open review item with what a person needs to settle it: the
  transactions (account, transaction date, amount, description, and bank
  category label), the rules or candidate legs involved, and the decision
  kinds that would settle it;
- every pair formed on a date gap, and every pair where a leg's own rule
  result is not a transfer claim, so a coincidental match can be spotted and
  undone with a `classify` decision.

This output contains financial values. It goes to the operator's terminal or a
private report, never to routine logs.

## Synthetic Examples

Balances are omitted; they do not affect classification.

### Setup

All accounts are in DKK. Bo, a household member, has an account the household
does not import, so it is outside the reporting boundary.

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
| `d-0004` | `classify` | a transaction the bank later withdrew (scenario 17) | `groceries` | Receipt shows groceries |

### Scenarios

| # | Situation | Transactions | Result | Evidence or review item |
| --- | --- | --- | --- | --- |
| 1 | A rule assigns an expense | `joint-current` 2026-02-02 −640.00 `NETTO 0412` | `expense`, `groceries` | rule `r-netto` |
| 2 | The same rule meets a positive amount | `joint-current` 2026-02-12 +120.00 `NETTO 0412` | `refund`, `groceries` | rule `r-netto`. With scenario 1, groceries net to 520.00. |
| 3 | A bank label used through a rule | `joint-current` 2026-02-14 −310.00 `FOETEX 88`, bank label `Groceries` | `expense`, `groceries` | rule `r-bank-groceries`, the only match |
| 4 | Equal-priority rules disagree | `joint-current` 2026-02-20 −85.00 `MOBILEPAY NETTO` | `unknown` | `rule-conflict`: `r-mobilepay` says `eating-out`, `r-netto` says `groceries` |
| 5 | Priority settles the conflict | Scenario 4 after adding `r-mobilepay-netto` (priority 10, text contains `MOBILEPAY NETTO`, assigns `groceries`) | `expense`, `groceries` | rule `r-mobilepay-netto`. The conflict item disappears. |
| 6 | Returned income | `joint-savings` 2026-03-31 −3.50 `INTEREST ADJ` | `refund`, `interest` | rule `r-interest`. Income falls by 3.50. |
| 7 | A manual decision beats a rule | `joint-current` 2026-02-07 −2,400.00 `IKEA 551` | `expense`, `gifts` | decision `d-0001`. Lineage also records `r-home` as matching. |
| 8 | Same-day transfer | `joint-current` 2026-01-20 −3,000.00 `TO SAVINGS`; `joint-savings` 2026-01-20 +3,000.00 `FROM CURRENT` | `transfer` ×2, one group | `same_day` |
| 9 | Transfer across a month boundary | `joint-current` Fri 2026-01-30 −5,000.00 `TO SAVINGS`; `joint-savings` Mon 2026-02-02 +5,000.00 `FROM CURRENT` | `transfer` ×2, one group | `date_gap` of 3 days, claimed by `r-savings-transfer`. Each month shows its own leg; neither month's income or expenses change. |
| 10 | A coincidence | `joint-current` 2026-03-10 −250.00 `IKEA 551`; `anna-current` 2026-03-12 +250.00 `MOBILEPAY CARL` | `expense`, `household-goods`; `refund`, `eating-out` | Not candidates: neither leg has a transfer claim. They would not pair on the same day either. |
| 11 | Repeated same-amount legs | `anna-current` 2026-03-02 −2,000.00 `BUDGET JOINT` twice; `joint-current` 2026-03-02 +2,000.00 `BUDGET FROM ANNA` twice | `transfer` ×4, two groups | `repeated_legs`, paired in `account_sequence` order |
| 12 | Competing legs | `joint-current` 2026-03-05 −1,500.00 `TO SAVINGS` and −1,500.00 `DENTIST 7`; `joint-savings` 2026-03-05 +1,500.00 `FROM CURRENT` | `unknown` ×3 | One `ambiguous-transfer` item: the outgoing legs have different text. After `d-0002` pairs the savings legs, the dentist leg falls back to `r-dentist`: `expense`, `health`. |
| 13 | A leg waiting for the next import | `joint-current` 2026-04-29 −800.00 `TO SAVINGS`; the latest `joint-savings` transaction is from 2026-04-20 | `unknown` | `unmatched-transfer`, `counterpart-may-not-be-imported`. When the next export adds +800.00 on 2026-04-29, the rebuild pairs them (`same_day`). |
| 14 | A transfer claim with no candidate | `joint-current` 2026-02-16 −1,000.00 `TO SAVINGS`; both other accounts have later transactions, and none is +1,000.00 within 3 days | `unknown` | `unmatched-transfer`, `no-candidate`. If the money went to a savings account that is not imported, a `classify` decision to `external-saving` settles it. |
| 15 | Money from a member's account that is not imported | `joint-current` 2026-02-01 +4,000.00 `FROM BO` | `income`, `contribution` | rule `r-contribution-bo`. Bo's account is outside the boundary, so this is never a transfer. |
| 16 | One-sided transfer | `joint-current` 2025-12-15 −10,000.00 `TO SAVINGS` | `transfer`, no group | decision `d-0003`, applicable because `joint-savings`' managed period starts in 2026-01. Without it: `unmatched-transfer`, `no-candidate`. |
| 17 | A decision whose target disappeared | The bank withdraws the transaction `d-0004` targets, and Silver records *withdrawn*. | no transaction | `decision-not-applicable`, reason `target-missing`. The decision is never moved to a similar transaction. |
| 18 | Invalid configuration | A decision assigns `food-out`, which does not exist. | Nothing is published | The build fails, naming the decision. |
| 19 | A new account turns income into transfers | Bo's account is later imported as a `person` account. Its −4,000.00 `BUDGET` leg on 2026-02-01 matches scenario 15. | `transfer` ×2 | `same_day`. The pair beats `r-contribution-bo`, and every report restates. Before Bo's managed period starts, `FROM BO` stays `contribution`. |

A zero-amount `INTEREST ADJ` matched by `r-interest` is `unknown`, with a
`sign-mismatch` review item.

### Taxonomy changes

| # | Change | Result |
| --- | --- | --- |
| T1 | Rename `eating-out` to "Restaurants and takeaway" | Every report shows the new name. Nothing is reclassified. |
| T2 | Move `household-goods` from `home` to `housing` | The `housing` and `home` rollups restate for every month. |
| T3 | Split: add `furniture` to `home`, and `r-furniture` (priority 10, text contains `IKEA`, amount at most −1,000.00, assigns `furniture`) | IKEA purchases of 1,000.00 or more move to `furniture` in every month. Scenario 10's −250.00 stays in `household-goods`. Scenario 7 stays `gifts`, because `d-0001` beats every rule. |
| T4 | Delete `gifts` while `d-0001` references it | Configuration error naming `d-0001`. Nothing is published. |

## Left to Other Tickets

- **Issue #10:** file formats for rules and decisions, CLI command names, and
  how review output is presented.
- **Issue #12:** whether money moved to savings, investment, or loan accounts
  that are not imported should count differently in the savings measure. It is
  an expense today.
- **Issue #47:** pairing transfers that lose a fee, once splits exist.
