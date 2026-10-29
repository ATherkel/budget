# Copyright 2026 Therkel
"""Forcing new folder entries to disk, for writes that must survive a crash."""

import os
import sys
from pathlib import Path


def sync_folder(folder: Path) -> None:
    """Force a folder's new entries to disk, where the platform allows it.

    Windows cannot open a folder to fsync it; NTFS journals a rename itself.
    """
    if sys.platform == "win32":
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
