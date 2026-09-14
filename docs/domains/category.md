# Category Domain

A category groups income or expense facts for reporting and budgeting. It is a
household-owned taxonomy, independent of any bank's category labels.

Initial category attributes:

- stable `category_id`, household-assigned
- name
- category group: every category belongs to exactly one
- direction: `income` or `expense`
- active state

The hierarchy has exactly two levels, category group → category. Only a
category is ever assigned to a transaction; a category group exists for
rollups. Renaming a category or moving it to another group restates all
reports (current interpretation). Deliberately reclassifying past transactions
is a classification change, not a category change.

A classified booked transaction carries exactly one category. It is never
split across categories ([ADR-008](../decisions/ADR-008-single-category-per-transaction.md)).

Bank-provided categories in the current CSV exports are useful classification
signals but are not authoritative. They are retained as provenance in Silver;
Gold categories are assigned by rules or manual decisions.

Transfers, adjustments, and unclassified transactions do not carry a category.
A refund carries the expense category of the purchase it reverses.
