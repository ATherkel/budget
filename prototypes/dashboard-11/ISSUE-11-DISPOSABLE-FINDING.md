## Finding: fixed expenses and rådighedsbeløb — 28 September 2026

While discussing budget-versus-actual trends and the first-release inclusion of
read-only budgets, the maintainer identified another overview requirement:
split actual expenses into **Faste udgifter** and other expenses, and show
**Rådighedsbeløb**.

The maintainer confirmed this planned measure:

**Planned monthly take-home income − planned monthly fixed expenses = planned
monthly rådighedsbeløb.** Annual/quarterly commitments should be represented by
their monthly budget allowance. Actual fixed/other expenses and the existing
income-minus-all-expenses figure remain separate measures.

The category-level classification proposal exposed a modeling problem. A broad
group such as Bolig can contain rent and furniture, and even an individual
category may contain transactions with different fixed/other treatment. The
maintainer's current view is that production classification probably needs to
work per transaction, and requested a separate issue rather than silently
settling that design in the prototype.

The open question is how transaction-level treatment relates to planned fixed
commitments: a future or annual bill can belong in the monthly budget before
there is a booked transaction to tag. We need an explicit contract connecting
the planned measure and actual split, including refunds, unknown treatment,
history, and report coverage. A simple category flag is not an accepted solution.

Terminology reference: section 4.1 of the current [Finanstilsynet and
Forbrugerombudsmanden guidance](https://www.retsinformation.dk/eli/retsinfo/2025/10137/pdf)
describes income after tax less fixed commitments, including monthly, quarterly
and annual payments. This informs the household measure; it does not make the
dashboard a lender's creditworthiness assessment or loan-eligibility tool.

The chart/Enkel changes already in progress continue independently. This finding
does not change booked transaction amounts, the accepted Savings = Income −
Expenses measure, or classify actual household data.

🤖 Generated with Codex (GPT-6 Astra)
