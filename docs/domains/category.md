# Category Domain

A category groups income or expense facts for reporting and budgeting. It is a
household-owned taxonomy, independent of any bank's category labels.

Initial category attributes:

- stable `category_id`, household-assigned, immutable and never reused for a
  different meaning
- name
- category group: every category belongs to exactly one
- direction: `income` or `expense`, shared by every category in its group

The hierarchy has exactly two levels, category group → category. Only a
category is ever allocated to a transaction; a category group exists for
rollups. A `group_id` is immutable and never reused either.

Renaming a category, moving it to another group, retiring it, or changing its
direction restates every report that was ever produced, because the dimension
carries only the current interpretation. Each such change is therefore appended
to [`category-changes.md`](category-changes.md) on the day it is made, so a
decision taken on an older report can still be read. Deliberately reclassifying
past transactions is a classification change, not a category change.

A category reaches a transaction through a **category allocation**, a record
of how much of that transaction belongs to the category. A classified
transaction has exactly one allocation, for its whole amount, and no way to
author a second exists yet; the allocations of a transaction always sum to its
amount ([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

## Taxonomy

The household defines its categories in configuration; the platform ships
none. The taxonomy and how changes to it behave are in
[`classification.md`](../architecture/classification.md#taxonomy). A category
can be deleted only once no rule or decision references it.

## Bank Categories

Bank-provided categories in the current CSV exports are useful classification
signals but are not authoritative. They are retained as provenance in Silver. A
classification rule may test them, but they are never copied into Gold and
never used as a fallback
([ADR-011](../decisions/ADR-011-classification-precedence.md)).

## Assignment

Transfers, adjustments, and unclassified transactions do not carry a category.
A refund carries the category of the movement it reverses. When a rule or
manual decision assigns a category, the type follows from the category's
direction and the amount's sign: a positive amount in an expense category, or
a negative one in an income category, is a refund.
