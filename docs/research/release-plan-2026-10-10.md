---
type: research
---
# Proposed releases from first dashboard to a dependable household app

## Basis

The owner confirmed **actuals first in 0.3**. This proposal assigns every
currently open issue in the [ledger](issue-audit-ledger-2026-10-10.md), and
names missing delivery work instead of treating a feature's specification as
its implementation. It does not set dates or promise that later undefined
features are ready to build. GitHub has not been changed.

Keep the existing closed 0.1 and 0.2 milestones as delivered history. Keep
`Polish` outside release gates. Keep `Later` as a small uncommitted design
queue, rather than the home of everything after the dashboard.

## Release outcomes

| Milestone | User-visible result | Existing issues proposed here | Gate |
| --- | --- | ---: | --- |
| **0.3 First dashboard** | Import CSVs, correct review items and read trustworthy monthly actuals in an authenticated app. | 30 | The whole monthly workflow works twice, recovers safely and passes the household trial. |
| **0.4 Spending investigation and operations** | Explain category/account figures and understand import or pipeline problems. | 9 | Detail reconciles to the overview; diagnostics and logs preserve privacy. |
| **0.5 Budgets and trends** | Compare actuals with immutable household plans and inspect changes over time. | 3 | Incomplete/wrong-scope plans are explicit; old publications keep their targets; charts have usable exact tables. |
| **0.6 History and reproducibility** | Browse what was reported then and what is known now, with the right inputs and plan. | 2 | Historical build, retention, version and unavailable-result behavior works end to end. |
| **0.7 Commitments, trips and refund notes** | Use the app for real household planning beyond monthly category targets. | 5 | Fixed commitments, trip exclusions and refund links preserve accounting and historical meaning. Reserve delivery requires its own accepted implementation scope. |
| **0.8 Bank connections** | Add a consented read-only bank source without changing financial consumers. | 2 | Connector implementation, access lifecycle, safe retries and completed operator-specific setup exist; policy scaffolds alone are insufficient. |
| **Polish** | Optional small improvements picked deliberately. | 17 | No release dependency unless new evidence changes impact. |
| **Later** | Uncommitted splits/fee transfers and packaging questions. | 2 | Obtain scope before assigning a release. |
| **Close/consolidate** | Remove satisfied or overlapping work after preserving acceptance. | 5 | #186/#208 resolved candidates; #145/#254 into #250; #255 into #240. |
| **Roadmap only** | Keep the cross-release map separate from a release finish line. | 1 | #2 has explicit roadmap/planning status. |

Counts describe existing issues, not effort. The 30 in 0.3 include an umbrella,
small contract decisions and guard tests; the later milestones need additional
delivery tickets described below. They must not look artificially smaller by
counting an entire upstream subsystem as one UI issue.

The planned Later reduction is **42 → 2** existing issues. New unscheduled
ideas may still land there, but each needs an explicit unresolved question and
a named next decision. Do not create a new catch-all numbered milestone.

## 0.3: a working actuals application

### Included

- Existing Gold classification, decisions, persistence, publication, analytics
  and UI work: #170/#171/#172/#173/#175/#176/#177/#178/#179/#180/#181,
  #103/#104/#111, with #100 as its umbrella.
- The already scheduled restore #121 and late-booking profile/recipe work #250.
- Promote #119, #150, #188, #217, #232, #237, #238, #239, #241, #243, #244,
  #252 and #253 from Later or Polish as **proposed 0.3 work/decisions**.
  Resolve small contract questions in their owning bundles; do not require
  a separate implementation campaign for each documentation correction.
- Two missing delivery owners: Gold operating integration and Gold review
  discovery. These are detailed below and are not counted among the 30.

Exclude budgets, trends, advanced Kontrol, historical pickers, connectors,
forecasts and browser editing. A reader still gets a usable explanation of
coverage, provisional figures and unclassified money in #104.

### Dependency-ordered execution

1. **Resolve the first-release contract decisions.** #241 transfer policy
   identity; #243 taxonomy obligations; #250 including #254's whole-day/minimum
   policy; #237/#239 invalid registry combinations; #238 trailing missing
   balance; #252 coverage wording; #244 precise no-op meaning; #121 recovery
   scope; #150 clean-files confirmation semantics. Preserve prior owner rulings.
