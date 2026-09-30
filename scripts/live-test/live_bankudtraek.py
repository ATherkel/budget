"""Live-test #113 through the household layout: profile, accounts.toml, inbox.

Usage:
  uv run python live_bankudtraek.py <profile.toml> <from> <through>

A rough rehearsal of `budget import` (#117) with #149's account-number check:
- <profile.toml> is a development profile (operations.md "Profiles"); its
  [paths] name the stores, the inbox and the inputs.
- The account is the inbox folder a file sits in: inbox\\<account_id>\\*.csv.
- <from> and <through> are the inclusive range chosen on netbank's slider.
  An account exported with another range goes in RANGE_OVERRIDES.

Read-only on the household folder: nothing is moved to the archive, and no
line is written to imports.jsonl. Prints outcomes, counts and dates only.
"""

import re
import sqlite3
import sys
import tomllib
from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

from budget.bronze import BronzeStore, ImportDeclaration, migrate_bronze
from budget.bronze.parsers.registry import source_parser
from budget.profiles import Profile

# account_id -> (from, through), for an account exported with another range.
RANGE_OVERRIDES: dict[str, tuple[str, str]] = {}

# danske-csv-v1's filename convention: <name>-<account number>-<YYYYMMDD>.csv
ACCOUNT_NUMBER = re.compile(r"-(\d{10})-\d{8}(?:\(\d+\))?\.csv$", re.IGNORECASE)
# A browser's "(1)" copy hides the `-YYYYMMDD.csv` suffix the parser reads.
COPY_SUFFIX = re.compile(r"-(\d{8})\(\d+\)\.csv$", re.IGNORECASE)


def load_toml(path: Path) -> dict:
    """Read one TOML file, refusing a format version other than 1."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != 1:
        sys.exit(f"{path.name}: expected format = 1")
    return data


def inbox_files(inbox: Path, accounts: dict) -> list[tuple[str, Path]]:
    """Every .csv under inbox\\<account_id>\\, warning about unknown folders."""
    found = []
    for folder in sorted(p for p in inbox.iterdir() if p.is_dir()):
        csvs = sorted(folder.glob("*.csv"))
        if folder.name not in accounts:
            if csvs:
                print(f"SKIP inbox\\{folder.name}: not an account in accounts.toml")
            continue
        found += [(folder.name, csv) for csv in csvs]
    return found


def duplicate_groups(files: list[tuple[str, Path]]) -> list[list[tuple[str, Path]]]:
    """Inbox files whose bytes are identical across two or more accounts.

    A bank export carries no account number in its content, so the same bytes
    under two accounts means at least one download holds another account's
    transactions (seen twice with Danske, 2026-09-29 and 2026-09-30).
    """
    by_digest = defaultdict(list)
    for account, csv in files:
        by_digest[sha256(csv.read_bytes()).hexdigest()].append((account, csv))
    return [g for g in by_digest.values() if len({a for a, _ in g}) > 1]


def report_duplicates(groups: list[list[tuple[str, Path]]], accounts: dict) -> None:
    """Print each duplicate incident: its accounts, files, counts and spans."""
    print(
        f"\n{len(groups)} duplicate incident(s): identical bytes under different accounts"
    )
    for number, group in enumerate(groups, start=1):
        print(f"\nIncident {number}")
        print(f"  {'account':<22} {'records':>7}  {'transactions':<22} file")
        for account, csv in group:
            parser = source_parser(accounts[account]["source_format"])
            result = parser.parse(csv.read_bytes())
            span = transaction_span([r["Dato"] for r in result.records])
            print(f"  {account:<22} {len(result.records):>7}  {span:<22} {csv.name}")
    print("\nAt least one file per incident holds another account's transactions.")
    print("Re-download those accounts, checking netbank shows the right account.")


def files_to_import(
    files: list[tuple[str, Path]], accounts: dict
) -> list[tuple[str, Path]]:
    """Stop before importing when the inbox holds a duplicate incident."""
    groups = duplicate_groups(files)
    if not groups:
        return files
    report_duplicates(groups, accounts)
    try:
        answer = input("\nContinue anyway? [y/N] ") if sys.stdin.isatty() else ""
    except EOFError:  # a terminal with nothing behind it answers no
        answer = ""
    if answer.strip().lower() not in {"y", "yes"}:
        print("Nothing imported.")
        # Refused input (operations.md exit code 3): nothing is imported.
        sys.exit(3)
    # "Yes" imports the clean accounts only. Importing an incident's files
    # would let Bronze give the bytes to whichever account sorts first, so
    # they stay in the inbox for a re-download instead.
    #
    # Exercise for later: is this the right policy for `budget import`? The
    # alternative is importing everything and letting Bronze refuse all but
    # the first file of each incident. Weigh which one can store another
    # account's transactions under the wrong account, and which one blocks
    # the least of the inbox.
    suspect = {csv for group in groups for _, csv in group}
    skipped = len(suspect)
    print(f"Importing the clean files; {skipped} incident file(s) stay in the inbox.\n")
    return [(account, csv) for account, csv in files if csv not in suspect]


def number_mismatch(csv: Path, account: dict) -> bool:
    """#149: the filename's account number contradicts accounts.toml."""
    declared = account.get("bank_account_number")
    match = ACCOUNT_NUMBER.search(csv.name)
    return declared is not None and match is not None and match.group(1) != declared


