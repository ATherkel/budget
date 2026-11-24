# Copyright 2026 Therkel
"""Compare a page's HTML with the copy pinned in `snapshots/`.

A refactor of the dashboard must leave every page's HTML as it was, so each
page is compared with its pinned copy character for character. A difference
fails with a diff of the two. To pin a page on purpose, after reviewing that
diff, delete its file and rerun with `BUDGET_PIN_SNAPSHOTS=1` set: only then is
a missing file written, and the test still fails so the new copy is reviewed.
"""

import difflib
import os
import re
from pathlib import Path

import pytest

SNAPSHOTS = Path(__file__).parent / "snapshots"

# A static file's address carries its content digest. Masked, so editing the
# CSS or script leaves the pages that link to it unchanged.
_DIGEST = re.compile(r"(/static/[^\"?]+)\?v=[0-9a-f]+")


def _masked(html: str) -> str:
    return _DIGEST.sub(r"\1?v=<digest>", html)


def assert_matches_snapshot(name: str, html: str) -> None:
    """Fail unless `html` is the page pinned as `name`, showing any difference."""
    pinned = SNAPSHOTS / f"{name}.html"
    page = _masked(html)
    if not pinned.exists():
        if os.environ.get("BUDGET_PIN_SNAPSHOTS") != "1":
            pytest.fail(
                f"no pinned copy of {pinned.name}; see tests/dashboard/snapshot.py"
            )
        pinned.write_text(page, encoding="utf-8", newline="\n")
        pytest.fail(f"pinned {pinned.name} for the first time; review it and rerun")
    expected = pinned.read_text(encoding="utf-8")
    if page != expected:
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            page.splitlines(keepends=True),
            fromfile=f"pinned {pinned.name}",
            tofile="rendered now",
        )
        pytest.fail(
            f"the HTML differs from {pinned.name}. A refactor must not change it;"
            " re-pin only an intended change, after reviewing this diff:\n"
            + "".join(diff),
            pytrace=False,
        )
