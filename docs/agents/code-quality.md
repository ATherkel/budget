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
| Templates | djlint plus the repository line rule; authoritative settings are [`.djlint_rules.yaml`](../../.djlint_rules.yaml) and [`tests/test_template_lint.py`](../../tests/test_template_lint.py) | `uv run djlint src --lint`; `uv run pytest tests/test_template_lint.py` |
| No logic in dashboard templates | the template logic gate; the rule is [Templates Hold No Logic](../architecture/presentation-layer.md#templates-hold-no-logic) | `uv run pytest tests/test_template_logic.py -n0` |

Run them all at once:

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run complexipy && uv run djlint src --lint
```

Configuration lives in `pyproject.toml`. The template line rule lives in
[`.djlint_rules.yaml`](../../.djlint_rules.yaml) and is guarded by
[`tests/test_template_lint.py`](../../tests/test_template_lint.py); both are
authoritative. The CSS overlap check is advisory:
[CSS Declaration Overlap Advisory](#css-declaration-overlap-advisory). The
dashboard's structure rules are in [Presentation Agent Brief](ui-agent.md).

## Parallel Test Runs

`uv run pytest` runs the suite in parallel with pytest-xdist: the `addopts`
line in `pyproject.toml` starts one worker per core and keeps each test module
(or test class) on one worker. Add `-n0` to run serially, which `--pdb` needs and which starts
faster for a single file.

## CSS Declaration Overlap Advisory

`uv run python -m tests.css_duplicates` scans the dashboard stylesheet root
recursively by default. Optional path arguments inspect specific stylesheets.
The threshold is the `SHARED_LIMIT` value in
[`tests/css_duplicates.py`](../../tests/css_duplicates.py); that setting is the
single source of truth.

The report names both paths, lines, selectors and grouping contexts, plus the
declarations the rules share. Overlap alone always exits successfully, and the
report never recommends a specific selector. Ordinary `uv run pytest` prints the
same advisory through its terminal reporting, and `.pre-commit-config.yaml` runs
the command verbosely when relevant files change. In GitHub Actions the pytest
run also prints each finding as a warning annotation at the later rule, so
findings appear on the run and the PR's changed files. GitHub shows only the
first annotations of each kind per step, so the log stays the complete report.
Review responsibility is in
[Pull Request Reviews](pr-review.md#css-declaration-overlap-advisory).

Read failures, tokenizer/parser errors, unsupported syntax and a dashboard root
with no stylesheets are explicit diagnostics. They make the command exit
nonzero and fail `test_dashboard_css_analyses_without_errors` in pytest. Dev
tools are pinned in `uv.lock`; install the hooks with `uvx pre-commit install`.

## Rules for agents

- Write code that passes the gate; do not satisfy it by weakening it. Never
  edit the tool configuration, raise a threshold, add a rule to an ignore
  list, or add a suppression (`# noqa`, `# type: ignore`, `# ty: ignore`,
  `# complexipy: ignore`, `{# djlint:off #}`) without the owner's explicit
  approval in the task. When approved, the suppression names the exact rule and a
  comment says why.
- Do not suppress CSS read, parse, or unsupported-syntax diagnostics. Overlap
  reporting without diagnostics is advisory; its review responsibility is in
  [Pull Request Reviews](pr-review.md#css-declaration-overlap-advisory).
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
