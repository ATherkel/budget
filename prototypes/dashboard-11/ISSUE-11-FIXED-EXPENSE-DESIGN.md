## Origin and question

Follow-up to [the fixed-expense / rådighedsbeløb finding on #11](https://github.com/ATherkel/budget/issues/11#issuecomment-5865951679).
The maintainer requested this issue after the dashboard discussion revealed that
categories may mix fixed commitments and other spending.

How should the household identify fixed expenses, probably at transaction level,
and connect that treatment to a monthly plan so the dashboard can show both
actual fixed/other spending and planned rådighedsbeløb?

## Confirmed requirements

- Show actual expenses split into Faste udgifter and other expenses.
- Show planned monthly rådighedsbeløb = planned take-home income minus planned
  monthly fixed expenses, with quarterly/annual commitments spread over months.
- Keep this distinct from actual income minus all expenses and from savings
  after optional earmarking. Do not redefine existing accepted measures.
- Read-only budget comparison is part of the first usable release; targets are
  maintained outside the dashboard. Browser editing and forecasting remain
  deferred. See [the scope decision on #2](https://github.com/ATherkel/budget/issues/2#issuecomment-5865909851).
- The maintainer suggested classification probably needs to be per transaction.
  This is a design direction to resolve, not an approved schema or automatic rule.

## Decisions to resolve with the maintainer

1. Define fixed/other treatment independently of a transaction's category and
   type. Decide whether explicit transaction decisions, household rules/defaults,
   or another existing decision mechanism should supply it. Preserve immutable
   booked facts and do not repurpose transfer/expense transaction types.
2. Define planned commitments before any transaction exists. Specify how a mixed
   category's budget separates fixed and other amounts without double counting,
   and how planned take-home income and annual bills supply monthly values.
3. Define unknown treatment, refunds/reversals, changing commitments and partial
   account coverage. Missing treatment must not silently become "other" or zero.
4. Define ownership across configuration, classification, publications and
   analytics. Old publication views must keep a coherent treatment and budget
   version; presentation consumes the resulting report DTOs only.
5. Agree selected-account versus whole-household scope and understandable labels
   for planned figures versus actual month-to-date amounts.

## Resolution evidence

An agreed terminology and data/decision contract, plus synthetic examples:

- Two expenses in the same category have different fixed/other treatment.
- An annual fixed bill contributes to the monthly plan before being booked.
- A refund reduces the correct actual expense bucket.
- Unresolved treatment or incomplete evidence is visible without asserting a
  fully known split or rådighedsbeløb.
- A later classification/budget change has explicit historical-view semantics.

Record the resulting analytics-facing requirements on #11. Follow the normal
production TDD workflow for implementation after the public seam is agreed.
No bank thresholds, lending decision, debt engine, or loan-eligibility claim is
requested. Background terminology: [current official guidance, §4.1](https://www.retsinformation.dk/eli/retsinfo/2025/10137/pdf).

🤖 Generated with Codex (GPT-6 Astra)
