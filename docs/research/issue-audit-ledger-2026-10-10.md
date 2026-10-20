---
type: research
---
# Complete issue ledger, 10 October 2026

All **76 open issues** have exactly one proposed disposition below. This is a
snapshot and proposal, not a record of GitHub changes. See the [audit](issue-audit-2026-10-10.md)
for evidence and dependency interpretation, and the [release plan](release-plan-2026-10-10.md)
for exit criteria and missing work.

“Open blockers” means the **current native GitHub graph**, not blockers inferred
by this audit. A dash is not a guarantee of implementability: the action column
identifies missing dependencies and unresolved decisions. Closed blocker edges
are retained in the evidence but excluded from this scheduling view. Labels are
shown as recorded; no speculative ready/blocked label has been applied.

| Proposed disposition | Existing open issues |
| --- | ---: |
| 0.3 | 30 |
| 0.4 | 9 |
| 0.5 | 3 |
| 0.6 | 2 |
| 0.7 | 5 |
| 0.8 | 2 |
| Later | 2 |
| Polish | 17 |
| Close / consolidate | 5 |
| Roadmap | 1 |

New delivery owners in the release plan are **additional work**, not counted
as if an existing issue already covers them. “Close / consolidate” contains
recommendations requiring preservation of acceptance before closure; these
issues remain open in GitHub.

