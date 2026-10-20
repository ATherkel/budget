---
type: research
---
# Issue audit: release scope and architecture, 10 October 2026

This is a durable research record, not an approved change to financial policy,
issue status, or release commitments. The owner confirmed during the audit that
**0.3 means an authenticated monthly actuals dashboard from CSV exports**;
budgets and bank connections follow later. Recommendations below preserve that
boundary. The root audit owns the complete issue allocation and the comparison
with GitHub's native blocking graph.

## Evidence and coverage

Reviewed the bodies of all 76 open issues in the downloaded GitHub snapshot,
their available comments, the five milestone descriptions and both open PR
descriptions. Read the glossary, roadmap, vision, presentation and publication
contracts, relevant operating rules, budget/forecast domain documents, ADR-008
and ADR-015, and the current CLI, review, migration and backup boundaries.
The checkout is detached at
`1fb24037f9144dff9b9cc02ce6efb8b28efb6323`; it is not current main. Source findings
were subsequently corroborated through `git show`/`git grep` against
`origin/main` at `9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75`, and differences in
the cited operating, presentation and Gold contracts were read. Backup,
migration, CLI and review source files are identical at both revisions. No
private exports or operator stores were read, and no application tests were
needed for this scope audit.

Issue and PR links below identify live sources; their wording can change after
this date. Findings distinguish confirmed text/code discrepancies from proposed
release choices. Native blocking edges were not independently re-audited here.

## Findings that affect the first usable application

### R1. Gold storage needs operational integration before production imports

