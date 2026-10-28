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
  consumed currency projection;
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
  decision-log prefixes, supported provenance contracts, and currencies for
  exactly the consumed run accounts, including runs later voided;
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

Closing review requested a sensitivity check rather than accepting the anomaly.
An isolated detached worktree at `686c229` added only
`from budget.silver.identity import IDENTITY_VERSION`, then ran:

```text
python -m pytest tests/cli/test_rebuild_gold.py::FirstPublicationTests::test_the_gold_recipe_copies_the_exact_silver_provenance -q
```

It then failed on the intended assertion:

```text
AssertionError: assert None == '1'
  recipe.silver_fingerprint_scheme was None; provenance.fingerprint_scheme was '1'
```

The scratch worktree was removed. `a88572c` also strengthens the current CLI
fixture with a nonempty effective decision, nonempty audit prefix, and a known
Silver producer distinct from Gold's current producer.

## Closing correction pass

The root's closing review produced six required findings. All are resolved:

| Finding | Resolution | Evidence |
| --- | --- | --- |
| Silver decision-log audit position and prefix incorrectly defeated recipe equality | Kept both fields durable and excluded both audit-only values from `Recipe` equality. The full Gold-only -> publish -> unchanged Silver rebuild -> Gold rebuild sequence returns the original publication and pointer history. | `6bb47bb` red, `ef36133` green |
| Prefix hashes split on every byte line boundary while parsing is LF-only | Replaced `bytes.splitlines()` with incremental SHA-256 updates at exact LF delimiters. A carriage-return-prefixed valid entry now has its full exact hash at position 1 and publishes. | `5c2d3a8` red, `0bd9ff5` green |
| Non-`ENOENT` decision-log read errors escaped unsanitized | Converted other `OSError`s to a path-independent `ConfigurationError`; CLI import and rebuild refuse before writes and do not leak exception content. | `e7b2db4` red, `ef769ee` green |
| Gold did not validate a future store's fingerprint scheme or identity contract | Gold refuses unsupported schemes and identity versions before writes with actionable Silver rebuild guidance; a direct SQLite future-store fixture keeps the pointer unchanged. | `a2dbe44` red, `dd50d0a` green |
| Currency freshness omitted accounts whose only run was voided | Silver provenance now stores consumed run IDs, payload hashes and account IDs; its currency projection is exactly those run accounts, including later-voided inputs. The full storage currency snapshot remains separate. Changed/removed voided-account currencies refuse; an added empty account remains valid. | `494d90a` red, `20f65d2` green |
| Historical red `686c229` did not prove its intended sensitivity | Re-ran it in an isolated historical snapshot with only the missing import repaired; it reached the intended `None == '1'` assertion. The current test was strengthened with nondefault Silver/Gold producer identities and nonempty decisions/prefix. | post-hoc evidence above; `a88572c` |

Additional closing coverage:

| Commit | Coverage |
| --- | --- |
| `74eb31d` | CLI effective Silver retraction: stale Gold refuses, rebuilt Silver publishes |
| `aac6267` | CLI effective Silver supersession: stale Gold refuses and the typed replacement persists |
| `76b6f69` | Physical decision-log truncation refuses with the pointer unchanged |
| `25e4a2a` | Populated Silver schema v2 migrates to v3, clears untrusted derived rows, rebuilds via CLI and publishes |
| `23bce33` | Every public Silver field and currency variation changes the fingerprint |
| `a88572c` | Gold recipe copy uses nondefault decisions, prefix and distinct stage producer |
| `301f44b` | ADR, glossary, Silver, publications and operations wording match the corrected contract |

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

The final closing-correction integration run produced:

```text
uv run pytest -q
943 passed, 1 xfailed, 420 subtests passed in 127.67s
```

The final closing-correction quality gate produced:

```text
uv run ruff check .                 # All checks passed
uv run ruff format --check .        # 255 files already formatted
uv run ty check                     # All checks passed
uv run complexipy                   # All functions are within the allowed complexity
uv run pytest tests/test_docs_frontmatter.py -q
66 passed
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
  are persisted in `f2e7577` and compared in `202bba6`; CLI retraction and
  supersession are covered by `74eb31d` and `aac6267`.
- **Gold-only decision:** the Gold prefix/position remains in the recipe, while
  only effective Silver state requires a Silver rebuild.
- **Prefix corruption:** replacement in `7579c31`/`b4e7b12`; physical truncation
  and exact CR/LF hashing in `76b6f69` and `5c2d3a8`/`0bd9ff5`.
- **Currency changes:** `7174e9c`/`08c7298`; voided-only consumed runs in
  `494d90a`/`20f65d2`; empty additions in `87335de`.
- **Unknown versus valid empty Silver:** explicit completion in `f2e7577`,
  unknown refusal in `e405a71`, valid empty behavior in the review phase tests.
- **Metadata/result atomicity and read snapshots:** `3d6189b`.
- **Import and rebuild propagation:** `ab13986`, `1e8a3f9`, and `b54c4a1`.
- **Immutable recipe and changed same-run result:** `2729364` and `f3454ec`.
- **Legacy recipe readability:** `8f4a579`; populated v2 migration recovery in
  `25e4a2a`.
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
- `301f44b` corrects the closing-review distinctions between immutable run
  references, full storage currencies and the exact consumed currency
  projection.

## Remaining limitations

- Bronze parser provenance is explicitly `unknown`. Parser capture and
  migration recovery remain #326 work.
- Historical Silver snapshots and cross-version replay are not implemented.
- Development-only Gold code change/no-op behavior remains #342 work.
- The intermediate red `686c229` remains in history because this phase was
  instructed not to rewrite it. Its post-hoc sensitivity check now proves the
  intended assertion, but its original recorded failure remains `NameError`.
- The existing direct `rebuild_silver` test remains supplementary evidence only;
  the accepted CLI seams are covered by the rebuild, import and migration tests
  above.
