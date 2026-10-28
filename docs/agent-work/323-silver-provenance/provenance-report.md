---
type: 323-silver-provenance
---
# Stage-specific provenance implementation report

Status: ready for root review

Branch: `codex/323-review-fixes`

Accepted baseline: `5934ba355819b73b72c3d45cd3046a10687f3f89`

## Scope delivered

This phase implements the safe #323 A+B boundary:

- a versioned canonical fingerprint of every public Silver result field and its
  consumed currency snapshot;
- one Silver completion value committed atomically with the result, exact
  stored/repeated import runs, consumed currencies, effective Silver decisions,
  decision-log position and prefix hash, actual Silver producer code, and
  identity version;
- explicit unknown provenance for direct Silver replacements and an explicit
  unknown Bronze parser marker;
- Silver v3 migration that clears pre-provenance derived state;
- Silver rebuild and import integration that applies the validated decision log
  and records the exact context;
- Gold v5 recipe storage that immutably copies Silver provenance and remains
  readable for legacy recipes whose provenance is absent;
- Gold validation of changed effective Silver decisions, rewritten/truncated
  decision-log prefixes, and currencies for represented accounts;
- no-op protection based on the full Silver fingerprint, so changed Silver under
  unchanged import-run identifiers publishes new Gold;
- acceptance of Gold-only changes and an added empty account; and
- recovery after Silver commits and Gold publication fails.

Bronze parser capture, historical Silver replay, and cross-version replay remain
outside this phase.

## Red/green log

| Behaviour | Red | Green |
| --- | --- | --- |
| Complete Silver fingerprint | `00c2069` | `a9a0e92` |
| Atomic result, currency, decision and provenance persistence | `b320d08` | `f2e7577` |
| Public rebuild captures exact consumed context | `8b965ea` | `1e8a3f9` |
| CLI applies and records Silver decisions | `d13edd5` | `b54c4a1` |
| Gold recipe copies immutable Silver provenance | `686c229` | `45a8ed3` |
| Gold refuses unapplied effective Silver decisions | `7d4311d` | `202bba6` |
| Gold verifies the consumed decision-log prefix | `7579c31` | `b4e7b12` |
| Gold refuses changed consumed currencies | `7174e9c` | `08c7298` |

Observed red failures:

- `00c2069`: the focused fingerprint test received `''` instead of
  `6bd2f02b87c4cc09447b8479ca5b535e17fcd8a025ece2cc24e9db6f0a9b57ab`.
- `b320d08`: `read_build()` returned `{}` currencies and `None` provenance
  instead of the supplied known build.
- `8b965ea`: the rebuild returned unknown provenance instead of the exact
  consumed log, decision and producer fields.
- `d13edd5`: a valid nonempty Silver decision log exited 3 with the old blanket
  refusal instead of exiting 0 after applying the decision.
- `7d4311d`: an unapplied effective Silver decision exited 0 and published
  publication 2 instead of refusing with exit 4.
- `7579c31`: a replaced consumed decision-log prefix exited 0 and published
  instead of reporting a broken prefix.
- `7174e9c`: a changed consumed currency escaped as an unhandled
  `UnknownCurrencyError`; the test normalized that to an assertion failure
  because the application had no handled refusal yet.

Red-history anomaly:

`686c229` was committed during the interrupted provider turn before its
implementation. A post-hoc snapshot run reached `NameError` because the prior
CLI green had removed the now-unused `IDENTITY_VERSION` import while the parent
Gold path still named it; it did not fail on the intended recipe assertion.
`45a8ed3` implements and passes the behavior. No history was rewritten after
the interruption.

## Supporting commits

These behaviours emerged with earlier slices or are regression pins and therefore
passed on first execution:

