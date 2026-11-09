# Copyright 2026 Therkel
"""Tests that read the docs folder or the README carry the `docs` marker.

CI runs only `pytest -m docs` on a pull request that changes nothing but
documentation, so a test that reads a document must be selected by that
marker without anyone remembering to add it by hand.
"""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

CONFTEST = Path(__file__).resolve().parent / "conftest.py"

DOCS_READING_MODULES = {
    "test_slash_path": 'PAGE = "docs/architecture/x.md"\n',
    "test_path_parts": 'PAGE = Path(__file__).parent / "docs" / "x.md"\n',
    "test_readme": 'README = Path(__file__).parent / "README.md"\n',
}
OTHER_MODULE = {"test_plain": 'NAME = "documents"\n'}


def _module(source: str) -> str:
    return f"from pathlib import Path\n{source}\ndef test_it():\n    pass\n"


def test_only_docs_reading_modules_get_the_docs_marker(
    pytester: pytest.Pytester,
) -> None:
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyprojecttoml(
        '[tool.pytest.ini_options]\nmarkers = ["docs: reads docs/ or README.md"]\n'
    )
    modules = DOCS_READING_MODULES | OTHER_MODULE
    pytester.makepyfile(**{name: _module(src) for name, src in modules.items()})

    result = pytester.runpytest("-m", "docs", "--collect-only", "-q")

    selected = {line.split("::")[0] for line in result.outlines if "::" in line}
    assert selected == {f"{name}.py" for name in DOCS_READING_MODULES}
