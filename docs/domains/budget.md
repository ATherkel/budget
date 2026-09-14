# Budget Domain

A budget is a planned amount for a category and period; it is not a
transaction and cannot change historical spending facts.

Initial budget fields:

- `budget_id`
- `category_id`
- period (`YYYY-MM` initially)
- target amount as `Decimal`
- currency
- optional notes and effective date

Budget variance is calculated by analytics from the budget target and Gold
expense totals. Annual budgeting can be derived from monthly targets until a
separate annual-budget contract is justified.
