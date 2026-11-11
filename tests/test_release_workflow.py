# Copyright 2026 Therkel
"""The Release workflow's dry-run report names why a release would be refused (#492).

The report step is a shell script inside `release.yml`. These tests run that
script with bash, giving it the outcomes of the earlier steps as environment
variables, and read the job summary it writes.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"
)
REPORT_STEP = "Report what a release would create"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _step_script(step_name: str) -> str:
    """The `run:` script of the workflow step called `step_name`."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"      - name: {step_name}")
    run = next(i for i in range(start, len(lines)) if lines[i] == "        run: |")
    body: list[str] = []
    for line in lines[run + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body))


def _dry_run_summary(tmp_path: Path, **outcomes: str) -> str:
    """The summary the report step writes when the earlier steps ended as given."""
    summary = tmp_path / "summary.md"
    env = {
        **os.environ,
        "GITHUB_REF": "refs/heads/try/tag",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "owner/budget",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_STEP_SUMMARY": str(summary),
        "DRY_RUN": "false",
        "REF": "try/tag",
        "TAG": "v0.3.0",
        "STATE": "new",
        "VERSION_OUTCOME": "success",
        "INSTALL_OUTCOME": "success",
        "CHECK_OUTCOME": "success",
        **outcomes,
    }
    script = _step_script(REPORT_STEP)
    bash = shutil.which("bash") or "bash"
    subprocess.run([bash, "-e", "-c", script], env=env, check=True)
    return summary.read_text(encoding="utf-8")


def test_a_failed_install_is_named_rather_than_blamed_on_the_manifest_check(
    tmp_path: Path,
) -> None:
    # A failed `uv sync --locked` skips the manifest check. It writes no
    # manifest section, so the report must not point at one.
    summary = _dry_run_summary(
        tmp_path, INSTALL_OUTCOME="failure", CHECK_OUTCOME="skipped"
    )

    assert "1. The locked dependencies could not be installed" in summary
    assert "see above" not in summary


def test_a_failed_version_step_is_the_only_reason_given(tmp_path: Path) -> None:
    # The steps after it are skipped because of it, so they are not reasons.
    summary = _dry_run_summary(
        tmp_path,
        VERSION_OUTCOME="failure",
        INSTALL_OUTCOME="skipped",
        CHECK_OUTCOME="skipped",
    )

    assert "1. The tags or releases could not be read (see the log of that step)" in (
        summary
    )
    assert "2. " not in summary
