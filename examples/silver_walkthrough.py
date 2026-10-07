# Copyright 2026 Therkel
"""A synthetic Silver walkthrough, runnable on its own.

`budget rebuild --from silver` and `budget review` are exercised on invented
data in one temporary folder: a local development profile is written, two
exports are imported through the public `import_inbox_file` operation (the
`import` CLI does not exist yet), Silver is rebuilt and the open review items
are listed. Nothing outside the temporary folder is read or written, and no
real profile, export or bank data is touched.

Every identifier the commands print is real; this script replaces each run of
16 or more lowercase hexadecimal characters with `<id>`, so its transcript is
reproducible. Run it with:

    uv run python examples/silver_walkthrough.py
"""

import io
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.cli import main as budget_main
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile

ACCOUNTS = """\
format = 1

[account.joint-current]
display_name = "Joint current"
account_type = "current"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
"""
HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'
# One export the bank states cleanly, and one whose balance chain breaks.
MARCH = (("01.03.2026", "NETTO", "-45,00", "955,00"),)
APRIL = (
    ("01.04.2026", "NETTO", "-45,00", "955,00"),
    ("02.04.2026", "BIO", "-100,00", "955,00"),
)
_IDENTIFIER = re.compile(r"[0-9a-f]{16,}")


def _say(line: str) -> None:
    """Write one transcript line to stdout."""
    sys.stdout.write(line + "\n")


def _export(*rows: tuple[str, str, str, str]) -> bytes:
    """One synthetic `danske-csv-v1` payload, one row per tuple."""
    lines = [
        f'"{dato}"," Mad "," Dagligvarer ","{text}","{amount}","{balance}",'
        '"Udført","Nej"'
        for dato, text, amount, balance in rows
    ]
    return "\r\n".join([HEADER, *lines]).encode("cp1252")


def _budget(profile_file: Path, *arguments: str) -> tuple[int, str, str]:
    """Run one `budget` command in-process; return status, stdout, stderr."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = budget_main(["--profile", str(profile_file), *arguments], environ={})
    return status, stdout.getvalue(), stderr.getvalue()


def _show(command: str, outcome: tuple[int, str, str]) -> None:
    """Print one command's status line and its own, normalised output."""
    status, stdout, stderr = outcome
    _say(f"budget {command} -> {status}")
    for line in (stdout + stderr).splitlines():
        _say(f"  {_IDENTIFIER.sub('<id>', line)}")


def _import(profile: Profile, name: str, content: bytes, coverage: Coverage) -> str:
    """Import one synthetic export and return the run's Bronze outcome."""
    source = profile.inbox / "joint-current" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    with writer_lock(profile) as lock:
        imported = import_inbox_file(lock, source, coverage)
    return imported.import_run.outcome


def _rebuild(profile_file: Path) -> tuple[int, str, str]:
    """Run the one rebuild this walkthrough uses."""
    return _budget(profile_file, "rebuild", "--from", "silver")


def walkthrough(root: Path) -> None:
    """Run the whole synthetic walkthrough with every path under `root`."""
    stores = root / "stores"
    profile_file = root / "development.toml"
    profile_file.write_text(
        'format = 1\nprofile = "development"\n\n[paths]\n'
        f"stores = '{stores}'\ninputs = '{root / 'inputs'}'\n"
        f"inbox = '{root / 'inbox'}'\nexports = '{root / 'exports'}'\n",
        encoding="utf-8",
    )
    _show("migrate", _budget(profile_file, "migrate"))

    accounts = root / "inputs" / "accounts.toml"
    accounts.parent.mkdir(parents=True, exist_ok=True)
    accounts.write_text(ACCOUNTS, encoding="utf-8")
    profile = Profile(
        name="development",
        stores=stores,
        inputs=root / "inputs",
        inbox=root / "inbox",
        exports=root / "exports",
    )

    outcome = _import(
        profile,
        "danske-20260306.csv",
        _export(*MARCH),
        Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 5)),
    )
    _say(f"import_inbox_file joint-current -> {outcome}")
    _show("rebuild --from silver", _rebuild(profile_file))
    status, stdout, stderr = _budget(profile_file, "review")
    _show("review", (status, stdout or "(no open review items)", stderr))

    outcome = _import(
        profile,
        "danske-20260403.csv",
        _export(*APRIL),
        Coverage(covers_from=date(2026, 4, 1), covers_through=date(2026, 4, 2)),
    )
    _say(f"import_inbox_file joint-current -> {outcome}")
    _show("rebuild --from silver", _rebuild(profile_file))
    _show("review", _budget(profile_file, "review"))


def main() -> None:
    """Run the walkthrough in one temporary folder."""
    with TemporaryDirectory() as directory:
        walkthrough(Path(directory))


if __name__ == "__main__":
    main()