2. **Proceed on independent seams.** #170/#172 classify/read decisions;
   #175 stores Gold; #179 computes reports from fixtures; #103 builds the
   authenticated synthetic shell; #119 builds replay. #232 can strengthen the
   shared repository contract before SQLite acceptance. These are not one
   serial queue.
3. **Complete warehouse behavior and operations.** #171 → #173; Gold operating
   integration after #175; #176 consumes the complete classification, decision,
   window and storage seams and the correctness fixes. #121 restores supported
   stages after replay and Gold operating integration are ready.
4. **Connect readers and the correction workflow.** #104 after #103/#179;
   #180 after #175/#179; Gold review discovery after #173/#175; #178 after
   #172/#173/#176 plus usable review; #177 after #176. #181 verifies source
   independence. #217 checks the actual monthly import path; #253 checks
   published invariants alongside the correctness fixes.
5. **Accept the application in #111.** Verify the imported-data dashboard,
   repeat operation, correction, backup/restore, undo, privacy and household
   trial. A passing fixture demo or one first import is insufficient.

Native issue edges can express completion dependencies even when implementation
can begin with an agreed fixture. Keep that distinction explicit in briefs.

### New owner N1: Gold participates in migrations and complete backup sets

**Proposed title:** `Operations: migrate, back up and recover a profile with Gold`

**Prerequisites:** #175's store/stage interface, #188's remaining stage checks;
completed #174/#198 supply the existing runner/backup conventions. Its completion
blocks production completion of #176 and all-stage recovery acceptance in #121.

**Scope and acceptance:**

- Register Gold with the shared migration and profile/stage identity machinery;
  the serving application never creates or migrates schema.
- Include Gold in the supported complete backup set, manifest, checksum,
  integrity and lost-store rules. Older Bronze-only and Bronze/Silver backup
  sets retain explicit supported behavior.
- A synthetic production profile can migrate Gold, import/build/publish, back
  up all stores and import/build again with Gold already present.
- Preserve coherent store/input state and the existing writer lock. A failed
  backup or migration cannot be reported as a successful complete operation.
- Specify the boundary with #121: N1 creates/verifies complete sets and supplies
  stage adapters; #121 restores them and replays the agreed catch-up path.
- Exercise supported interruption/retry cases without touching real profiles.
  Full legacy-publication conversion belongs to the later history release.

This is the missing counterpart of completed Silver backup issue #198. Merely
adding a Gold schema in #175 does not satisfy it.

### New owner N2: the operator can find Gold review items

**Proposed title:** `Review: list Gold classification items and decision targets`

**Prerequisites:** #173's final classification/review semantics and #175's
published read surface. The integration walkthrough belongs to #178 and
depends on this read surface; do not make N2 depend on #178 in the opposite
direction.

**Scope and acceptance:**

- Extend the existing operator review route to expose open Gold rule conflicts,
  unmatched/ambiguous transfers and non-applicable decisions from one pinned
  publication, while retaining supported Silver review behavior.
- Supply the stable identifiers/handles and allowed details required to make
  a decision through #178. Do not make the deferred Kontrol screen mandatory.
- Define how the command behaves with no publication and while a new one is
  published; do not combine items/targets from different publications.
- Remain read-only and preserve routine-log privacy. Any additional terminal
  detail must respect the accepted command-output policy, not silently expand it.
- #178's synthetic W2 proves list → choose → decide → rebuild → resolved item.

If preferred, this can be an explicit bounded addition to #178 instead of a
new issue. Either way it needs one owner and acceptance evidence.

### Existing-owner amendments

- **#103:** passphrase provisioning (`set-passphrase`), accepted session policy
  and secure cookies, login throttling, logout and protected fragments.
- **#111:** production `serve` composition, startup/upgrade instructions, private
  read-only reporting and documented supported exposure. LAN/internet deployment
  remains separately authorized; 0.3 does not promise public hosting.
- **#121:** whole-profile versus individual-store recovery decision; restore
  all supported manifest stores, catch-up, and explicit backup-integrity
  verification. Do not claim deferred historical replay verification is built.
