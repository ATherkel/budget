---
type: gold-review
---
# PR 322: transaction context for Gold review

Base: 541beb9ffb2c041fb37814638dc428f274b01676. Keep the correction on PR #322:
one existing CLI seam and its publication reader, not an independent feature.
User authorized fixing review 4371407719; CLI seam and deferred mode were
already agreed. Earlier classification output privacy interpretation was wrong:
financial values are permitted in the operator terminal, never routine logs.

## Contract

Materialize account, transaction date, Decimal amount with currency, description,
and bank category for every surviving target inside the same Gold read snapshot
as its item and identifiers. Preserve target ordering and full candidate sets
under account filtering. Keep handles short and rule/decision references intact.
Never join mutable current Silver during review. Bank category is currently
absent from GoldTransaction: add optional bank_category to privileged transaction
lineage, populate from Silver during classification, persist only needed review
target provenance in an additive migration 0003, and join existing published
transactions/accounts for other facts. Keep the analytics GoldTransaction shape
unchanged. Existing publications cannot recover an absent historic bank label:
show unavailable rather than consulting Silver or fabricating one. Null labels
must be clear. Keep classification choices and missing-target semantics intact.

Render settlement guidance from classification.md's review-kind table, with
conditional choices clearly conditional rather than claiming a decision will
validate. Zero-amount category decisions cannot apply; classify as adjustment
is the meaningful classify option there. Non-applicable decisions need
supersede/retract guidance, including when all targets are missing. Do not build
a decide command, rule editor, dashboard, or unrelated summary/pair listing.
Escape control characters in free text so one transaction cannot forge terminal
lines. Routine logs must never contain these details or transaction handles.

## Deferred slices

1. Distinguishable ambiguous candidate details through budget review: synthetic
   Gold built from Silver, published, then read through CLI; pin expected details
   and bank label without reading present-day Silver for Gold context.
2. Settlement choices across review kinds, including zero amounts and missing
   targets; existing output tests updated only for intentional format additions.
3. Context stays pinned through concurrent publish/retention; privacy guards
   distinguish permitted stdout from forbidden routine log data. Verify older
   publication/null labels and control-character handling where new behavior
   demands it. One red then green per behavior; preserve actual failing evidence.

One Flash writer owns relevant src/budget/gold, reviewing.py, summaries.py,
additive Gold migration, related tests and contract docs. Astra owns this plan,
final acceptance and GitHub updates. No workflow/configuration/gate weakening,
production data, unrelated changes, pushes or GitHub posts from worker. Local
red/green commits are authorized by the active ship-issue workflow; use agent
identity and attribution. If blocked by permissions, retain exact patches and
logs and report instead of bypassing. Run quality gates before each commit and
full suite once at completion. Record actual provenance honestly.

Astra reviews actual patch and red evidence before pushing to existing PR and
replying to the inline finding. Static Flash routing verified; runtime provider
metadata unverified. Preserve the unrelated PR310 handoff stored in TEMP.


## Accepted result

Astra reviewed the actual patch and one correction batch. Review targets now
include published account/date/money/currency/description/bank-label context;
all facts are materialized inside the same SQLite snapshot. Amount-aware
settlement guidance avoids category decisions for zero targets. Optional bank
lineage preserves existing constructors. Free-text controls are escaped and
routine log records remain counts/kinds only. Schema 3 leaves historic labels
unavailable rather than joining current Silver. No stack or new PR is needed.

Worker Git writes were blocked. Actual red/green execution and exact stage
patches were retained locally; the final reviewed correction is integrated as
one fix commit, not presented as a sequence of red/green Git commits. Two initial
reds covered candidate context and settlement choices; correction reds covered
zero-amount choices and constructor compatibility. Later passing concurrency,
privacy and migration guards are not claimed as failing reds.

Validation: full suite 765 passed, 1 xfailed, 404 subtests passed. Ruff lint and
format, ty and complexipy passed. No workflow changes or production access.
Static worker routing passed; runtime provider metadata remains unverified.
