---
type: agents
---
# Code Quality Gate

All Python code and templates in this repository must pass these checks. CI
runs them in `.github/workflows/quality.yml` and `.github/workflows/pytest.yml`;
run them locally before every commit that touches Python or templates. CSS has
an advisory overlap report described below.

| Check | Tool | Local command |
| --- | --- | --- |
| Lint | ruff, every rule enabled | `uv run ruff check .` |
| Format | ruff formatter | `uv run ruff format --check .` |
| Types | ty, warnings promoted to errors | `uv run ty check` |
| Cognitive complexity ≤ 15 per function | complexipy (SonarQube rule `python:S3776`) | `uv run complexipy` |
| Templates, lines ≤ 120 characters | djlint, lint only | `uv run djlint src --lint` |

Run them all at once:

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run complexipy && uv run djlint src --lint
```

Configuration lives in `pyproject.toml`; djlint's line rule lives in
`.djlint_rules.yaml`, because its own `max_line_length` only steers the
formatter. djlint skips a line that holds a comment, so
`tests/test_template_lint.py` also checks every template line's length.

## CSS Declaration Overlap Advisory

`uv run python -m tests.css_duplicates` scans the dashboard stylesheet root
recursively by default. Optional path arguments inspect specific stylesheets.
The threshold is the `SHARED_LIMIT` value in
[`tests/css_duplicates.py`](../../tests/css_duplicates.py); that setting is the
single source of truth.

The report names both paths, lines, selectors and grouping contexts, plus the
declarations the rules share. Overlap alone always exits successfully. Reuse or
keeping separate styles is a review judgment; the report never recommends a
specific selector. Ordinary `uv run pytest` prints the same advisory through
its terminal reporting, and `.pre-commit-config.yaml` runs the command verbosely
when relevant files change.

Read failures, tokenizer/parser errors, and unsupported syntax are explicit
diagnostics and make the command or pytest session fail. Dev tools are pinned
in `uv.lock`; install the hooks with `uvx pre-commit install`.

## Rules for agents

- Write code that passes the gate; do not satisfy it by weakening it. Never
  edit the tool configuration, raise a threshold, add a rule to an ignore
  list, or add a suppression (`# noqa`, `# type: ignore`, `# ty: ignore`,
  `# complexipy: ignore`, `{# djlint:off #}`) without the owner's explicit
  approval in the task. When approved, the suppression names the exact rule and a
  comment says why.
- Treat CSS declaration overlaps as review leads, not check failures. Do not
  suppress read, parse, or unsupported-syntax diagnostics. Review responsibility
  is in [Pull Request Reviews](pr-review.md#css-declaration-overlap-advisory).
- Treat a complexity failure as a design signal. Split the function by
  responsibility, extract guard clauses, or replace branching with data
  (lookup tables, polymorphism); do not just move nesting into a helper that
  is equally hard to read.
- Fully annotate public functions, methods and module-level values. Prefer
  precise types over `Any`.
- `ruff check --fix` and `ruff format` may be applied freely; review the
  diff, because unsafe fixes are not applied automatically.
- In the TDD workflow (`docs/agents/tdd.md`) the gate must pass at the end of
  each green phase and after the review/refactor stage. A red-phase test may
  fail its assertion, but it must still pass lint, format and type checks.
