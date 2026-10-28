---
type: 323-silver-provenance
---
# Closing review findings and resolutions

Status: ready for root spot-check

Branch: `codex/323-review-fixes`

This note records the six required findings from the independent Astra closing
review and their correction evidence. The original design, research and slice
files are unchanged.

| Finding | Required behavior | Resolution | Evidence |
| --- | --- | --- | --- |
| 1 | Gold-only audit movement must not defeat recipe equality | `Recipe` retains the Silver audit position and prefix but excludes those audit-only values from equality. Full publish/rebuild/no-op pointer behavior is pinned. | `6bb47bb` red; `ef36133` green |
| 2 | Prefix hashes must use exact LF-delimited lines and incremental hashing | Removed `bytes.splitlines()`; CR-prefixed JSON remains valid while its position-1 hash equals the exact full-line hash. | `5c2d3a8` red; `0bd9ff5` green |
| 3 | Filesystem read errors other than `FileNotFoundError` must become sanitized configuration refusals | `read_decision_log` catches other `OSError`s, emits only the filename and error class/message, and CLI import/rebuild tests prove no writes or leaked private text. | `e7b2db4` red; `ef769ee` green |
| 4 | An older Gold consumer must reject newer Silver fingerprint or identity contracts before writing | Gold validates both contracts after reading the stored provenance and gives `budget rebuild --from silver` guidance. A future-store SQLite fixture proves the pointer remains unchanged. | `a2dbe44` red; `dd50d0a` green |
| 5 | Currency freshness must include accounts whose only runs a decision voided | Every consumed run records its account ID. Provenance stores the consumed currency projection separately from the full storage snapshot; Gold guards that exact projection. | `494d90a` red; `20f65d2` green |
| 6 | The invalid historical red must demonstrate its intended sensitivity | An isolated `686c229` snapshot added only the missing `IDENTITY_VERSION` import and failed the intended recipe-copy assertion; the current fixture now uses a nondefault decision, prefix and distinct stage producers. | post-hoc check in `provenance-report.md`; `a88572c` |

Coverage added under the approved public CLI seam:

- `74eb31d`: effective Silver retraction refuses stale Gold, then publishes
  after Silver rebuild.
- `aac6267`: effective Silver supersession refuses stale Gold, then publishes
  with the typed replacement retained.
- `76b6f69`: a physically truncated recorded prefix refuses with no pointer
  move.
- `25e4a2a`: populated Silver schema v2 migrates to v3, clears derived rows and
  recovers through CLI Silver rebuild and Gold publication.
- `23bce33`: every public Silver field and currency variation changes the
  versioned fingerprint.
- `a88572c`: the Gold recipe fixture uses nondefault decisions, audit context
  and a Silver producer distinct from Gold's producer.

Documentation:

- `301f44b` distinguishes the full storage currency snapshot from the consumed
  run-account projection, including later-voided runs.
- It also defines import-run recipe entries as immutable Bronze references to
  the run ID and payload hash rather than copied metadata.
- ADR-020, the glossary, Silver layering, publications and operations now agree
  on compatibility, freshness, recovery and historical limits.

Validation:

```text
uv run pytest -q
943 passed, 1 xfailed, 420 subtests passed in 127.67s

uv run ruff check .
All checks passed!

uv run ruff format --check .
255 files already formatted

uv run ty check
All checks passed!

uv run complexipy
All functions are within the allowed complexity.

uv run pytest tests/test_docs_frontmatter.py -q
66 passed
```

Remaining limitations:

- Bronze parser identity is explicitly `unknown`; capture, replay and migration
  stay in the later #326 boundary.
- The original `686c229` failure remains recorded as `NameError`; it was not
  rewritten. The isolated post-hoc run now proves the intended assertion.
- The existing direct `rebuild_silver` test is supplementary; the CLI behaviors
  above are the accepted proof.
