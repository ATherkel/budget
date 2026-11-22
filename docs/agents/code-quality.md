---
type: agents
---
# Code Quality Gate

All Python code, templates and CSS in this repository must pass these checks.
CI runs them in `.github/workflows/quality.yml`, and the duplicate CSS check in
`.github/workflows/pytest.yml`, and blocks the merge when any one fails, so run
them locally before every commit that touches Python, templates or CSS.

| Check | Tool | Local command |
| --- | --- | --- |
| Lint | ruff, every rule enabled | `uv run ruff check .` |
| Format | ruff formatter | `uv run ruff format --check .` |
| Types | ty, warnings promoted to errors | `uv run ty check` |
| Cognitive complexity ≤ 15 per function | complexipy (SonarQube rule `python:S3776`) | `uv run complexipy` |
| Templates, lines ≤ 120 characters | djlint, lint only | `uv run djlint src --lint` |
| No CSS rule shares 3 or more declarations with another | `tests/css_duplicates.py` | `uv run pytest tests/test_css_duplicates.py` |

Run them all at once:

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run complexipy && uv run djlint src --lint \
  && uv run pytest tests/test_css_duplicates.py
```

Configuration lives in `pyproject.toml`; djlint's line rule lives in
`.djlint_rules.yaml`, because its own `max_line_length` only steers the
formatter. djlint skips a line that holds a comment, so
`tests/test_template_lint.py` also checks every template line's length.
The duplicate CSS check names the earlier rule to reuse. It reads the
stylesheets `base.html` links, in link order, so "earlier" can mean an earlier
file, and it fails on a stylesheet in `static/` that `base.html` doesn't link. Approved duplicates sit
in `css-duplicates-allowlist.txt`, one `rule | earlier rule` pair per line. An
entry that no longer matches fails the check, so a stale entry cannot linger.
Dev tools are pinned in `uv.lock`. `.pre-commit-config.yaml` runs djlint and
the duplicate CSS check on commit once installed with `uvx pre-commit install`.

## Rules for agents

- Write code that passes the gate; do not satisfy it by weakening it. Never
  edit the tool configuration, raise a threshold, add a rule to an ignore
  list, or add a suppression (`# noqa`, `# type: ignore`, `# ty: ignore`,
  `# complexipy: ignore`, `{# djlint:off #}`) without the owner's explicit
  approval in the task. When approved, the suppression names the exact rule and a
  comment says why. A new line in `css-duplicates-allowlist.txt` counts as a
  suppression: reuse the rule the check names instead.
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
