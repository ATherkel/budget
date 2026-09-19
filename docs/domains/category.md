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

## Initial Taxonomy

The household defines the taxonomy in configuration; the platform ships no
built-in categories. It needs at least one income and one expense category,
and categories for money that crosses the reporting boundary without being
ordinary pay or spending, such as money moved to a savings account that is
not imported, or contributions from a household member's account that is not
imported.

A category is removed only after every classification rule and manual
decision that references it has been repointed. Splits, merges, and other
changes are described in [`classification.md`](../architecture/classification.md#taxonomy).

## Bank Categories

Bank-provided categories in the current CSV exports are useful classification
signals but are not authoritative. They are retained as provenance in Silver. A
classification rule may test them like any other source text, but they are
never copied into Gold and never used as a fallback
([ADR-011](../decisions/ADR-011-classification-precedence.md)). Gold categories
are assigned by classification rules or manual decisions.

## Assignment

Transfers, adjustments, and unclassified transactions do not carry a category.
A refund carries the category of the movement it reverses. When a rule
or manual decision assigns a category, the type follows from the category's
direction and the amount's sign, so a positive amount in an expense category
is a refund, as is a negative amount returned from an income category.
