# #11 — throwaway monthly dashboard

**Ready for feedback; no usability conclusions yet.** One design, read-only,
plain HTML/CSS/JS and a Python standard-library static server. Nothing here is
production application code. No dependencies to install.

Question: can two household members understand monthly spending, investigate
an unexpected category total, and recognize incomplete figures?

## Run

From the repository root in PowerShell:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Open <http://127.0.0.1:8011>. Stop with Ctrl+C. The server binds only to this
computer. Phone-sized browser testing is supported; access from a separate
physical phone has not been configured.

```powershell
py -3.12 prototypes/dashboard-11/check_fixtures.py
```

## Data boundary

- `example.json` is entirely synthetic: July–September 2026, two accounts,
  categorized income/spending, a refund, a negative spending category, paired
  internal transfer, offsetting unknown amounts, separate corrections, a
  confirmed quiet account/month, and missing/partial September data.
- At the user's later request, a frozen **private, bank-derived** report for
  14 months was prepared locally from the two supplied CSVs. It is under the
  already ignored `imports/.dashboard-11/`. It contains real dates and amounts,
  generic account/transaction labels, and illustrative assignments based on
  bank categories. It is not synthetic or a validated household report.
- Ambiguous movements remain unknown. Private coverage is explicitly
  unverified, not inferred from a stated balance. Historical local reports also
  remain provisional until validated; “month ended” alone is not admission
  evidence. One cancelled row was
  excluded. No bank description, account number, or source filename is in
  the report. Do not publish the private JSON or screenshots of that dataset.
- The default is the local snapshot when available; otherwise the synthetic
  example runs unchanged. The Data selector switches fixtures, not designs.
- The running server reads only frozen JSON and an allowlist of UI assets.
  It never reads CSVs, exposes the imports directory, or performs report
  arithmetic. The one-time fixture preparation is not an import pipeline.
- No database, authentication, upload, classification, matching, reconciliation,
  coverage engine, editing, remote infrastructure, or browser persistence.
- Fixture totals are Decimal strings; the renderer only formats numbers.
  Bars receive precomputed display percentages. Frozen totals are checked
  against contributing rows; synthetic totals also have hand-checked constants.

## Scope and decision status

Checked 15 September 2026: #2 and #11 open; #16, #18, #20 open and unmerged.
#16 documents the accepted #5 decisions (transaction dates, seven-day export
lag, whole-export quarantine); it is not yet on main. #18's Gold model and
#20's classification/transfer policies remain proposals, as do their ADRs.
This UI does not adopt their proposed responsibilities or rules. #10 remains
open and does not block frozen reports. Published prototype data stays synthetic.

The ownership labels Mine and Common follow the user's request. Hers and the
two children's account groups are future display needs; they are not added
to the reporting boundary by this experiment. Ownership and account type
(current/savings) are separate concepts.

The explicit session instructions override the prototype skill's multiple
variants/promotion steps and the repository's per-test red/green handoffs
for this throwaway artifact only. Verification is arithmetic plus browser
checks. Normal production TDD remains intact.

See [SESSION.md](SESSION.md) for observed feedback and checks, and
[REPORT-SHAPE.md](REPORT-SHAPE.md) for the proposed analytics-facing shape.

## Feedback exercise

Try together, preferably letting the less familiar person drive first:

1. Find where the money went this month.
2. Investigate why a category total looks surprising.
3. Identify which figures should be treated as incomplete.

Say what you try, what you expect, and where you hesitate. The facilitator
should observe first and withhold explanations of the intended answers.
If the local current month is too sparse for task 2, choose an earlier month;
the synthetic August example provides a repeatable alternative.

Do not close #11 or promote any code based on agent checks alone.
