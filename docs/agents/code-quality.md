# Code Quality Gate

All Python code in this repository must pass four checks. CI runs them in
`.github/workflows/quality.yml` and blocks the merge when any one fails, so
run them locally before every commit that touches Python.

| Check | Tool | Local command |
| --- | --- | --- |
| Lint | ruff, every rule enabled | `uv run ruff check .` |
| Format | ruff formatter | `uv run ruff format --check .` |
| Types | ty, warnings promoted to errors | `uv run ty check` |
| Cognitive complexity ≤ 15 per function | complexipy (SonarQube rule `python:S3776`) | `uv run complexipy` |
| Quality gate | SonarQube Cloud | CI only |

Run them all at once:

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run complexipy
```

Configuration lives in `pyproject.toml` (ruff, ty, complexipy) and
`sonar-project.properties` (SonarQube). Dev tools are pinned in `uv.lock`.

## Rules for agents

- Write code that passes the gate; do not satisfy it by weakening it. Never
  edit the tool configuration, raise a threshold, add a rule to an ignore
  list, or add a suppression (`# noqa`, `# type: ignore`, `# ty: ignore`,
  `# complexipy: ignore`, `# NOSONAR`) without the owner's explicit approval
  in the task. When approved, the suppression names the exact rule and a
  comment says why.
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
- SonarQube cannot run locally without a token. If its CI job reports new
  issues, fix them the same way as local findings and push again.
