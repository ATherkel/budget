# Kernel/Bronze continuation

Coordinator: Codex (GPT-6 Astra). Implementation: one installed native
astra_flash_builder, deepseek/deepseek-v4.1-flash, DeepSeek API.

## Existing decisions and baseline

Continue task 01a0b8f4-b59d-7e12-8dbc-5b2851eac4ab in this existing worktree,
branch codex/kernel-bronze, HEAD 387aa3a9e439a73b6e7726ce86aca4f04cc5b8ea.
The worktree has pre-existing uncommitted application, tests, packaging and
VS Code configuration. A source snapshot and status inventory are preserved at
../kernel-bronze-baseline-20260922. Do not attribute those files wholesale to
this continuation or discard them. The Bronze contract is unchanged against
the locally available origin/main d5544ef.

The user approved SQLite persistence and the BronzeStore import/read seam in
the prior task, and on 2026-09-22 explicitly approved completing this bundle
with internal test-first slices rather than per-test user review.

Subsequent user instruction authorizes local commits at each actual red boundary
before green implementation, and again after passing green verification. Use
test(red): and feat(green): or fix(green): headers, agent bot author/committer and
model trailers. Preserve honest chronology; do not fabricate earlier red stages.
This overrides the no-commit restriction below, but does not authorize pushing.

## One implementation and verification phase

Complete source-preserving local ingestion against docs/architecture/bronze-layer.md
and docs/agents/bronze-agent.md. Preserve existing public dataclass/read contracts
and all three existing tests. First make the existing account-conflict red test
green, then use focused sequential red/green slices for missing behaviors.

Acceptance:

- Exact bytes, SHA-256, decoded fields, ordinals, and private provenance survive
  reopening; source fields are not trimmed, typed, normalized, or mapped.
- Same-account repeats get their own dates and run ID and link to the original
  stored run without new payload/records. Cross-account attempts persist as
  refused, preserve original evidence, and never seed future account ownership.
- Strict Windows-1252 and exact header/CSV structural validation produce a
  retained payload/run plus deterministic FormatFailure and zero source records
  for malformed input. Never guess encoding or include source content/filenames
  in failure reasons. UTF-8's encoded Danish header must fail exact matching.
- Export date is explicitly supplied or taken solely from the filename suffix;
  missing/invalid export metadata fails clearly before persistence, without
  echoing private names. Explicit export dates take precedence, as before.
- Declared coverage dates outside [maximum source Dato, exported_on] persist as
  refused, never clamped. Read Dato only for coverage bounds, regardless of row
  ordering/status. Preserve its original string in records. Invalid Dato must
  not bypass safeguards or manufacture coverage: fail clearly and retain bytes.
- Missing coverage is allowed only if exported_on minus one day is in the
  maximum source Dato's reporting month (or earlier), and the proposed coverage
  is not before the last transaction. Otherwise persist a refused run. For
  missing declarations, the attempted exported_on fallback remains recorded in
  the existing nonnullable date fields, marked exported_on source; outcome
  refused prevents downstream admission. Do not imply this is admitted evidence.
- Undecodable/malformed payloads yield FormatFailure before the missing-coverage
  rule; retain attempted fallback date metadata, not invented transaction dates.
- Refused attempts retain payload/provenance and deterministic parsed records
  when available, but cannot count as a stored run or repeat origin. A corrected
  presentation of a previously refused payload can be stored without collision.
- Transactions remain atomic, use bound SQL, and preserve existing SQLite data.
  No destructive migrations. Unknown source formats fail clearly without guessing.
- Tests use synthetic inputs and real temporary SQLite stores through BronzeStore.
  Run focused tests per slice and the relevant full unittest discovery once at end.
  Check installed VS Code adapter discovery/current-file imports if practicable;
  distinguish configuration checks from an actual GUI debugger launch.

Ownership: Flash may edit kernel/, tests/, necessary packaging/VS Code fixes,
and its unique WORKER-REPORT.md in this directory. Preserve unrelated scaffolding;
do not rewrite it for style. Astra owns this plan and CHECKPOINT.md.

Non-goals: Silver/Gold, account configuration, financial interpretation, UI/CLI,
manual-decision file format or workflow (issue #10), publishing, Git operations
that mutate history, dependencies requiring network installation, production data.
Void-based reassignment is deferred pending the manual-decision input contract;
cross-account payload reuse remains refused until that dependency is integrated.

## Review and resume

Flash supplies changed-file list, red/green commands and outputs, final verification,
limitations and baseline-relative patch. Astra reviews actual changes and evidence
once through specification and quality/security lenses. At most one consolidated
correction cycle by default. Final acceptance does not claim the manual-decision
dependency or downstream kernel layers are complete. Local red/green commits are
authorized by the later instruction above; no pushes or deployment.
