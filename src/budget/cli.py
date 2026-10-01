# Copyright 2026 Therkel
"""The `budget` command line."""

from collections.abc import Mapping, Sequence


def main(argv: Sequence[str], *, environ: Mapping[str, str]) -> int:
    """Run one command and return its exit status."""
    raise NotImplementedError
