---
type: 323-silver-provenance
---
# Review visibility implementation report

Status: ready for root review

Branch: `codex/323-review-fixes`

Baseline: `7122199b105e8f88a531dd69953fdb81e5cd5d4b`

## Scope and result

`budget review` now distinguishes Silver with no completed build from Silver
whose completed build legitimately contains no review items. The unavailable
state is the state left after the Silver v2 migration clears derived rows.
Instead of returning an empty queue with exit 0, review:

- prints an actionable diagnostic to stderr;
- directs the operator to `budget rebuild --from silver`;
- exits 4, the existing refused-environment status for a stage that is not
  built; and
- still prints review items retained in the current Gold publication.

A completed empty Silver build, represented through the public
`SilverStore.replace` interface with an account currency snapshot, continues to
exit 0 with no output.

This slice does not implement Silver provenance, fingerprints, or changes to
Gold recipes.

## Slice log

| Slice | Behaviour | Red commit | Green commit |
| --- | --- | --- | --- |
| 1 | Refuse to present an unbuilt or migration-cleared Silver as a complete empty queue, while accepting a built empty result | `38173b4` | `f415f9d` |
| 2 | Retain the current Gold publication's review items in the incomplete review output | `7eac225` | `591d7cb` |

The first red commit was amended before its green began so the unrelated
routine-log rotation test would create a genuinely built empty Silver fixture.
Its final SHA is `38173b4`.

## Red evidence

Slice 1 command:

```text
uv run pytest tests/cli/test_review_command.py -k distinguishes_unbuilt_silver -q
```

Exit status: 1.

```text
AssertionError: assert (0, '', '') == (
    4,
    '',
    'budget: Silver review is unavailable because Silver has not been built or '
    'was cleared by a migration; run `budget rebuild --from silver`; the review '
    'queue is incomplete\n',
)
At index 0 diff: 0 != 4
```

The assertion failed on the missing refusal, not on setup, import, or typing.

Slice 2 command:

```text
uv run pytest tests/cli/test_gold_review_command.py -k unbuilt_silver_does_not_hide -q
```

Exit status: 1.

```text
AssertionError: assert [] == [
    'f1e2d3c4...  rule-conflict  gold  publication 1  targets 89abcdef  '
    'rules r-mobilepay, r-netto',
    '  target 89abcdef  joint-current  2026-01-28  -842.50 DKK ...',
    '  settle  adjust rule priority or narrow a rule; otherwise classify a target ...',
]
Right contains 3 more items, first extra item: ...
```

The assertion showed that the unavailable-Silver path returned before reading
the retained Gold publication.

## Green and final verification

The focused tests passed after each green. The final relevant suite was:

```text
uv run pytest tests/cli/test_review_command.py tests/cli/test_gold_review_command.py tests/cli/test_silver_logging.py -q
```

Exit status: 0.

```text
16 passed, 6 subtests passed
```

The repository quality gate also passed before every commit:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check .` | 0 | `All checks passed!` |
| `uv run ruff format --check .` | 0 | `250 files already formatted` |
| `uv run ty check` | 0 | `All checks passed!` |
| `uv run complexipy` | 0 | All functions within the configured complexity limit |

The full repository pytest suite was not run for this focused slice.

## Changed paths

- `src/budget/reviewing.py`: expose whether Silver has a completed build, add
  the unavailable-review refusal, and retain Gold items on the incomplete path.
- `src/budget/cli.py`: print review output before refusing incomplete Silver,
  map the refusal to exit 4, and log only completed reviews.
- `tests/cli/test_review_command.py`: cover the unavailable versus built-empty
  distinction through the public CLI.
- `tests/cli/test_gold_review_command.py`: cover retained Gold visibility while
  Silver is unavailable.
- `tests/cli/test_silver_logging.py`: use a legitimately built empty Silver
  result in the routine-log rotation fixture.
- `docs/agent-work/323-silver-provenance/review-visibility-report.md`: this
  report.

## Risks and review focus

- The review test exercises the migrated store's unbuilt state directly. The
  existing Silver storage test separately verifies that the v1-to-v2 migration
  clears derived rows and leaves `SilverStore.is_built()` false.
- The incomplete path deliberately does not write a completed review routine
  log, because the review queue is incomplete.
- This branch remains limited to review visibility. Provenance freshness,
  fingerprints, and atomic Silver metadata are for later slices.
