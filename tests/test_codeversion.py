# Copyright 2026 Therkel
"""The production code guard must prove the *installed* package is committed.

A package installed inside a directory the enclosing repository ignores, such
as `.venv/Lib/site-packages/budget`, is invisible to `git status` run in that
repository: the repository reports itself clean, so a guard that only asks the
enclosing repository accepts untracked code. This test builds a real, purely
synthetic Git checkout with its own agent identity, and points the import
system's file metadata at a synthetic package inside it. Nothing real is read.
"""

import os
import shutil
import subprocess
import unittest
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

import budget
from budget.codeversion import UncommittedCodeError, require_committed_code
from budget.profiles import Profile

# A Git call that does not answer in this long fails the fixture, not the suite.
GIT_TIMEOUT_SECONDS = 30


def _git_executable() -> str:
    """Return Git's absolute path, or skip where Git is not installed."""
    found = shutil.which("git")
    if found is None:
        pytest.skip("git is not installed")
    return str(Path(found).resolve())


def _git_environment(home: Path) -> dict[str, str]:
    """A minimal Git environment: no operator configuration or identity.

    The path holds only the discovered Git directory, so the guard's own
    `shutil.which` and `subprocess.run` find that executable and nothing else.
    """
    environment = {
        "PATH": str(Path(_git_executable()).parent),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(home / "gitconfig"),
        "GIT_TERMINAL_PROMPT": "0",
    }
    # Platform plumbing only: the interpreter's temporary folders, the Windows
    # system root Git needs to start, and the executable suffixes `which` uses.
    for name in ("SYSTEMROOT", "TEMP", "TMP", "PATHEXT"):
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    return environment


def _run_git(checkout: Path, environment: Mapping[str, str], *arguments: str) -> str:
    """Run one Git command as the synthetic agent, and return its stdout."""
    completed = subprocess.run(
        [
            _git_executable(),
            "-c",
            "user.name=Synthetic Agent",
            "-c",
            "user.email=agent@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            *arguments,
        ],
        cwd=checkout,
        env=dict(environment),
        check=True,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return completed.stdout


def _production_profile(folder: Path) -> Profile:
    """A synthetic production profile; the guard reads no path from it."""
    return Profile(
        name="production",
        stores=folder / "stores",
        inputs=folder / "inputs",
        inbox=folder / "inbox",
        exports=folder / "exports",
    )


def _synthetic_package(folder: Path) -> Path:
    """One synthetic `budget` package folder, and its `__init__.py`."""
    folder.mkdir(parents=True, exist_ok=True)
    module = folder / "__init__.py"
    module.write_text("# synthetic\n", encoding="utf-8")
    return module


class InstalledCheckoutTests(unittest.TestCase):
    def test_an_ignored_installed_package_is_not_committed_code(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            checkout.mkdir()
            environment = _git_environment(root / "home")
            _run_git(checkout, environment, "init")
            (checkout / ".gitignore").write_text(".venv/\n", encoding="utf-8")
            tracked = _synthetic_package(checkout / "src" / "budget")
            installed = _synthetic_package(
                checkout / ".venv" / "Lib" / "site-packages" / "budget"
            )
            _run_git(checkout, environment, "add", "--all")
            _run_git(
                checkout,
                environment,
                "commit",
                "--message",
                "Synthetic: one tracked package and one ignored copy",
                "--message",
                "Co-Authored-By: Codex DeepSeek V4.1 Flash <noreply@openai.com>",
            )
            profile = _production_profile(root)

            # The repository is clean, and the ignored copy is invisible to it.
            assert (
                _run_git(
                    checkout,
                    environment,
                    "status",
                    "--porcelain",
                    "--untracked-files=normal",
                )
                == ""
            )

            # The guard's own Git call inherits this environment, so it reads
            # no operator configuration either.
            with mock.patch.dict(os.environ, environment, clear=True):
                # The tracked source is committed code, so the guard accepts it.
                with mock.patch.object(budget, "__file__", str(tracked)):
                    require_committed_code(profile)

                # The ignored installed copy is not: a clean repository that
                # merely encloses it must not pass for committed code.
                with (
                    mock.patch.object(budget, "__file__", str(installed)),
                    pytest.raises(UncommittedCodeError),
                ):
                    require_committed_code(profile)


if __name__ == "__main__":
    unittest.main()
