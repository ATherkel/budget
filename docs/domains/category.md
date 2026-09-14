# Category Domain

A category groups income or expense facts for reporting and budgeting. It is a
household-owned taxonomy, independent of any bank's category labels.

Initial category attributes:

- stable `category_id`
- name
- optional parent category
- direction: `income` or `expense`
- active state

Bank-provided categories in the current CSV exports are useful classification
signals but are not authoritative. They are retained as provenance in Silver;
Gold categories are assigned by rules or manual decisions.

Transfers and unclassified transactions do not require a category.
