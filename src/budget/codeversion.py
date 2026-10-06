# Copyright 2026 Therkel
"""The code a production build runs: a committed, clean checkout.

Production builds run only from committed code (operations.md, *Development
diverges from a stage*): a development store may build from uncommitted code
and records no code version, a production one may not. The check asks Git
about the checkout the installed package belongs to, never the caller's
working directory, with a finite timeout; anything that leaves the state
unverifiable - a missing Git, a failing command, a timeout - refuses the build
rather than guessing. Git's own output is never repeated to the operator.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Final

import budget
from budget.profiles import PRODUCTION_PROFILE_NAME, Profile

# A Git call that does not answer in this long is not verifiable.
GIT_TIMEOUT_SECONDS: Final = 10
_UNCOMMITTED: Final = "this checkout has uncommitted changes"
_UNVERIFIABLE: Final = "this checkout's state cannot be checked"


class UncommittedCodeError(RuntimeError):
    """A production build cannot prove that the code it runs is committed."""

    def __init__(self, reason: str) -> None:
        """Name the problem, never repeating Git's own output."""
        super().__init__(
            f"production builds run only from committed code, and {reason}; "
            "nothing was written"
        )


def require_committed_code(profile: Profile) -> None:
    """Refuse a production build whose code cannot be proved committed.

    Development and test profiles make no reproducibility promise, so they are
    not checked. The checkout is the one the installed package belongs to, so
    the answer does not depend on the caller's working directory.
    """
    if profile.name != PRODUCTION_PROFILE_NAME:
        return
    completed = _status(_checkout())
    if completed is None or completed.returncode != 0:
        raise UncommittedCodeError(_UNVERIFIABLE)
    if completed.stdout.strip():
        raise UncommittedCodeError(_UNCOMMITTED)


def _checkout() -> Path:
    """Return the directory the installed `budget` package belongs to."""
    return Path(budget.__file__).resolve().parent.parent


def _status(checkout: Path) -> subprocess.CompletedProcess[str] | None:
    """Ask Git about the checkout, or return None when it cannot be asked."""
    found = shutil.which("git")
    if found is None:
        return None
    # `which` can answer with a relative PATH entry; the command needs one
    # absolute executable.
    git = str(Path(found).resolve())
    try:
        # The one suppression in this module: the command is a fixed literal
        # with no shell, and `git` is the absolute path `shutil.which` found.
        return subprocess.run(  # noqa: S603
            [git, "status", "--porcelain", "--untracked-files=normal"],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
