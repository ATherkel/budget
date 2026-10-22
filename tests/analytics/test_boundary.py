# Copyright 2026 Therkel
"""Analytics reads Gold only through its seam (`analytics-layer.md`, #179).

No analytics module may import Bronze, Silver, a parser or
`GoldLineageRepository`. The test allows rather than forbids, so a new
pipeline module is outside the boundary until someone decides otherwise.
"""

import ast
import sys
from pathlib import Path

import budget.analytics

ANALYTICS = Path(budget.analytics.__file__).parent


def _imports(module: Path) -> list[tuple[str, str | None]]:
    """Return each `(module, name)` a file imports; `name` is None for `import x`."""
    imported: list[tuple[str, str | None]] = []
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.extend((node.module or "", alias.name) for alias in node.names)
    return imported


def _allowed(module: str) -> bool:
    top = module.partition(".")[0]
    return (
        module == "budget.gold"
        or module.startswith("budget.analytics")
        or (top != "budget" and top in sys.stdlib_module_names)
    )


def test_analytics_imports_only_the_standard_library_and_the_gold_seam() -> None:
    outside = {
        (path.name, module, name)
        for path in ANALYTICS.rglob("*.py")
        for module, name in _imports(path)
        if not _allowed(module) or name == "GoldLineageRepository"
    }

    assert outside == set()
