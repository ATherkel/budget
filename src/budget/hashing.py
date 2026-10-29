# Copyright 2026 Therkel
"""Hashing utilities for generating consistent identifiers."""

import hashlib
import json


def hash_parts(inputs: list[str | int]) -> str:
    """Hash inputs serialised as a compact JSON array with SHA-256.

    Args:
        inputs: A list of strings or integers to be hashed.

    Returns:
        The SHA-256 hash of the inputs as a hexadecimal string.

    """
    serialised = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialised.encode()).hexdigest()