- **#250:** configuration and identity seam, including #254; **#176** owns final
  pipeline wiring. Consolidate #145's later-superseded instructions first.
- **#178:** keep its voided-run retry identity fix and Bronze conflict exception.
  The review extension does not replace these accepted requirements.
- **Operating docs:** mark `status`, `check`, full `verify` and other unbuilt
  command forms with their real delivery scope; either assign their minimum
  release form or stop claiming they ship in 0.3.

### Release acceptance checklist

All are independent acceptance evidence, using synthetic profiles for automated
checks. Household observations are a separate human activity.

1. Import an initial CSV set and then a later month through supported commands;
   Gold and complete backups exist after both, with an unchanged recipe a no-op.
2. Classify ordinary expenses/income/refunds and transfers; discover and resolve
   an ambiguous item through review/decide. Invalid decisions preserve state.
3. Reject known wrong-account duplicate incidents and invalid registry/Gold
   combinations according to the agreed policies. Complete coverage must not
   carry an older balance past an unresolved missing final balance.
4. Log in from phone and desktop; unauthenticated pages/fragments refuse access.
   Display exact analytics values and visible partial/no-data/provisional states.
5. Preserve publication pins across navigation/concurrent builds; stale responses
   cannot repaint current controls, and unavailable publications never silently
   become the latest result. Browser back/forward and empty selection work.
6. Correct an input, inspect the diff and undo; restore a complete supported
   backup into the agreed destination and perform the agreed catch-up. No
   integrity or recovery guarantee rests on an unimplemented command.
7. Keep financial payloads and private paths out of routine logs/browser storage;
   presentation reads only analytics, and a second synthetic source changes no
   analytics/presentation code.
8. Both household readers independently understand the overview and its trust
   explanation. Record limitations and follow-ups; do not call prototype QA
   household acceptance.

## 0.4: investigation and operations

**Existing scope:** #105, #106, #118, #151, #155, #187, #192, #223, #230.

