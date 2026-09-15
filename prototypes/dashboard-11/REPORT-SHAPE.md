# Minimal proposed monthly report

**Proposal from screen needs, not human-validated and not a Gold contract.**
The renderer consumes a report produced by analytics. A production implementation
must obtain it through analytics rather than copying the private fixture process.

```text
MonthlyReport
  period: id, label, start, end, provisional, provisionalReasons[]
  currency: DKK
  coverage: status, incompleteAccounts[{id, name, status, reasons[]}]
  measures: income, expenses, netCashFlow, savings, savingsRate
  incomeTransactions: TransactionDisplay[]
  categories: [{id, name, purchases, refunds, netSpending,
                coverage, transactions: TransactionDisplay[]}]
  unclassified: {moneyIn, moneyOut, count, transactions}
  adjustments: {moneyIn, moneyOut, count, transactions}
  transfers: {moneyIn, moneyOut, count, transactions}
  accounts: [{id, name, ownerLabel, accountType, coverage,
              balance: {amount|null, asOf|null}, quietConfirmed,
              transactions: TransactionDisplay[]}]

TransactionDisplay
  id, accountId, accountName, date, description, amount, kind, kindLabel
```

- All monetary fields are exact Decimal strings in one stated currency.
  Money out is negative; expense/category summaries use spending-positive
  convention and may be negative after net refunds. Savings rate is nullable
  when income is not positive. No financial calculations occur in the browser.
- Coverage is mandatory on every household measure. It can be included once
  as an explicit shared reference for a report with the same account scope,
  as long as every drill-down carries and displays it. Period provisionality,
  account coverage, and unresolved classifications are separate facts.
- Balance date belongs next to the balance. A missing balance is null, not
  zero. Zero activity is only confirmed with complete evidence. A last stated
  balance must not imply a complete month. No aggregate balance is needed yet.
- Category drill-down needs purchases/refunds/net supplied independently of
  presentation. A refund retains its own date; it is not moved back to the
  purchase month. Details repeat period and account coverage.
- Unknown in/out/count must survive even when the amounts cancel. Corrections
  without categories stay separate. Transfers are excluded from income,
  spending and savings. Each transaction belongs to exactly one report bucket.
- Owner labels are presentation metadata, not matching eligibility or account
  types. Do not encode Mine/Hers/Common/children as five financial account types.
- Transaction IDs are display/report IDs; no bank account number, CSV filename,
  source row ID, credentials, or raw payload is needed by the screen.
- Prototype-only fields (`barPercent`, friendly copy, `openingBalance` audit
  fixtures, dataset metadata) are not required production contract fields.
- Eager transaction arrays are sufficient here. Pagination or a separate detail
  report is an implementation choice for later. YTD/trend/report filtering is
  outside this first version.

Open: do these labels make sense to both participants; is income minus expenses
the preferred headline; which account groups should be shown; is a category
subtotal plus contributing entries enough to explain a surprise; how much
coverage detail belongs above the fold; what should a production classification
workflow supply? No proposed ADR has been accepted through this screen.
