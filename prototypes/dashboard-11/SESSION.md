# #11 session record — 15 September 2026

## Status

Ready for feedback. The prototype has
not yet been tried by the user and their wife. No usability approval or
successful task completion is claimed.

## Observed user input and resulting changes

- The user requested one coherent small design, explicit report fixtures and
  a throwaway-only browser/arithmetic verification exception. Built that scope.
- Before trying the UI, the user asked to use the two local CSVs and clarified
  ownership labels: mine, hers, common, plus two children's savings accounts.
  Added a local-only bank-derived fixture, generic labels, and Mine/Common
  ownership labels for the two available accounts. Preserved an explicitly
  separate synthetic example for edge cases absent from those local statements.
- This is requirements input, **not observed usability feedback**.

## Agent verification

- Passed Decimal arithmetic checks for all 14 local and 3 synthetic months:
  category purchases/refunds/net, income/expenses/net/savings rate, separate
  unknown and correction in/out/count, exclusive reporting buckets, matching
  account details, and independently specified synthetic opening/ending balances.
  Synthetic monthly totals also match hand-checked constants; local report
  totals match a separately summed frozen bucket baseline. This checks arithmetic,
  not the correctness of private classification or coverage assumptions.
- Browser checked at 1280×900, 390×844 and 320×740. Month selection, dataset
  selection, category details, refunds including negative spending, unknown
  entries, paired transfers, account details, no-data balances, quiet months,
  and separate corrections work. Escape closes details and focus returns to
  the trigger. No horizontal overflow in the checked phone states.
- Agent-found corrections: category bars needed block layout; complete account
  evidence uses a neutral green rather than warning styling; narrow screens
  stack account information; historical local samples remain explicitly
  provisional because their import status has not been validated.
- Private fixtures are ignored by Git. Source files were not changed. Server
  exposes only the selected frozen reports and UI assets on loopback.

## Human exercise — awaiting observations

1. Find where money went this month.
2. Explain an unexpected category total by investigating it.
3. Identify incomplete figures.

For each participant record attempted action, expectation, hesitation or
misinterpretation, and their exact words where useful. Record assistance
provided; do not count a coached answer as unaided success. Then change the
most important observed confusion and repeat that task.

## Validated decisions

No dashboard design decision has yet been validated with the participants.
The explicit implementation/data instructions above are agreed scope, not
validation of layout, labels, or comprehension.

## Untested assumptions and remaining questions

- Whether the labels and dense local categories work for both people.
- Whether incomplete/account-specific notices are noticed and understood.
- Whether “Left after expenses” is understood as income minus expenses,
  separate from actual account balance movement and unclassified money.
- Whether generic transaction labels retain enough detail for investigation.
- Whether Mine/Common ownership labels help; how Hers/children should appear.
- Whether the account-specific zero-activity and no-data treatments are distinct.
- Local fixture categories and coverage are not validated financial facts.
- This session does not settle YTD/trends, warehouse readiness, import/config
  decisions in #10, or the Gold/classification proposals in #18/#20.