def exported_on_of_copy(csv: Path) -> date | None:
    """Declare the export date of a "(1)" copy; None lets the parser read it."""
    copy = COPY_SUFFIX.search(csv.name)
    return datetime.strptime(copy.group(1), "%Y%m%d").date() if copy else None


def refusal_reasons(run, first: date | None, last: date | None) -> list[str]:
    """Re-derive why Bronze refused a run; the store keeps only the outcome.

    Mirrors budget.bronze.coverage.declared_range_refused and the one-owner
    rule in store._decide_outcome, so it can drift from them: it is a
    live-test aid, not the source of truth.
    """
    reasons = []
    owners = sqlite3.connect(
        f"file:{profile.bronze_store.as_posix()}?mode=ro", uri=True
    )
    owner = owners.execute(
        "SELECT declared_account_id FROM import_runs WHERE payload_id = ? "
        "AND outcome = 'stored' AND declared_account_id <> ? LIMIT 1",
        (run.payload_id, run.declared_account_id),
    ).fetchone()
    owners.close()
    if owner:
        reasons.append(f"same bytes already stored for {owner[0]}")
    if run.covers_from > run.covers_through:
        reasons.append("range starts after it ends")
    if run.covers_through > run.exported_on:
        reasons.append(f"range ends after the export date {run.exported_on}")
    if first is not None and first < run.covers_from:
        reasons.append(f"a transaction on {first} is before the range")
    if last is not None and last > run.covers_through:
        reasons.append(f"a transaction on {last} is after the range")
    return reasons


def transaction_span(dato_values: list[str]) -> str:
    """First..last Dato of a payload's records, or 'none'."""
    days = sorted(datetime.strptime(d, "%d.%m.%Y").date() for d in dato_values)
    return f"{days[0]}..{days[-1]}" if days else "none"


profile_file, default_from, default_through = sys.argv[1:]
settings = load_toml(Path(profile_file))
if settings.get("profile") != "development":
    sys.exit("refusing: this script only runs a development profile")
paths = {key: Path(value) for key, value in settings["paths"].items()}
accounts = load_toml(paths["inputs"] / "accounts.toml")["account"]

profile = Profile(name="development", stores=paths["stores"])
migrate_bronze(profile)  # creates on first run, no-op afterwards
print("store:", profile.bronze_store)

files = files_to_import(inbox_files(paths["inbox"], accounts), accounts)

with BronzeStore(profile) as store:
    for account_id, csv in files:
        account = accounts[account_id]
        if number_mismatch(csv, account):
            print(
                f"{account_id:<22} SKIP     filename's account number is not this account's"
            )
            continue
        covers_from, covers_through = RANGE_OVERRIDES.get(
            account_id, (default_from, default_through)
        )
        run = store.import_file(
            csv,
            ImportDeclaration(
                declared_account_id=account_id,
                source_format=account["source_format"],
                covers_from=date.fromisoformat(covers_from),
                covers_through=date.fromisoformat(covers_through),
                exported_on=exported_on_of_copy(csv),
            ),
        )
        records = store.get_source_records(run.payload_id)
        failures = [f.reason for f in store.get_format_failures(run.payload_id)]
        days = sorted(
            datetime.strptime(r.fields["Dato"], "%d.%m.%Y").date() for r in records
        )
        span = f"{days[0]}..{days[-1]}" if days else "none"
        print(
            f"{account_id:<22} {run.outcome:<8} records={len(records):<4} "
            f"declared={run.covers_from}..{run.covers_through} tx={span}"
            + (f"  FAIL: {failures[0]}" if failures else "")
        )
        if run.outcome == "refused":
            first, last = (days[0], days[-1]) if days else (None, None)
            for reason in refusal_reasons(run, first, last):
                print(f"{'':<22} why: {reason}")

db = sqlite3.connect(profile.bronze_store)
for table in ("raw_payloads", "import_runs", "source_records", "format_failures"):
    print(f"{table}: {db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]}")
db.close()
