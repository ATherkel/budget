# Copyright 2026 Therkel
"""A synthetic Silver walkthrough, runnable on its own.

`budget import` and `budget review` are exercised on invented data in one
temporary folder: a local development profile is written, and two exports are
each saved in the account's inbox folder and imported with
`budget import --ranges`, which rebuilds Silver after storing them. The open
review items are listed after each import. The profile, inbox, ranges files,
stores, archive, import log and routine log all stay in the temporary folder,
and no real profile, export or bank data is read or written.

Every identifier the commands print is real; this script replaces each run of
16 or more lowercase hexadecimal characters with `<id>`, so its transcript is
reproducible. A command's output is indented under it; a line starting with
`#` is the script's own note. Run it with:

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


def _import(profile_file: Path, name: str, content: bytes, ranges: Path) -> None:
    """Save one export in the account's inbox folder, then run `budget import`."""
    source = profile_file.parent / "inbox" / "joint-current" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    outcome = _budget(profile_file, "import", "--ranges", str(ranges))
    _show(f"import --ranges {ranges.name}", outcome)


def _ranges(path: Path, covers_from: date, covers_through: date) -> Path:
    """Write a ranges file declaring one default range, and return its path."""
    path.write_text(
        f"format = 1\n\n[default]\nfrom = {covers_from}\n"
        f"through = {covers_through}\n",
        encoding="utf-8",
    )
    return path


def _review(profile_file: Path) -> None:
    """List the open review items, noting when the command printed nothing."""
    status, stdout, stderr = _budget(profile_file, "review")
    _show("review", (status, stdout, stderr))
    if not stdout + stderr:
        _say("# (no output: no open review items)")


def walkthrough(root: Path) -> None:
    """Run the whole synthetic walkthrough with every path under `root`."""
    profile_file = root / "development.toml"
    profile_file.write_text(
        'format = 1\nprofile = "development"\n\n[paths]\n'
        f"stores = '{root / 'stores'}'\ninputs = '{root / 'inputs'}'\n"
        f"inbox = '{root / 'inbox'}'\nexports = '{root / 'exports'}'\n",
        encoding="utf-8",
    )
    _show("migrate", _budget(profile_file, "migrate"))

    accounts = root / "inputs" / "accounts.toml"
    accounts.parent.mkdir(parents=True, exist_ok=True)
    accounts.write_text(ACCOUNTS, encoding="utf-8")

    march = _ranges(root / "ranges-march.toml", date(2026, 3, 1), date(2026, 3, 5))
    _import(profile_file, "danske-20260306.csv", _export(*MARCH), march)
    _review(profile_file)

    april = _ranges(root / "ranges-april.toml", date(2026, 4, 1), date(2026, 4, 2))
    _import(profile_file, "danske-20260403.csv", _export(*APRIL), april)
    _review(profile_file)


def main() -> None:
    """Run the walkthrough in one temporary folder."""
    with TemporaryDirectory() as directory:
        walkthrough(Path(directory))


if __name__ == "__main__":
    main()