Category/group detail and account activity extend the report contract through
their own owners. Kontrol shows published financial trust; #155 shows pipeline
operation. Keep the audiences and permitted data separate. #151's persisted
refusal reasons and #192's failure-logging guard precede the full stage history.
The shared busy-store mapping must cover real operations (#187), not just
migration. #118 adds full Bronze reparsing, while preserving import provenance.

**Gate:** a household reader can investigate a figure without losing context;
an operator can distinguish failed, refused, quarantined, skipped and interrupted
work, and maintain/reparse the installation through documented commands. Logs
contain no financial content. If `status`/`check` were deferred from 0.3, assign
explicit tickets here. Fix the accessible README link and update the checker
without weakening quality rules.

## 0.5: budgets and trends

**Existing scope:** #102 → #107 → #108, using #105's detail navigation.

#102 is a specification, not an input pipeline. Give #107 explicit end-to-end
ownership or create bounded children for budget validation, immutable Gold/
recipe projection and analytic comparison before building the screen. Accepted
scope is household TOML targets with exact account-scope applicability;
account-specific plan precedence stays a separate deferred requirement.

**Gate:** changing a target produces a new publication, old publications keep
their targets, missing targets differ from zero, partial plans do not invent a
complete household target, and selected-account mismatch is explained. Actuals
and plans use the correct grains. Phone/keyboard chart navigation and the exact
table alternative are usable. No budget editor, forecasting or commitments are
smuggled into ordinary comparison.

## 0.6: history and reproducibility

**Existing scope:** #109, #247. **Missing upstream delivery scope:**

- As-was pointer-history lookup, labels and deliberate result retention.
- Recipe/code-version replay, scratch build and fingerprint verification;
  as-known-at generation using the correct cutoff and today's approved inputs.
- Public history discovery/opening through analytics, including unavailable
  and legacy results, with the proper known-at reference date.
- Supported migration/legacy isolation and recovery. Name exactly which versions
  are convertible; retain unsupported results without pretending current code
  can read them.
- Raw configuration auditing (#247): decide bytes versus hashes and audit
  storage for no-op attempts before implementation.

#109 itself already asks for separate prerequisite tickets; create them before
claiming the milestone is ready. #109's present #106/#108 dependencies place the
history UI after diagnostics and budget trends. A smaller earlier history
feature would require an explicit split, not deleting those edges blindly.

**Gate:** select a historical publication and receive its own data, taxonomy,
plan and knowledge date; an as-known-at build is never accidentally current;
replaying the named recipe with supported code verifies the result. Retention,
unavailable and legacy behavior are honest and recoverable.

## 0.7: commitments, trips and refund notes

**Existing scope:** #99 → #110, #134, #159 and the reserve specification #112.

These can be separate small increments within the milestone. Planned monthly
rådighedsbeløb remains distinct from actual net cash flow. Refund notes remain
a review-only scratchpad; the decision log is the reproducible input. Trip tags
retain household actual expenses while excluding them from the explicitly
named everyday-budget comparison and comparing tagged funding at trip level.

#112 only defines reserve semantics. If reserve implementation is required in
this release, it needs approved delivery children and a revised effort estimate;
otherwise say that 0.7 resolves the policy and schedule delivery separately.
Splits, fee transfers and account-specific budget precedence also need their
own contracts and are not implied by “polish.”

**Gate:** independently worked cases cover annual bills, refunds, scope changes,
partial evidence, delayed transactions and historical edits. No transfer is
relabelled as a refund to make a budget look better, and no earmarked reserve
becomes a fictional bank account.

## 0.8: bank connections

**Existing scope:** #182 parser/account-number contract and #248 operative
registration documents. **Missing delivery initiative:** consented read-only
connector, authentication/callback/credential lifecycle, account/source mapping,
raw API evidence and source-record ingestion, retries/idempotency, and clear
expired-consent/failure behavior. Scheduled ingestion is a separately scoped
child if needed, not automatically part of the policy-doc issue.

No provider API, legal or pricing research was undertaken in this audit. Provider
requirements must be verified when those implementation/setup tickets are
specified. #249's heading-only templates are not completed privacy/terms
documents; neither #248 nor that PR implements bank access.

**Gate:** source contract examples prove both successful and interrupted/repeated
imports, the operator can revoke/re-establish access, actual consent and setup
are owner-authorized, and financial reporting consumers stay unchanged. Keep CSV
import as a supported path. This milestone is an outcome proposal pending the
connector's missing scope; it is not currently ready for autonomous execution.

## What 1.0 should mean

Proposed meaning: **the household can rely on the agreed workflows, maintain
the installation and recover its data without an agent babysitting normal use**.
It is not “every GitHub issue is closed.” Agree the final must-have feature list
after the 0.3 and budget household trials reveal actual needs.

Suggested release conditions are accurate/trust-labelled reports, repeatable
upgrades and recovery, understandable onboarding and monthly operations,
accessible core flows, documented supported platforms/exposure, and no unresolved
material correctness/security/data-loss findings. Packaging (#209) is required
only if a distributable install becomes part of that supported model; clean
checkouts already have an operating contract.

Forecasts, subscription detection, browser editing and broader account planning
are in vision/prototype history but lack sufficiently scoped delivery issues.
Keep them visible as uncommitted initiatives with decision owners. They may
continue after 1.0 unless the owner explicitly includes them. Optional fixture,
wording and formatting issues never need to reach zero.

## Concrete tracker change set

- Create 0.4–0.8 with the outcomes/gates above; keep dates unset.
- Keep 0.3's name and revise its description to say that presentation consumes
  analytics over Gold, with actuals-only scope and working operation/recovery.
- Apply the exact per-issue assignment in the ledger. Resolve or consolidate
  the five listed closure candidates only after preserving their remaining
  acceptance; remove #2 from release gating without losing its roadmap links.
- Create N1/N2 or explicitly amend their chosen existing owners. Create the
  missing history/connector initiatives before marking those releases ready.
- Reconcile current-scope text and policy decisions before applying the proposed
  native dependencies; keep schema version numbers untouched.
- Re-check the complete resulting graph, including closed parents, for cycles,
  later-release prerequisites and references to closed duplicates.

This proposal is the reviewable result of the audit. Applying it is a separate
tracker-edit pass so outstanding domain decisions are not silently turned into
implementation instructions.