**Evidence:** [#175](https://github.com/ATherkel/budget/issues/175) owns the Gold
schema, persistence and `GoldPublications`, but does not explicitly own expansion
of backup sets and migration orchestration. At the inspected main revision,
[`backups.py`](../../src/budget/backups.py) names `gold.db` and `gold` as uncovered
stores; `_covered_stores` includes Bronze and optional Silver only.
`require_backup_allowed` rejects uncovered stores before commands write.
[`migration.py`](../../src/budget/migration.py) registers Bronze and Silver only.
The [backup contract](../architecture/operations.md#backup-and-restore) documents
this temporary refusal. [#111](https://github.com/ATherkel/budget/issues/111)
assumes migrations/Profile guards and expressly does not absorb warehouse work.

**Consequence:** creating `gold.db` without expanding these boundaries leaves a
dashboard that can read one publication but breaks the ordinary production
import/backup cycle. This is a concrete integration dependency, not optional
operator polish.

**Recommendation:** explicitly assign a bounded 0.3 slice for Gold stage
registration, Profile/schema guards, inclusion in consistent backup sets and
manifests, missing-Gold recovery rules, and the existing import backup preflight.
Put it under #175 or give it its own ticket; require it before production wiring
is accepted in #111. Test a second production-profile synthetic import after
Gold exists, not just the first publication. Keep future legacy-publication
migration behavior in its later history release.

### R2. Restore scope and its operator advice do not yet agree

**Evidence:** [#121](https://github.com/ATherkel/budget/issues/121) says Bronze
restore only, depends on archive replay
[#119](https://github.com/ATherkel/budget/issues/119), and excludes a complete
warehouse restore. Its later comments require restoring every store in a backup
manifest after Silver support landed. A second comment identifies the conflict
between advice to restore one missing Silver store beside live Bronze and the
accepted rule that restore writes only into a profile with no stores.
The [operating contract](../architecture/operations.md#backup-and-restore)
additionally says restore ends with `verify`, while
[publication first-release scope](../architecture/publications.md#first-release-scope)
explicitly defers full recipe replay verification.

**Recommendation:** rewrite #121's current acceptance contract before execution.
Resolve whole-profile versus individual-store recovery explicitly, preserve
consistent stage/input history, name its Silver and Gold scope, and distinguish
backup checksum/SQLite integrity verification from later recipe-replay `verify`.
Because #121 is already a 0.3 commitment, its required #119 work cannot remain
an indefinite Later prerequisite. If reducing scope, record the exact supported
recovery path and limitation on #111 rather than claiming full disaster recovery.

### R3. The operator cannot discover Gold review work through the existing CLI

**Evidence:** [`reviewing.py`](../../src/budget/reviewing.py) reads Silver review
items only. [#170](https://github.com/ATherkel/budget/issues/170),
[#171](https://github.com/ATherkel/budget/issues/171), and
[#173](https://github.com/ATherkel/budget/issues/173) publish Gold classification
review items. [#178](https://github.com/ATherkel/budget/issues/178) implements
`decide` and its validation boundary, but does not explicitly extend `review`.
[W2](../architecture/operations.md#w2-settling-a-review-item) and
[the command contract](../architecture/operations.md#commands) promise a route
from visible review items to a decision. The full Kontrol screen
[#106](https://github.com/ATherkel/budget/issues/106) is deliberately deferred.

**Recommendation:** assign Gold `review` enumeration, safe details and usable
target handles to #178 or a separate 0.3 ticket. A reader seeing incomplete
classification in the overview must have an operator route that can actually
find and resolve it. Do not make #106 a new first-release blocker.

### R4. Passphrase provisioning needs a named owner; other promised commands

**Evidence:** [#103](https://github.com/ATherkel/budget/issues/103) owns real
authentication and the passphrase policy. [#111](https://github.com/ATherkel/budget/issues/111)
owns real startup. Neither explicitly names `set-passphrase`; the
[commands table](../architecture/operations.md#commands) does. Current
[`cli.py`](../../src/budget/cli.py) exposes only migrate, backup, rebuild, import
and Silver review. `check` and `status` are also documented but absent and have
no clearly named owner among the open tickets.

**Recommendation:** put passphrase provisioning and `serve` wiring explicitly
in #103/#111's acceptance map. Decide whether `check` and `status` ship in 0.3
or are documented as later; the first useful app need not wait for a run-history
UI. Do not treat a demo login or manually assembled fixture server as completion.

### R5. Financial correctness issues in Later can undermine 0.3 trust

**Evidence and disposition:**

| Issue | Why release placement deserves changing |
| --- | --- |
| [#238](https://github.com/ATherkel/budget/issues/238) | A trailing missing bank balance can produce quiet months marked complete with an older, incorrect balance. This directly contradicts trustworthy coverage, even if the simple overview does not display balances yet. Recommend a 0.3 correctness gate. |
| [#237](https://github.com/ATherkel/budget/issues/237) | Gold can publish orphan account facts when the registry omits an account in stored Silver. The issue's comment identifies #176 as the future path making this reachable. Set the refusal policy before that path ships. |
| [#239](https://github.com/ATherkel/budget/issues/239) | Facts after `closed_on` lack matching managed-period snapshots. Set registry/Silver disagreement policy together with #237 before production Gold. |
| [#252](https://github.com/ATherkel/budget/issues/252) | The `coverage_start` description promises quiet complete months that the managed-period grain excludes. Clarify before #179 bakes in consumer assumptions; keeping the accepted grain is the smaller proposed change. |
| [#232](https://github.com/ATherkel/budget/issues/232) | A bare string account selection can be a substring filter in memory and a character collection in SQLite. Cheap shared-contract protection before #175/#179 provides real value. It is not evidence that validated dashboard selections currently trigger it. |
| [#251](https://github.com/ATherkel/budget/issues/251), [#253](https://github.com/ATherkel/budget/issues/253) | Boundary and invariant tests protect the exact coverage promises the dashboard advertises. Pair #253 with the #238 fix so its failing case is resolved, not merely hidden. |
| [#150](https://github.com/ATherkel/budget/issues/150) | Cross-account identical exports have already caused wrong-account imports in real operation. Strong candidate for 0.3 input safety, but its confirmation behavior remains an explicit owner question. |

Keeping a finding out of its originating PR is not evidence that it is safe to
leave out of the first usable release. Conversely, low-risk guard tests need
not all become independent hard blockers if their owning implementation slice
can carry the acceptance case.

## Conflicts, overlap, and stale instructions

### R6. Release numbering drift is widespread and changes what an agent builds

The [actual milestone 0.2](https://github.com/ATherkel/budget/milestone/5) is closed
and means the real-data CLI; [0.3](https://github.com/ATherkel/budget/milestone/2)
is the first dashboard. Most dashboard and Gold issue bodies still say
“0.2 First dashboard.” The dated scope amendments correctly preserve actuals
only, but use the old number. [#100](https://github.com/ATherkel/budget/issues/100)
also still says in one section that Gold 0.2 is proposed pending #12, although
its introduction says #12 is closed and PR #166 merged. **Gold contract 0.2 is
a schema version, not release 0.2: do not globally replace every `0.2`.**

[#2](https://github.com/ATherkel/budget/issues/2) calls itself an
implementation-readiness planning ticket, while #100 now names it the broader
product roadmap. Its completion criterion needs an explicit choice: close a
finished decision map, or redefine it as the roadmap parent. It should not
indefinitely block a release because it indexes later product decisions.

[#100](https://github.com/ATherkel/budget/issues/100) explicitly closes at the
first-dashboard checkpoint even while later children remain open. Preserve
that useful rule. [#99](https://github.com/ATherkel/budget/issues/99),
[#102](https://github.com/ATherkel/budget/issues/102),
[#107](https://github.com/ATherkel/budget/issues/107), and #100 retain historical
“first-release budget” wording; a concise current-scope header should beat
that historical text. [#110](https://github.com/ATherkel/budget/issues/110) and
[#112](https://github.com/ATherkel/budget/issues/112) still direct new progress
to closed #11, unlike the corrected later tickets.

[Open draft PR #142](https://github.com/ATherkel/budget/pull/142) mirrors an
older plan and explicitly promises first-release budgets. It must be marked
as historical prototype/reference scope or aligned before merge; it must not
silently supersede the current accepted scope. [The roadmap](../03-roadmap.md)
still says “Phase 0 — Contracts and Decisions (current)” and puts connectors
before budgets without reference to actual releases. Refresh it after release
outcomes are chosen.

### R7. Three late-booking-window issues need one current contract

[#145](https://github.com/ATherkel/budget/issues/145) records the owner's earlier
decision to wait until after the first dashboard: first a constant, then a
profile key when configuration exists. [#250](https://github.com/ATherkel/budget/issues/250)
is in 0.3 and records a later ruling for a profile key and fingerprinted recipe
value. [#254](https://github.com/ATherkel/budget/issues/254) covers public-seam
validation that can fold into #250. The two schedule instructions conflict even
though immutable-history intent agrees. Main's current Gold and presentation
contracts already state that a profile can choose a nondefault window, further
supporting #250 as the current direction rather than returning to a constant.

Recommend making #250 the authoritative current owner, explicitly citing the
superseding ruling before closing #145 as superseded; fold #254 acceptance into
it. Choose allowed minimum and whole-day validation once. #176 consumes that
value; it must never create a dependency cycle by making all of #250 wait for
#176 while #176 waits for #250. Separate the input/identity contract prerequisite
from the pipeline wiring integration, or execute one coherent bundle.

### R8. Some apparent polish is a higher-level acceptance conflict

[#244](https://github.com/ATherkel/budget/issues/244) calls case-sensitive
fingerprints for case-insensitive literal patterns harmless. But
[#176](https://github.com/ATherkel/budget/issues/176) requires rules restored to
the same meaning to publish nothing. `netto` versus `NETTO` is the issue's
concrete counterexample. Either normalize supported literal conditions before
publication ships, or narrow the no-op contract to specified canonical
equivalence. Do not attempt general regex semantic equivalence.

[#241](https://github.com/ATherkel/budget/issues/241) identifies two normative
documents disagreeing over transfer policy in configuration identity versus
the code version. Resolve before #171/#176; stable code identity may already
preserve reproducibility, but the documented recipe must tell one story.

[#247](https://github.com/ATherkel/budget/issues/247) correctly keeps raw hashes
out of semantic identity, yet asks both that a formatting-only build publish
nothing and that every recipe retain exact raw input hashes. Define where
attempt-specific raw hashes live when no new recipe/publication is persisted.
Its title promises hashes, while its purpose asks to recover exact file text;
hash-only cannot do the latter. It can remain later after this design choice.

### R9. Consolidate duplicates without erasing distinct acceptance

[#255](https://github.com/ATherkel/budget/issues/255) is already fully contained
in item 1 of [#240](https://github.com/ATherkel/budget/issues/240). Fold it there.
[#254](https://github.com/ATherkel/budget/issues/254) and #250 have the overlap
described above. [#206](https://github.com/ATherkel/budget/issues/206) and
[#207](https://github.com/ATherkel/budget/issues/207) are distinct wording fixes
on the same summary line and make a sensible single cleanup bundle.

[#104](https://github.com/ATherkel/budget/issues/104) correctly adds #179 as its
analytics owner, but its original implementation/testing bullets still order
analytics computations and report tests. Rewrite the current action list so
#179 owns calculations and #104 owns rendering, including the basic trust
explanation. [#109](https://github.com/ATherkel/budget/issues/109) already
correctly distinguishes foundational pinning/recovery in #103/#104/#180 from
later historical navigation; preserve that split.

### R10. Future work has missing parents and unresolved domain seams

| Topic | Evidence and missing owner/decision |
| --- | --- |
| Historical publications | #109 explicitly says its upstream public history facilities are untracked future prerequisites. Create bounded tickets for scratch/replay and version selection, labels/retention, as-was/as-known-at commands, and legacy migration behavior; all are in [publications.md](../architecture/publications.md#past-views). |
| Splits and fee transfers | [#114](https://github.com/ATherkel/budget/issues/114) waits for splits but no open issue owns the split workflow/refund-allocation contract deferred by [ADR-008](../decisions/ADR-008-category-allocation-grain.md). Its proposed “transfer allocation” also conflicts with today's category-allocation/type rules; ordinary category splits alone do not decide mixed transfer-plus-fee transaction semantics. |
| Reserves | #112 specifies selected-category carry-forward and earmarking and requires a separate implementation plan. Completing #112 is not delivery of reserves; keep an implementation placeholder in the roadmap until the policy produces tickets. |
| Account-specific budgets | #100 explicitly guarantees future account-specific budgets and #102 preserves scope extension, but no open issue owns overlap/precedence decisions and delivery. Create a future decision/implementation owner rather than counting #107 as completion. |
| Phone refund notes | [#134](https://github.com/ATherkel/budget/issues/134) has substantial accepted follow-up decisions: `refund-of`, `openpyxl`, both spreadsheet date systems, blank-row behavior, Google Sheets editing an `.xlsx`, profile-named scratchpad. Promote that current contract above superseded options; retain dependencies on Gold decisions/review. Refund-of needs cycle/missing-target and eventual split-refund policy, not only file reading. |
| Trip budgets | [#159](https://github.com/ATherkel/budget/issues/159) is decided in comments: trip tags, category breakdown, tagged funding transfers, no funding links. Its body still asks already answered options. Budget comparisons intentionally exclude tagged expenses while household actuals retain them; define and label that comparison subtotal explicitly so the shared-actuals promise is not accidentally violated. Input/tag authoring and history remain open. |
| Connectors | [#248](https://github.com/ATherkel/budget/issues/248) owns policy documents only. [PR #249](https://github.com/ATherkel/budget/pull/249) is heading-only scaffolding and explicitly does not finish those policies. Neither owns connector ingestion, account consent, credentials/callbacks or operations; create the implementation initiative before promising a connected release. |
| Forecasts | [The vision](../00-vision.md), [roadmap](../03-roadmap.md) and [forecast domain](../domains/forecast.md) include forecasts and subscription detection, but the open issues do not provide implementation scope or acceptance. They should remain explicitly uncommitted until decisions exist. |

### R11. Several issue descriptions describe an obsolete code frontier

[#151](https://github.com/ATherkel/budget/issues/151) still suggests editing the
first Bronze migration if #113 has not merged; that branch of the instruction
is obsolete and unsafe for deployed stores. [#186](https://github.com/ATherkel/budget/issues/186),
[#187](https://github.com/ATherkel/budget/issues/187),
[#188](https://github.com/ATherkel/budget/issues/188), and
[#192](https://github.com/ATherkel/budget/issues/192) describe a world with no
import command or no Silver store, but both now exist. Recheck implementation
before scheduling; some work may already be absorbed. #217's old “wait for
#200/PR #210” text needs the same closed-prerequisite cleanup.

[#209](https://github.com/ATherkel/budget/issues/209) explicitly says its current
Git-checkout requirement is correct until packaging is chosen. Do not invent
a 0.3 packaging requirement merely to empty Later. Similarly, owner-approved
optional issues such as [#189](https://github.com/ATherkel/budget/issues/189)
should stay optional unless new evidence changes the impact.

## Proposed releases by user-visible outcome

These are sequencing recommendations, not dates or a claim that all product
scope is decided. The root audit should map every issue exactly once and check
that its prerequisite milestone is not later than its consumer's. Independent
decision work can proceed early without forcing all implementation into 0.3.

| Release | Outcome | Principal current owners and missing work | Exit evidence |
| --- | --- | --- | --- |
| **0.3 First usable actuals** | Import CSVs, resolve review items, publish, log in and understand a monthly household result. | Existing 0.3 Gold/publication/decision/report/shell tickets and #111; R1–R5 minimum operational/correctness closure, #119 if #121 retains catch-up. No budget/connector scope. | Two imports with Gold present; real adapter parity; private read-only HTTP pages/fragments; visible no-data/partial/provisional states; usable CLI correction and recovery; both household readers complete overview/explanation tasks. |
| **0.4 Investigate and operate** | Explain spending and account trust; diagnose and safely maintain the app. | #105, #106; remaining import/refusal/logging/busy-store hardening, #155 after UI choice; #118 if full Bronze reparse is wanted here. | Category/account detail ties to published totals; diagnostics stay outside Enkel; routine logs remain private; operator can understand a failed/unfinished run. |
| **0.5 Compare with plans** | Household monthly targets and actual-versus-budget trends. | #102 → #107 → #108, using #105; carry current-plan ingestion and immutable Publication integration as one end-to-end deliverable. | Missing/zero/partial targets and wrong scope are distinct; previous publications retain their plan; exact tables and keyboard/phone charts work; household budget trial passes. |
| **0.6 Explain history** | Browse trustworthy as-was and as-known-at reports, including their original plans. | New replay/scratch/labels/retention/legacy tickets → #109; #247 if exact-file audit is chosen. | Historical data, taxonomy, plan and reference date agree; old code/version refusal and unavailable/legacy recovery are explicit; a replay matches its fingerprint. |
| **0.7 Plan commitments and real-life exceptions** | Fixed commitments and rådighedsbeløb, trip spending, phone refund reminders; then precisely scoped reserves and splits. | #99 → #110; #134; #159 after #107; #112 decision plus new implementation owner; new splits owner → #114. | Independent examples preserve household spending, account balances, transaction/allocation reconciliation, immutable history and distinction between planned capacity and actual money left. Split further if this group becomes too large. |
| **Later initiatives, separately scoped** | Bank connections, packaging, forecasts, account-specific budgets. | Connector initiative with #248/#249 completion, scheduled ingestion; packaging decision → #209; forecast and account-plan contract tickets. | Each receives its own explicit outcome and acceptance before commitment. Avoid a fake “1.0 done” containing undefined vision work. |
| **Polish, no release gate** | Deliberate small cleanup. | Existing low-impact formatting, fixture and diagnostic wording fixes; #255 folded into #240; #256. | Normal quality gates; pick alongside touched areas. Correctness, security and needed accessibility are not automatically polish. |

An alternative is to move budget comparison ahead of advanced diagnostics if
that produces more household value; its actual dependencies are #102, #104,
#105 and the publication pipeline, not all of #106. The proposed sequence
respects #109's current dependency on trends; changing it would require
splitting history acceptance rather than silently deleting prerequisites.

## What “done” needs to mean

0.3 has an identifiable finish: #111's real working overview and household trial.
The rest currently mixes committed requirements, design questions, optional
improvements and broad vision. A useful 1.0 definition would name the smallest
complete household workflow the owner wants to rely on, then explicitly list
what can continue after 1.0. Do not require every optional issue to close.
Likewise, #100's first-dashboard closure must not erase its later children's
requirements. Maintain one release map and current issue contracts, with old
comments retained as decision history.
