# Copyright 2026 Therkel
"""Compare a page's HTML with the copy pinned in `snapshots/`.

A refactor of the dashboard must leave every page's HTML as it was, so each
page is compared with its pinned copy character for character. To pin a page
again, delete its file and rerun the test: a missing file is written, and the
test fails so the new copy is reviewed before it is trusted.
"""

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
    """Fail unless `html` is the page pinned as `name`."""
    pinned = SNAPSHOTS / f"{name}.html"
    page = _masked(html)
    if not pinned.exists():
        SNAPSHOTS.mkdir(exist_ok=True)
        pinned.write_text(page, encoding="utf-8", newline="\n")
        pytest.fail(f"pinned {pinned.name} for the first time; review it and rerun")
    assert page == pinned.read_text(encoding="utf-8"), (
        f"the HTML differs from {pinned.name}; delete it and rerun to pin it again"
    )
