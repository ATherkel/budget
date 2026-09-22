# Kernel/Bronze acceptance checkpoint

2026-09-22. Reviewed and accepted for the scoped local prototype by Codex
(GPT-6 Astra). Worker: /root/kernel_bronze_build, installed
astra_flash_builder / deepseek/deepseek-v4.1-flash. Worker is finished.

## State

Workspace: C:\Users\Therkel\Documents\GitHub\budget\.tmp\kernel-bronze
Branch: codex/kernel-bronze. Original HEAD: 387aa3a9e439a73b6e7726ce86aca4f04cc5b8ea.
Accepted application/report HEAD: 7cef91a. Initial uncommitted source snapshot:
../kernel-bronze-baseline-20260922. Source changes were reviewed relative to
that snapshot as well as against Git; the inherited VS Code fixes were unchanged.

Implemented account-conflict refusal, strict Windows-1252/header/quoted-field
validation and retained format failures, export/coverage safeguards, repeat and
refused-run persistence, and compatibility on re-presenting legacy payloads.
Source data and import history remain immutable. Only derived cache is reconciled.

The worker's full verification reports 12 unittest methods passing, including
parameterized cases, reopening SQLite, legacy-parser data, escaped/multiline
fields and quoted empty fields. Commands and red/green commit pairs are in
WORKER-REPORT.md and commit bodies. Astra checked actual source/test diffs,
original-test preservation, commit identities/trailers and git diff --check.
Targeted Astra reproductions confirmed two review defects before correction:
legacy failure plus stale records, and accepted unquoted stray quotes. Both
were fixed with red/green pairs. Acceptance of the quotation correction required
one further narrow pair for a trailing delimiter bypass. The final patch and
worker's passing targeted/full-suite evidence resolve those findings.

No full-suite duplicate run was performed by Astra. VS Code configuration and
current-file imports were checked; no live GUI debugger or Test Explorer run
is claimed. No push, merge, deployment, real bank data, or package installation.

## Accepted contract interpretations and limits

- Stored means retained in Bronze; format failures still prevent downstream
  admission. Malformed records produce zero source records.
- Explicit export dates retain precedence over filename suffixes. Dato uses
  DD-MM-YYYY as in the previously approved fixtures.
- Missing coverage records the attempted exported_on fallback, with outcome
  refused when the declaration is required. The fallback value is bounded by
  the last source date; its downstream evidence interpretation is separate.
- LF and trailing line breaks remain accepted; all fields must be quoted.
- No refusal-reason field, void API, or manual-decision workflow was invented.
  Issue #10 remains necessary for void-based cross-account reassignment.
- There is no independent rebuild API. Old lax-parser databases need payload
  re-presentation to acquire stricter verdicts; opening them alone does not replay.
- Pre-existing packaging scaffolding (.python-version, pyproject.toml, uv.lock,
  src/) and pre-existing __pycache__ directories remain untracked and untouched.

Routing doctor observed gpt-6-astra as root and the installed Flash v4.1 role
pinned to DeepSeek API. The native role performed the work. Provider request
metadata was not available to this acceptance review, so end-to-end inference
routing is unverified; static configuration alone is not runtime proof.

## Resume

Review the local red/green chain with git log --reverse --oneline 387aa3a..HEAD
from this worktree; use git show on each pair to walk from failed behavior to
passing implementation. All commits use agent bot identity and model trailers.
The existing task's initial two green slices are honestly checkpointed in the
first red commit; they were not retroactively split into invented history.

Next planning boundary: resolve issue #10's manual-decision input contract for
void-based reassignment, or scope the Silver continuation separately. This
acceptance completes the defined ingestion bundle, not every kernel layer.