## 0.3

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#100](https://github.com/ATherkel/budget/issues/100) Implement the modular household dashboard from the #11 prototype | 0.3 First dashboard | — | `ready-for-agent` | Keep the explicitly amended closure rule: #111 completes the first-dashboard checkpoint even while later children stay open. It is an umbrella, not an executable ready task. |
| [#103](https://github.com/ATherkel/budget/issues/103) D2: Build the authenticated dashboard shell and shared navigation | 0.3 First dashboard | — | `wayfinder:task` | Can start using the accepted synthetic report adapter. Make set-passphrase and session invalidation/lifetime explicit; full pages and fragments share real authentication. |
| [#104](https://github.com/ATherkel/budget/issues/104) D3: Deliver the simple monthly actuals overview from analytics | 0.3 First dashboard | [#179](https://github.com/ATherkel/budget/issues/179), [#103](https://github.com/ATherkel/budget/issues/103) | `wayfinder:task` | Rendering owner only; calculations/validation belong to #179. Preserve all-category order, quiet unclassified note and local trust explanation. #179 is already a native blocker. |
| [#111](https://github.com/ATherkel/budget/issues/111) D10: Integrate the production report adapter and validate the first usable dashboard | 0.3 First dashboard | [#181](https://github.com/ATherkel/budget/issues/181), [#180](https://github.com/ATherkel/budget/issues/180), [#104](https://github.com/ATherkel/budget/issues/104), [#103](https://github.com/ATherkel/budget/issues/103) | `wayfinder:task` | 0.3 acceptance: authentic adapter, household trial and usable ongoing operation. Add explicit recovery/import-safety/undo/decision/Gold-operations gates; do not absorb missing warehouse implementation. |
| [#119](https://github.com/ATherkel/budget/issues/119) Bronze: replay history from the export archive and import log | Later | — | `ready-for-agent` | PROMOTE from Later: #121 needs archive replay and backup catch-up. #117 is closed. Share any future refusal-reason log changes with #151 without inventing historical metadata. |
| [#121](https://github.com/ATherkel/budget/issues/121) Bronze: restore backups and refresh development safely | 0.3 First dashboard | — | `ready-for-agent` | Missing native #119 blocker. Rewrite outdated Bronze-only scope for supported manifest stores; resolve single-store advice versus empty-profile restore and define verification scope before implementation. |
| [#150](https://github.com/ATherkel/budget/issues/150) Import: stop on identical exports under different accounts (duplicate incidents) | Later | — | `needs-triage` | PROMOTE input safety: known duplicate incidents can assign exports to the wrong account. Settle the already identified continue-clean-files-only policy before execution. |
| [#170](https://github.com/ATherkel/budget/issues/170) Gold 4: classify by rules, with refunds, adjustments, allocations, lineage and review items | 0.3 First dashboard | — | `ready-for-agent` | Rule classification/allocation/lineage foundation. Upstream #168/#169 and PR #166 are complete. Resolve #243's taxonomy contract alongside this without manufacturing financial policy. |
| [#171](https://github.com/ATherkel/budget/issues/171) Gold 5: match transfers on claimed, cancelling legs | 0.3 First dashboard | [#170](https://github.com/ATherkel/budget/issues/170) | `ready-for-agent` | Transfer matching follows #170. Add #241 policy-location decision; automatic/manual matching must retain exact cancellation and named evidence. |
| [#172](https://github.com/ATherkel/budget/issues/172) Decisions 1: read and validate decisions.jsonl into effective decisions | 0.3 First dashboard | — | `ready-for-agent` | Decision-log reader can start: #168 and PR #166 are complete. Effective decisions and prefix hash underpin #173/#176/#178. |
| [#173](https://github.com/ATherkel/budget/issues/173) Gold 6: apply manual decisions to classification | 0.3 First dashboard | [#172](https://github.com/ATherkel/budget/issues/172), [#171](https://github.com/ATherkel/budget/issues/171) | `ready-for-agent` | Manual Gold decisions follow #171/#172. Its completion should block the real classified pipeline #176, not only later integration tests. |
| [#175](https://github.com/ATherkel/budget/issues/175) Publication 2: gold.db stores publications and serves GoldPublications | 0.3 First dashboard | — | `ready-for-agent` | SQLite Gold store can proceed from closed #167/#174. Shared selection contract #232 is a coordinated prerequisite; NEW Gold migration/backup integration follows this store seam. |
| [#176](https://github.com/ATherkel/budget/issues/176) Publication 3: pipeline build and rebuild from a recorded recipe | 0.3 First dashboard | [#172](https://github.com/ATherkel/budget/issues/172), [#175](https://github.com/ATherkel/budget/issues/175) | `ready-for-agent` | Add classification completion #173, window contract #250 and registry/coverage correctness #237/#238/#239; NEW Gold operations integration is required for production. Avoid mutual #250/#176 blockers. |
| [#177](https://github.com/ATherkel/budget/issues/177) Publication 4: print the build diff and undo | 0.3 First dashboard | [#176](https://github.com/ATherkel/budget/issues/176) | `ready-for-agent` | Build diff and undo remain explicit 0.3 operational scope. #176 is already recorded. Include undo in #111's operational acceptance. |
| [#178](https://github.com/ATherkel/budget/issues/178) Decisions 2: decide through the validation boundary | 0.3 First dashboard | [#173](https://github.com/ATherkel/budget/issues/173), [#176](https://github.com/ATherkel/budget/issues/176), [#172](https://github.com/ATherkel/budget/issues/172) | `ready-for-agent` | Decision validation, append and rebuild remain 0.3. Add Gold review discovery to W2's ownership; retain voided-import retry/account-conflict fixes from its comment. |
| [#179](https://github.com/ATherkel/budget/issues/179) Analytics 1: monthly household report over GoldRepository | 0.3 First dashboard | — | `ready-for-agent` | May start against Gold fixtures; do not add a storage/pipeline blocker. Own computations, selection validation and selection_options; settle #252's contradictory coverage wording. |
| [#180](https://github.com/ATherkel/budget/issues/180) Analytics 2: report context opens one publication | 0.3 First dashboard | [#175](https://github.com/ATherkel/budget/issues/175), [#179](https://github.com/ATherkel/budget/issues/179) | `ready-for-agent` | Production report adapter already waits for #175 and #179. It pins one publication and never silently replaces unavailable results. |
| [#181](https://github.com/ATherkel/budget/issues/181) End to end: a second synthetic source changes no analytics or dashboard code | 0.3 First dashboard | [#179](https://github.com/ATherkel/budget/issues/179), [#173](https://github.com/ATherkel/budget/issues/173), [#176](https://github.com/ATherkel/budget/issues/176) | `ready-for-agent` | Second synthetic source acceptance already waits for #173/#176/#179. It proves source independence, not a real bank connector. |
| [#188](https://github.com/ATherkel/budget/issues/188) Silver and Gold migrations need the busy-store refusal Bronze has | Later | — | `needs-triage` | PROMOTE remaining Gold-stage acceptance to 0.3. Shared runner already maps BUSY and Silver uses it; add stage-specific proof with #175/Gold integration, not duplicated mapping code. |
| [#217](https://github.com/ATherkel/budget/issues/217) Test: Silver is the same whether exports arrive month by month or all at once | Later | — | `enhancement`, `ready-for-agent` | PROMOTE production-path confidence: batch versus monthly import equivalence. #200 is closed; preserve normalization and same-export-date limitations. A found bug needs its own policy/repair scope. |
| [#232](https://github.com/ATherkel/budget/issues/232) Gold: reject a bare string for account_ids | Later | — | `bug`, `ready-for-agent`, `spare-time` | PROMOTE shared-contract correctness before SQLite/analytics integration. Reject bare-string account collections consistently; remove misleading spare-time label. No claim of an existing dashboard exploit. |
| [#237](https://github.com/ATherkel/budget/issues/237) Gold: a Silver transaction on an account missing from the registry | Later | — | `needs-triage` | PROMOTE: production Gold must not publish orphan account facts. Agree refusal policy, then block #176 completion; existing CLI protection does not cover the new stored-Silver path automatically. |
| [#238](https://github.com/ATherkel/budget/issues/238) Gold: quiet months after a last transaction with no stated balance read as complete | Later | — | `needs-triage` | PROMOTE: trustworthy coverage/balances required by the first real reports. Define trailing missing-balance policy and regress the reported case before production acceptance. |
| [#239](https://github.com/ATherkel/budget/issues/239) Gold: enforce invariant 14, no transaction after closed_on | Later | — | `needs-triage` | PROMOTE: enforce closed_on rather than publishing facts without managed-period coverage. Resolve together with #237 and gate #176. |
| [#241](https://github.com/ATherkel/budget/issues/241) Docs: is the transfer matching policy in the configuration snapshot or the code version? | Later | — | `needs-triage` | PROMOTE decision before transfer/pipeline work: code-pinned or configuration-pinned matching policy must have one normative statement. |
| [#243](https://github.com/ATherkel/budget/issues/243) Inputs: should taxonomy.toml require an income category and refuse type names as category IDs? | Later | — | `needs-triage` | PROMOTE small contract decision before classification acceptance: reconcile taxonomy prose, valid examples and loader obligations. Do not impose reserved IDs/income categories without deciding the rule. |
| [#244](https://github.com/ATherkel/budget/issues/244) Inputs: case-insensitive patterns fingerprint by their case | Polish | — | `needs-triage` | PROMOTE a no-op contract decision, not necessarily a mandatory refactor: literal case folding or precise narrowing of #176's same-meaning promise. Do not attempt regex semantic equality. |
| [#250](https://github.com/ATherkel/budget/issues/250) Load the late-booking window from the profile and record it in the recipe | 0.3 First dashboard | — | `ready-for-agent` | Current late-booking owner in 0.3. Absorb #145/#254; settle allowed integer minimum; own profile/recipe identity seam, with #176 responsible for final pipeline wiring. |
| [#252](https://github.com/ATherkel/budget/issues/252) Gold contract: coverage_start promises complete months the managed period never has | Later | — | `needs-triage` | PROMOTE contract clarification: managed period starts at first booked transaction under current accepted model. Proposed fix is wording; changing the grain would require a separate policy decision. |
| [#253](https://github.com/ATherkel/budget/issues/253) Gold tests: check contract invariants 10 and 12 on every build | Later | — | `needs-triage` | PROMOTE invariant acceptance alongside #238/#239; use on representative builds and do not hide known failures. It verifies contract, not a new feature. |

## 0.4

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#105](https://github.com/ATherkel/budget/issues/105) D4: Add category investigation and reusable detail navigation | Later | [#104](https://github.com/ATherkel/budget/issues/104) | `wayfinder:task` | Category/group investigation and reusable detail route; includes its report-contract extension and household investigation trial. Follows overview. |
| [#106](https://github.com/ATherkel/budget/issues/106) D5: Add advanced account activity and isolated Kontrol diagnostics | Later | [#105](https://github.com/ATherkel/budget/issues/105), [#104](https://github.com/ATherkel/budget/issues/104) | `wayfinder:task` | Advanced account activity and Kontrol, including its analytics contract. Preserve separation from #155 operator stages; not required for 0.3's local trust explanation. |
| [#118](https://github.com/ATherkel/budget/issues/118) Bronze: rebuild source records from retained payloads | Later | — | `ready-for-agent` | Retained-payload reparsing; #113 is already merged. Deliver the full Bronze rebuild path in 0.4; preserve provenance and import history. |
| [#151](https://github.com/ATherkel/budget/issues/151) Bronze: record why an import run was refused | Later | — | `needs-triage` | Persist refusal reason codes and replay them. #113 has merged: do not follow the obsolete edit-migration-0001 suggestion. Coordinate replay compatibility with #119. |
| [#155](https://github.com/ATherkel/budget/issues/155) Operator: show each pipeline run as red/green stages (Bronze, Silver, Gold, publish) | Later | — | `enhancement`, `needs-triage` | Stage history/diagnostics in 0.4. Add #150/#151/#192/#176 completion prerequisites and decide CLI/static/page form. Existing finished-command logs are not complete stage history. |
| [#187](https://github.com/ATherkel/budget/issues/187) Refuse a busy Bronze store with exit 4 in commands other than migrate | Later | — | `needs-triage` | Still substantive: shared migration BUSY handling does not catch arbitrary later store-operation BUSY failures. Refresh obsolete no-import-command description and cover actual command behavior. |
| [#192](https://github.com/ATherkel/budget/issues/192) Import command: keep OS error paths out of routine logs | Later | — | `needs-triage` | Current logs whitelist completion data; do not assert an observed leak. Preserve OS-error path exclusion as acceptance before #155 adds failure telemetry. |
| [#223](https://github.com/ATherkel/budget/issues/223) Fix the code ty 0.0.85 flags, then relax the ty pin | Later | — | `needs-triage` | 0.4 maintenance: code fixes and unpinning with all current quality gates. Existing pinned checker works; do not loosen diagnostics to make the update pass. |
| [#230](https://github.com/ATherkel/budget/issues/230) README: the Silver walkthrough's link to the ranges file reads only 'see above' | Later | — | `needs-triage` | 0.4 accessibility/documentation: name the ranges-file link target. Fix remains present; a new global CI rule is a separate optional decision. |

## 0.5

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#102](https://github.com/ATherkel/budget/issues/102) D1: Specify immutable monthly budget inputs and reporting history | Later | — | `wayfinder:task`, `ready-for-agent` | Budget contract/specification, then implementation under #107. Needs owner decisions on immutable plan inputs, account scope, completeness and history. No 0.3 dependency. |
| [#107](https://github.com/ATherkel/budget/issues/107) D6: Deliver read-only monthly budget comparisons and elapsed-month markers | Later | [#105](https://github.com/ATherkel/budget/issues/105), [#104](https://github.com/ATherkel/budget/issues/104), [#102](https://github.com/ATherkel/budget/issues/102) | `wayfinder:task` | Deliver budget ingestion/publication and comparison end to end after #102, with exact-scope availability and missing/zero distinctions. No browser editor. |
| [#108](https://github.com/ATherkel/budget/issues/108) D7: Deliver accessible actual-versus-budget trends and spending drill-down | Later | [#107](https://github.com/ATherkel/budget/issues/107), [#104](https://github.com/ATherkel/budget/issues/104) | `wayfinder:task` | Accessible actual-versus-budget trends and exact-table equivalent. Existing #107 blocker means this is not a standalone actuals-only trend ticket. |

## 0.6

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#109](https://github.com/ATherkel/budget/issues/109) D8: Add historical Publication navigation and concurrent-read recovery | Later | [#180](https://github.com/ATherkel/budget/issues/180), [#108](https://github.com/ATherkel/budget/issues/108), [#106](https://github.com/ATherkel/budget/issues/106), [#104](https://github.com/ATherkel/budget/issues/104) | `wayfinder:task` | History picker plus historical acceptance, not base publication pinning. Needs NEW upstream history/replay/retention/legacy owners; existing blockers alone are insufficient. |
| [#247](https://github.com/ATherkel/budget/issues/247) Recipes: record each configuration file's raw SHA-256 beside the canonical snapshot | Later | — | `needs-triage` | History/audit release: decide hashes versus retained bytes and what stores provenance for a canonical-equal no-op attempt. Do not add it as a blanket #175 blocker. |

## 0.7

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#99](https://github.com/ATherkel/budget/issues/99) Define fixed-expense treatment and planned rådighedsbeløb | Later | — | — | Decide fixed/other expenses and planned rådighedsbeløb before #110. Later comments defer this after the first app; its old first-release budget wording is superseded. |
| [#110](https://github.com/ATherkel/budget/issues/110) D9: Follow-up: implement fixed expenses and planned monthly rådighedsbeløb | Later | [#99](https://github.com/ATherkel/budget/issues/99), [#107](https://github.com/ATherkel/budget/issues/107), [#104](https://github.com/ATherkel/budget/issues/104), [#102](https://github.com/ATherkel/budget/issues/102) | `wayfinder:task` | Implement #99's fixed/other and planned-income/commitment contract after ordinary budgets. Update directions that send new progress to closed #11. |
| [#112](https://github.com/ATherkel/budget/issues/112) F1: Follow-up: specify selected-category carry-forward and earmarked savings | Later | [#102](https://github.com/ATherkel/budget/issues/102) | `wayfinder:task` | Reserve/carry-forward specification only. Schedule policy in 0.7, but create a separate delivery owner before claiming reserves ship. Do not reuse prototype arithmetic as policy. |
| [#134](https://github.com/ATherkel/budget/issues/134) Note an expected refund from the phone before the bank books it | Later | — | `ready-for-agent` | Add #178 blocker; Gold review also needs an owner. Consolidate settled comments into current contract: .xlsx scratchpad, openpyxl, refund-of, both date systems and table behavior. No spreadsheet reads during builds. |
| [#159](https://github.com/ATherkel/budget/issues/159) Trip tags: measure holiday spending against the trip, not everyday budgets | Later | [#107](https://github.com/ATherkel/budget/issues/107), [#102](https://github.com/ATherkel/budget/issues/102) | `needs-triage` | Implement settled trip-tag direction, not rejected funding links. Define tag authoring/history and clearly distinguish everyday-budget actuals from unchanged household actuals. Existing #102/#107 blockers are appropriate. |

## 0.8

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#182](https://github.com/ATherkel/budget/issues/182) Parsers: state that a declared account number must match the filename's exact form | Later | — | `needs-triage` | Parser-number canonical form decision/documentation before real additional sources. No evidence of a present Danske mismatch; coordinate with connector design rather than blocking all analytics. |
| [#248](https://github.com/ATherkel/budget/issues/248) Docs: add privacy notice and Terms and Conditions for personal Enable Banking use | Later | — | `documentation`, `needs-triage` | 0.8 connector-readiness documentation, NOT connector implementation. PR #249 is scaffolding only and does not close this acceptance. Actual connector needs new tickets and owner inputs. |

## Later

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#114](https://github.com/ATherkel/budget/issues/114) Pair transfers that lose a fee once splits exist | Later | — | `enhancement` | Keep in a small uncommitted design queue until splits AND mixed transfer/fee semantics have owners. Ordinary category splits alone do not allow a transaction to be partly transfer and partly expense. |
| [#209](https://github.com/ATherkel/budget/issues/209) Packaged installs: name the code version without a Git checkout | Later | — | `needs-triage` | Uncommitted packaging prerequisite. Clean-checkout deployment is supported by current policy; no need to require wheel/binary delivery for 0.3. |

## Polish

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#163](https://github.com/ATherkel/budget/issues/163) Tests: build accounts.toml entries explicitly instead of slicing the fixture by line | Polish | — | `needs-triage` | Optional fixture construction cleanup; positional line slicing still exists on main. No production behavior change. |
| [#164](https://github.com/ATherkel/budget/issues/164) Tests: pin the account-number reader's independence from the date suffix, and refuse format = 1.0 | Polish | — | `needs-triage` | Guard tests for already-working parser independence and exact TOML format type; optional maintenance, not a current bug. |
| [#165](https://github.com/ATherkel/budget/issues/165) Inputs: say which account's folder a misfiled export belongs in | Polish | — | `needs-triage` | Improve misfiled-export advice while retaining privacy; normal import behavior already refuses it correctly. |
| [#183](https://github.com/ATherkel/budget/issues/183) Inputs: say what shape a bank_account_number must have | Polish | — | `needs-triage` | Optional clearer expected-number-shape diagnostic, without echoing the private number. |
| [#185](https://github.com/ATherkel/budget/issues/185) Decide the exit status for a Bronze store file that is not a SQLite database | Polish | — | `needs-triage` | Owner explicitly accepts rare non-SQLite exit-1 behavior for now. Keep optional; do not silently promote it into release-blocking damage recovery. |
| [#189](https://github.com/ATherkel/budget/issues/189) Profile files: refuse embedded NUL characters as configuration errors | Polish | — | `bug` | Keep owner-approved optional NUL-path diagnostic fix. No new evidence justifies overriding its explicit nonblocking classification. |
| [#205](https://github.com/ATherkel/budget/issues/205) Silver walkthrough: April's opening balance does not follow March's | Polish | — | `needs-triage` | Optional synthetic balance-story correction; retain deliberate within-export break and README parity. |
| [#206](https://github.com/ATherkel/budget/issues/206) Rebuild summary: the account line counts runs and transactions without saying which | Polish | — | `needs-triage` | Optional summary unit labels; bundle with #207 but preserve both distinct acceptance points. |
| [#207](https://github.com/ATherkel/budget/issues/207) Rebuild summary: 'admitted' on the account line, 'accepted' on the run lines | Polish | — | `needs-triage` | Optional admitted/accepted terminology cleanup on the same summary as #206. |
| [#233](https://github.com/ATherkel/budget/issues/233) Gold: say in GoldRepository that records come in no fixed order | Later | — | `documentation`, `ready-for-agent`, `spare-time` | Optional protocol ordering clarification; coordinate early with #175/#179. Financial consumers should already avoid unspecified row order; normative-doc addition retains its owner decision. |
| [#234](https://github.com/ATherkel/budget/issues/234) Gold worked example: compare late_bookings_settled with gold-layer.md | Later | — | `documentation`, `ready-for-agent`, `spare-time` | MOVE to Polish: add doc/fixture parity for flags already correct; prove the guard with mutation. #231 is merged. |
| [#235](https://github.com/ATherkel/budget/issues/235) Gold worked example: build GoldCategory rows with keyword arguments | Polish | — | `ready-for-agent`, `spare-time` | Already Polish: optional keyword arguments in worked fixtures. Remove redundant spare-time label. |
| [#240](https://github.com/ATherkel/budget/issues/240) Gold build: tidy BalanceEvidence and the per-account history grouping | Polish | — | — | Optional BalanceEvidence/public-type and grouping cleanup. Absorb duplicate #255's precondition requirement. |
| [#245](https://github.com/ATherkel/budget/issues/245) Inputs: refuse a rule whose amount or date range is empty | Polish | — | `needs-triage` | Optional validation of empty rule ranges; existing documented rules do not prohibit them. No current runtime failure asserted. |
| [#246](https://github.com/ATherkel/budget/issues/246) Inputs: name extra known keys directly, and cache the snapshot fingerprint | Polish | — | `needs-triage` | Optional explicit known-key handling and fingerprint caching; no new architecture prerequisite. |
| [#251](https://github.com/ATherkel/budget/issues/251) Gold tests: pin the inclusive range bounds in coverage and late_bookings_settled | Later | — | `needs-triage` | MOVE to Polish: boundary guards for already-correct inclusive comparisons. Good to bundle with #238/#250, but not evidence of a present bad report. |
| [#256](https://github.com/ATherkel/budget/issues/256) Docs: re-wrap the prose lines PR #236 lengthened | Later | — | `needs-triage` | MOVE to Polish: source wrapping only, rendered meaning unchanged. |

## Close / consolidate

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#145](https://github.com/ATherkel/budget/issues/145) Presentation: make the late-booking window a config value | Later | [#111](https://github.com/ATherkel/budget/issues/111) | `enhancement`, `ready-for-agent` | Supersede into #250 after preserving immutable-history requirements and explaining the later ruling. Its existing #111 blocker must not carry over to the 0.3 window owner. |
| [#186](https://github.com/ATherkel/budget/issues/186) CLI exit-4 list names Bronze refusals that migrate cannot raise | Polish | — | `needs-triage` | CLOSE candidate: current CLI comment describes all-stage store refusals and real import/review/rebuild commands exist. The issue's keep-and-explain option is satisfied. |
| [#208](https://github.com/ATherkel/budget/issues/208) budget review prints nothing when no items are open; the README shows a message | Polish | — | `needs-triage` | CLOSE candidate: #229/README now mark the empty-review annotation as script text, and the script only emits it on successful silent review. |
| [#254](https://github.com/ATherkel/budget/issues/254) gold.build: take the late-booking window as a whole number of days | Later | — | `needs-triage` | FOLD whole-day/public-seam validation and minimum decision into #250, then close after acceptance is preserved. Avoid a second window implementation. |
| [#255](https://github.com/ATherkel/budget/issues/255) BalanceEvidence.of: state or remove its non-empty-history precondition | Later | — | `needs-triage` | DUPLICATE of #240 item 1; fold and close. Current caller guards empty history; no observed production failure. |

## Roadmap

| Issue | Current milestone | Open blockers | Current labels | Audit disposition / remaining work |
| --- | --- | --- | --- | --- |
| [#2](https://github.com/ATherkel/budget/issues/2) Plan the first usable household warehouse and dashboard | 0.3 First dashboard | — | `wayfinder:map` | Roadmap-only parent, not a delivery gate. Clarify whether planning is complete or this becomes the ongoing roadmap; replace unavailable old decision links. Keep #100 as the 0.3 acceptance umbrella. |

## Snapshot checks

- 76 distinct issue numbers, no omitted or multiply assigned issue.
- Current milestone counts: 18 in 0.3, 42 in Later, 16 in Polish.
- 58 native blocker edges, including 40 pointing to open issues; no cycle.
- 18 issues have an open native blocker; 8 of those carry `ready-for-agent`.
- Every open issue's fetched comment count matches GitHub's reported total.
- No pagination remains on the issue/dependency/sub-issue connections.

The two open PRs are [#142](https://github.com/ATherkel/budget/pull/142)
(historical dashboard prototype/specification) and
[#249](https://github.com/ATherkel/budget/pull/249) (policy-document scaffolds).
Neither is treated as a completed product feature or silently merged.

