# Category Domain

A category groups income or expense facts for reporting and budgeting. It is a
household-owned taxonomy, independent of any bank's category labels.

Initial category attributes:

- stable `category_id`, household-assigned, immutable and never reused for a
  different meaning
- name
- category group: every category belongs to exactly one
- direction: `income` or `expense`
- active state

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

Bank-provided categories in the current CSV exports are useful classification
signals but are not authoritative. They are retained as provenance in Silver;
Gold categories are assigned by rules or manual decisions.

Transfers, adjustments, and unclassified transactions do not carry a category.
A refund carries the category of the movement it reverses, including returned income.
