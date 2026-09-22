# Budget

A Python-first, self-hostable household budget platform. It is designed around
an immutable Bronze → Silver → Gold data pipeline so reports remain independent
of bank and import format.

Start with the [documentation map](docs/README.md) and the
[delivery roadmap](docs/03-roadmap.md).

## Install and test

`uv` manages the environment and the standard library's `unittest` runs the
tests. The runtime has no third-party dependencies, so there is nothing else to
install.

```powershell
uv sync
uv run python -m unittest discover -v -s tests -p 'test_*.py' -t .
```

`uv sync` creates `.venv/`, installs the `budget` distribution from `src/budget`
in editable mode, and is the whole setup step. `uv build` writes a wheel and an
sdist into the ignored `dist/` directory; installing that wheel is what proves
the package works outside the checkout, so nothing relies on `PYTHONPATH` or a
hand-edited `sys.path`. Python 3.12 or newer is required.

In VS Code, select `.venv/Scripts/python.exe` with **Python: Select
Interpreter** if the workspace was already using system Python.
`python.defaultInterpreterPath` only supplies the default for a window that has
no interpreter selected yet, so it does not replace a selection you already
made.

## Layout

| Path | Contents |
| --- | --- |
| `src/budget/` | the application package |
| `src/budget/bronze/` | Bronze: raw payloads, import runs, source records |
| `src/budget/bronze/parsers/` | the parser contract, the registry, and one module per source format |
| `tests/` | `unittest` suites, discovered from the repository root |
| `docs/` | contracts, decisions, and domain documents |

## Adding a source format

Parsing is separated by source, representation, and version:
[docs/developers/source-parsers.md](docs/developers/source-parsers.md) describes
the contract, how to register a format, and what is deliberately not solved yet.
