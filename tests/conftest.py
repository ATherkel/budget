# Copyright 2026 Therkel
"""Shared pytest hooks for the whole test suite."""

import re
from pathlib import Path

import pytest

from tests.css_duplicates import (
    discover_stylesheets,
    format_diagnostics,
    format_report,
    report_overlaps,
)

# A module that names the docs folder or the README reads documentation, so a
# docs-only pull request must still run it: CI selects these with `-m docs`.
DOCS_REFERENCE = re.compile(r"""docs/|["']docs["']|README\.md""")


def _reads_docs(module: Path, cache: dict[Path, bool]) -> bool:
    if module not in cache:
        cache[module] = bool(DOCS_REFERENCE.search(module.read_text(encoding="utf-8")))
    return cache[module]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test whose module refers to the docs folder or README."""
    cache: dict[Path, bool] = {}
    for item in items:
        if _reads_docs(item.path, cache):
            item.add_marker(pytest.mark.docs)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Show the CSS overlap advisory and fail the session on analysis errors."""
    report = report_overlaps(discover_stylesheets())
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    reporter.write_sep("=", "CSS declaration overlap advisory")
    reporter.write_line(format_report(report).rstrip())
    if report.diagnostics:
        reporter.write_line(format_diagnostics(report).rstrip())
        if exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
