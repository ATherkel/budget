# Copyright 2026 Therkel
"""The code a production build runs: a committed, clean checkout.

Production builds run only from committed code (operations.md, *Development
diverges from a stage*): a development store may build from uncommitted code
and records no code version, a production one may not. The check asks Git
about the checkout that holds the installed package, never the caller's working
directory: that checkout must track the package's own source, and it must have
no uncommitted changes. Every call has a finite timeout; anything that leaves
either answer unverifiable - a missing Git, a failing command, a timeout -
refuses the build rather than guessing. Git's own output is never repeated to
the operator.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Final

import budget
from budget.profiles import PRODUCTION_PROFILE_NAME, Profile

# A Git call that does not answer in this long is not verifiable.
GIT_TIMEOUT_SECONDS: Final = 10
_UNTRACKED_PACKAGE: Final = "the installed package is not tracked by its checkout"
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
    not checked. The package the running code was imported from must be tracked
    by the checkout that holds it - a package installed inside a folder that
    checkout ignores is not committed code, however clean that checkout looks -
    and the checkout itself must have no uncommitted changes.
    """
    if profile.name != PRODUCTION_PROFILE_NAME:
        return
    module = Path(budget.__file__).resolve()
    tracked = _git(module.parent, "ls-files", "--error-unmatch", "--", module.name)
    if tracked is None:
        raise UncommittedCodeError(_UNVERIFIABLE)
    if tracked.returncode != 0:
        raise UncommittedCodeError(_UNTRACKED_PACKAGE)
    status = _git(module.parent, "status", "--porcelain", "--untracked-files=normal")
    if status is None or status.returncode != 0:
        raise UncommittedCodeError(_UNVERIFIABLE)
    if status.stdout.strip():
        raise UncommittedCodeError(_UNCOMMITTED)


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str] | None:
    """Run one fixed Git command in `cwd`, or return None when it cannot run.

    Every command is chosen by this module's own callers and fixed, never built
    from input, and runs without a shell through the absolute executable
    `shutil.which` found.
    """
    found = shutil.which("git")
    if found is None:
        return None
    executable = str(Path(found).resolve())
    try:
        # The one suppression in this module.
        return subprocess.run(  # noqa: S603
            [executable, *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
