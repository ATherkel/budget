# Copyright 2026 Therkel
"""Synthetic profile files for CLI tests, written into a temporary folder.

Test profiles are never files (ADR-015), so these files say
`profile = "development"` and keep their folders inside the test's folder.
"""

from pathlib import Path

from budget.profiles import Profile


def write_profile(
    folder: Path,
    *,
    name: str = "development",
    stores: Path | None = None,
) -> Path:
    """Write a synthetic profile file whose folders stay inside `folder`."""
    stores = folder / "stores" if stores is None else stores
    path = folder / f"{name}.toml"
    path.write_text(
        f'format = 1\nprofile = "{name}"\n\n[paths]\n'
        f"stores = '{stores}'\ninputs = '{folder / 'inputs'}'\n"
        f"inbox = '{folder / 'inbox'}'\nexports = '{folder / 'exports'}'\n",
        encoding="utf-8",
    )
    return path


def development_profile(folder: Path) -> Profile:
    """The development profile `write_profile` describes inside `folder`."""
    return Profile(
        name="development",
        stores=folder / "stores",
        inputs=folder / "inputs",
        inbox=folder / "inbox",
        exports=folder / "exports",
    )
