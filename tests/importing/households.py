# Copyright 2026 Therkel
"""Synthetic households for the import tests.

A household is a migrated test profile with its own `accounts.toml`, and
`danske-csv-v1` exports dropped into its inbox. Every account, date, text and
amount here is invented.
"""

import json
from pathlib import Path

from budget.bronze import migrate_bronze
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile

ACCOUNTS = """\
format = 1

[account.joint-current]
display_name = "Joint current"
account_type = "current"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
bank_account_number = "0012345678"

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
"""

_HEADER = '"Dato","Kategori","Underkategori","Tekst","Beløb","Saldo","Status","Afstemt"'


def household(root: Path) -> Profile:
    """Build and migrate a test profile whose inputs hold `ACCOUNTS`."""
    profile = make_test_profile(root)
    migrate_bronze(profile)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def payload(*datos: str) -> bytes:
    """A `danske-csv-v1` export with one synthetic record per `Dato`."""
    rows = [
        f'"{dato}"," Mad "," Dagligvarer ","Café","-45,00","955,00","Udført","Nej"'
        for dato in datos
    ]
    return "\r\n".join([_HEADER, *rows]).encode("cp1252")


def drop(profile: Profile, account_id: str, name: str, content: bytes) -> Path:
    """Save an export into one account's inbox folder, as the household does."""
    folder = profile.inbox / account_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    return path


def log_entries(profile: Profile) -> list[dict[str, object]]:
    """Read `imports.jsonl`, whose every entry must end with a line feed."""
    text = profile.import_log_file.read_text(encoding="utf-8")
    assert text.endswith("\n")
    return [json.loads(line) for line in text.splitlines()]
