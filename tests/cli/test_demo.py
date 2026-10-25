# Copyright 2026 Therkel
"""The synthetic development dashboard started by `budget demo`."""

import io
import os
import socket
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import httpx2
import pytest
from fastapi.testclient import TestClient

from budget.cli import main
from budget.dashboard import create_app
from budget.gold.store import GoldStore
from budget.profiles import load_profile_file


def _free_port() -> int:
    """Return one currently unused loopback TCP port."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = int(listener.getsockname()[1])
    listener.close()
    return port


def _wait_until_login(client: httpx2.Client) -> None:
    """Wait for the real CLI's HTTP server, bound to a short deadline."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if client.get("/login").status_code == 200:
                return
        except httpx2.TransportError:
            time.sleep(0.05)
    pytest.fail("the real demo CLI did not start its dashboard")


def test_demo_creates_a_development_profile_and_starts_the_dashboard(
    tmp_path: Path,
) -> None:
    target = tmp_path / "synthetic-dashboard"
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        redirect_stdout(stdout),
        redirect_stderr(stderr),
        mock.patch("budget.cli.uvicorn.run") as serve,
    ):
        status = main(
            ["demo", "--directory", str(target), "--port", "8877"],
            environ={},
        )

    assert status == 0, stderr.getvalue()
    profile_file = target / "profile.toml"
    profile = load_profile_file(profile_file)
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
    dashboard = TestClient(
        create_app(profile, clock=lambda: datetime.now(UTC)),
        follow_redirects=False,
    )
    login = dashboard.post("/login", data={"passphrase": "budget-demo"})

    assert (
        status,
        stderr.getvalue(),
        profile.name,
        current is None,
        login.status_code,
        serve.call_args.kwargs["host"],
        serve.call_args.kwargs["port"],
        "http://127.0.0.1:8877" in stdout.getvalue(),
    ) == (0, "", "development", False, 303, "127.0.0.1", 8877, True)


def test_demo_refuses_and_does_not_change_an_existing_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    stderr = io.StringIO()

    with (
        redirect_stderr(stderr),
        mock.patch("budget.cli.uvicorn.run") as serve,
    ):
        status = main(
            ["demo", "--directory", str(target), "--port", "8877"],
            environ={},
        )

    assert (
        status,
        "already exists" in stderr.getvalue(),
        sentinel.read_text(encoding="utf-8"),
        serve.called,
    ) == (3, True, "unchanged", False)


def test_the_demo_command_serves_a_real_login_and_htmx_report(
    tmp_path: Path,
) -> None:
    target = tmp_path / "live-demo"
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "budget",
            "demo",
            "--directory",
            str(target),
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    observe = None
    try:
        with httpx2.Client(base_url=url, timeout=2) as client:
            _wait_until_login(client)
            login = client.post(
                "/login",
                data={"passphrase": "budget-demo"},
            )
            overview = client.get("/")
            today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()
            month = f"{today.year}-{today.month:02d}"
            reference_date = today.replace(day=1).isoformat()
            report = client.get(
                "/report",
                params={
                    "publication": "1",
                    "reference_date": reference_date,
                    "account": "demo-current",
                    "month": month,
                },
                headers={"HX-Request": "true"},
            )
            observe = (
                overview.status_code,
                login.status_code,
                'data-canonical-url="/?publication=1' in overview.text,
                report.status_code,
                report.headers.get("hx-push-url"),
            )
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)

    assert observe == (
        200,
        303,
        True,
        200,
        (
            f"/?publication=1&reference_date={reference_date}"
            f"&account=demo-current&month={month}"
        ),
    ), (stdout, stderr)