| Commit | Coverage |
| --- | --- |
| `87335de` | Added empty account remains valid without a Silver rebuild |
| `8f4a579` | Legacy Gold recipes read absent Silver provenance explicitly |
| `f3454ec` | Changed Silver under unchanged runs publishes new Gold |
| `3d6189b` | Explicit unknown completion, metadata rollback, snapshot consistency |
| `6c3027e` | Silver commit followed by Gold failure and an unchanged retry |
| `33777bb` | Incidental order and decimal scale ignored; duplicates retained |
| `ab13986` | Import path captures complete, honest Silver provenance |
| `e405a71` | A direct completed Silver replacement with unknown provenance refuses Gold |
| `2729364` | A later Silver replacement never mutates an older Gold recipe |
| `04515f5` | Synthetic demo recipe carries complete synthetic provenance |
| `4b1a5d7` | Backup schema and production Git fixtures align with this phase |

## Validation and integration

The first full-suite integration run after implementation produced:

```text
17 failed, 913 passed, 1 xfailed, 416 subtests passed
```

Failures were confined to the expected schema-version fixture updates, the
synthetic demo recipe, and production Git fixtures that now also need a
`rev-parse HEAD` answer. No provenance behavior failed.

After those integration fixes and the documentation updates, the full suite
produced:

```text
932 passed, 1 xfailed, 416 subtests passed
```

Relevant focused suites also passed:

- Silver fingerprint, store, storage and rebuild tests;
- CLI rebuild decision-log tests;
- Gold recipe, rebuild, freshness, currency and review tests;
- import capture and production rebuild/import tests;
- backup and migration tests;
- documentation front-matter tests.

All code-quality checks passed before each implementation commit:

```text
uv run ruff check .
uv run ruff format --check .
uv run ty check src tests
uv run complexipy
```

The checkout's pre-existing `.pytest_cache` is unreadable from the normal
sandbox, so `ty check src tests` was used during implementation and passed. The
final exact `uv run ty check` also passed through the approved workspace
boundary. No type rule or configuration was changed.

## Acceptance coverage

- **Same-run changed Silver:** `f3454ec`; Gold publishes publication 2 when the
  Silver fingerprint changes despite identical run identifiers.
- **Equivalent order and decimal scale:** `33777bb`; canonical sorting and exact
  decimal normalization keep fingerprints equal.
- **Duplicates and complete field coverage:** `00c2069`/`a9a0e92` plus
  `33777bb`.
- **Effective decision add/remove/retract:** current effective typed decisions
  are persisted in `f2e7577` and compared in `202bba6`; supersession and
  retraction are resolved by the decision-log reader.
- **Gold-only decision:** the Gold prefix/position remains in the recipe, while
  only effective Silver state requires a Silver rebuild.
- **Prefix corruption:** `7579c31`/`b4e7b12`.
- **Currency changes:** `7174e9c`/`08c7298`; empty additions in `87335de`.
- **Unknown versus valid empty Silver:** explicit completion in `f2e7577`,
  unknown refusal in `e405a71`, valid empty behavior in the review phase tests.
- **Metadata/result atomicity and read snapshots:** `3d6189b`.
- **Import and rebuild propagation:** `ab13986`, `1e8a3f9`, and `b54c4a1`.
- **Immutable recipe and changed same-run result:** `2729364` and `f3454ec`.
- **Legacy recipe readability:** `8f4a579`.
- **Retry after Silver commit and Gold failure:** `6c3027e`.

## Documentation

- ADR-014 now points to ADR-020 for stage-specific producer identity.
- New ADR-020 records the accepted Silver/Gold provenance contract.
- `publications.md` defines Silver provenance, Gold recipe capture, freshness
  checks, and the limits of replay.
- `operations.md` describes production writes, refusals, migration recovery and
  operator guidance.
- `CONTEXT.md` defines Silver build provenance and the stage-aware Recipe.
- `silver-layer.md` documents the atomic `SilverBuild` and `SilverProvenance`
  value.

## Remaining limitations

- Bronze parser provenance is explicitly `unknown`. Parser capture and
  migration recovery remain #326 work.
- Historical Silver snapshots and cross-version replay are not implemented.
- Development-only Gold code change/no-op behavior remains #342 work.
- The broken intermediate red `686c229` is retained because this phase was
  instructed to preserve its red/green history; root closing review should judge
  that anomaly explicitly.
