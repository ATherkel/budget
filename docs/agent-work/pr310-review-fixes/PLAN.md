---
type: pr310-review-fixes
---
# PR #310 review fixes

Baseline: `7fa6165e160c8ebee3a5005ceaa542963a64a7ac`.
Branch: `codex/pr310-review-fixes`, locally stacked on
`claude/project-thread-niy7lg` using `agent-gh stack init`.

## Contract

Deliver the seven owner-approved review requirements in one implementation
bundle. Keep FastAPI, Jinja, HTMX and the analytics boundary. Numerical reports
remain in #104. Do not commit, stage, push, submit a PR, merge, deploy, change
workflows, or access household data. Record red/green evidence as local artifacts
instead of commits because the handoff explicitly withholds commit authority.

The user confirmed these public seams: HTTP login/session requests with real
credential rotation; browser navigation, failure ordering and keyboard interaction;
the public throttle interface; real CLI demo/serve with isolated synthetic data.
Use deferred red-green, one failing behavior followed by its implementation.

## Architecture decisions

- Read one immutable credential snapshot per authorization attempt. Verify the
  submitted passphrase or cookie and issue any renewed cookie using that exact
  snapshot. No second credential-file read can supply a replacement signing key.
  An overlapping old authorization may finish, but its cookie must fail on the
  next request after rotation. Preserve atomic credential-file replacement.
- Canonicalize the initial resolved page before HTMX history captures it. Use a
  fully pinned URL containing publication, reference date, month and selected
  accounts. An omitted account on a pinned URL means empty selection. `/` remains
  the explicit fresh-entry action. Prefer server redirect if compatible with the
  existing HTTP contract; otherwise replace the current history entry before
  interaction. Never resolve the publication twice across that transition.
- Apply canonical URLs to empty report responses as well. Browser back, forward
  and reload must preserve the complete selection, including no accounts.
- Track request identity for report loading, success and failure. Only the active
  request can update the report state. Failures visibly mark the report unavailable
  or stale, announce the problem and offer retry using current controls. Handle
  network and HTTP failure, without allowing aborted/superseded requests to erase
  newer successful content.
- Store a bounded lock duration, doubling only until 900 seconds and resetting
  after successful login. Do not compute an unbounded exponent and then cap it.
- Add a copy-pasteable isolated synthetic development demo entry point that
  exercises actual `budget serve`. Never read or alter existing profiles. Tests
  use test profiles; manual demo uses a separate development profile. Document
  login, screen expectations, shutdown, cleanup and #104. Refuse unsafe reuse
  of an existing target and avoid accidental exposure beyond loopback.
- Use a small local CSS foundation with shared Jinja layout and deliberate visual
  tokens; no new CSS framework or external CDN required. The NemShopper reference
  is in `origin/archive/web-app` of its local checkout (current main has no web UI).
  Study its base/index templates, app.css and fake-data README startup. Borrow
  structure and quality, not a dependency on Pico. Deliver desktop/phone layout,
  focus indicators, semantic labels and clear loading/empty/error states.

## Ordered slices and acceptance

1. Rotation during session renewal cannot mint a replacement-key cookie.
2. Rotation during login cannot mint a replacement-key cookie.
3. Repeated lockouts stay capped beyond the 43rd cycle; success resets duration.
4. Initial history is pinned: publication 2, selection change, publication 3,
   Back restores publication 2 in an actual browser.
5. Empty account selection survives reload and Back/Forward in the browser.
6. Active request failure has visible accessible feedback and retry.
7. Superseded failure cannot overwrite a newer successful report.
8. Synthetic isolated demo starts through the real CLI, with useful documentation.
9. Shared responsive shell and keyboard browser evidence. Styling-only work may
   use visual verification rather than artificial red tests.

Flash owns scoped discovery, implementation, tests, debugging and routine browser
QA across dashboard, related CLI/demo files, tests, README and necessary dependency
declarations. No unrelated refactors or weakened quality configuration. Record
commands and red failures, green results, screenshots and browser assertions in
`docs/agent-work/pr310-review-fixes/IMPLEMENTATION.md` and local evidence files.

Run focused tests for each slice, then full `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run ty check`, and `uv run complexipy`.
Use a temporary writable UV_CACHE_DIR if the default cache is denied.

## Review and completion

Astra reviews the actual baseline diff for specification and security/quality.
The deferred red-green closing review uses one independent read-only reviewer.
Batch corrections to the existing Flash writer, then verify affected behavior.
No commit or push is authorized. GitHub stack publication remains pending that
authorization; local stack is already configured.

Routing doctor: static-ready; root GPT-6 Astra, worker
`deepseek/deepseek-v4.1-flash`, provider DeepSeek API. Runtime provider metadata
must be inspected when available; static readiness is not runtime verification.

## Acceptance

Accepted by Astra after baseline-diff review, independent deferred review and
the footer correction. Final suite: 821 passed, 1 expected failure, 412 subtests
passed; Ruff lint/format, ty, complexipy and diff checks passed. Root separately
verified 81 authentication and document tests and inspected desktop/phone images.
All implementation remains uncommitted as requested. See IMPLEMENTATION.md for
the slice log, review disposition and browser evidence limitations.

The native Flash role executed the bundle. Runtime provider request metadata was
not available to the root; provider routing remains statically verified only.
