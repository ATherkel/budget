# Copyright 2026 Therkel
"""Synthetic profile files for CLI tests, written into a temporary folder.

Test profiles are never files (ADR-015), so these files say
`profile = "development"` and keep their stores inside the test's folder.
"""

from pathlib import Path


def write_profile(
    folder: Path,
    *,
    name: str = "development",
    stores: Path | None = None,
) -> Path:
    """Write a synthetic profile file whose stores stay inside `folder`."""
    stores = folder / "stores" if stores is None else stores
    path = folder / f"{name}.toml"
    path.write_text(
        f"format = 1\nprofile = \"{name}\"\n\n[paths]\nstores = '{stores}'\n",
        encoding="utf-8",
    )
    return path
