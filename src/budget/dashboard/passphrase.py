# Copyright 2026 Therkel
"""The household passphrase, kept as a `scrypt` hash in the profile's passphrase file.

`operations.md` "Dashboard Access": the file holds the hash, never the
passphrase, and lives outside OneDrive and the repository.
"""

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

from budget.durability import sync_folder
from budget.profiles import Profile

# scrypt's cost: 2**15 x 8 blocks is 32 MiB and a fraction of a second, so a
# guessed passphrase costs the guesser the same.
_COST = 2**15
_BLOCK_SIZE = 8
_PARALLELISM = 1
_MAX_MEMORY = 64 * 1024 * 1024
_FORMAT = 1


def _hash(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode(),
        salt=salt,
        n=_COST,
        r=_BLOCK_SIZE,
        p=_PARALLELISM,
        maxmem=_MAX_MEMORY,
    )


class PassphraseNotSetError(Exception):
    """No passphrase guards the dashboard yet, so it must not start."""

    def __init__(self, profile: str) -> None:
        """Name the command that sets one."""
        super().__init__(
            f"no dashboard passphrase is set for the {profile} profile: "
            "run `budget set-passphrase` first"
        )


def require_passphrase(profile: Profile) -> None:
    """Refuse a profile whose dashboard has no passphrase set."""
    if profile.passphrase_file is None or not profile.passphrase_file.exists():
        raise PassphraseNotSetError(profile.name)


def _passphrase_file(profile: Profile) -> Path:
    if profile.passphrase_file is None:
        message = f"the {profile.name} profile names no [dashboard] passphrase_file"
        raise ValueError(message)
    return profile.passphrase_file


def set_passphrase(profile: Profile, passphrase: str) -> None:
    """Make `passphrase` the one the dashboard of `profile` accepts."""
    salt = secrets.token_bytes(16)
    content = json.dumps(
        {
            "format": _FORMAT,
            "salt": salt.hex(),
            "scrypt": _hash(passphrase, salt).hex(),
        }
    ).encode("utf-8")
    path = _passphrase_file(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside it, then swapped in whole: `serve` reads the file on every
    # check, so it must never see a half-written one, even after a crash.
    descriptor, partial_name = tempfile.mkstemp(
        dir=path.parent, prefix=".", suffix=".partial"
    )
    partial = Path(partial_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    sync_folder(path.parent)


def _stored(profile: Profile) -> dict[str, str]:
    """Read the passphrase file afresh, so `set-passphrase` takes effect at once."""
    stored = json.loads(_passphrase_file(profile).read_text(encoding="utf-8"))
    return {"salt": str(stored["salt"]), "scrypt": str(stored["scrypt"])}


def passphrase_matches(profile: Profile, candidate: str) -> bool:
    """Report whether `candidate` is the passphrase set for `profile`."""
    stored = _stored(profile)
    expected = bytes.fromhex(stored["scrypt"])
    return hmac.compare_digest(
        _hash(candidate, bytes.fromhex(stored["salt"])), expected
    )


def session_key(profile: Profile) -> bytes:
    """Return the key that signs session cookies, derived from the stored hash.

    A new passphrase gives a new key, so it invalidates every cookie signed
    before it.
    """
    stored_hash = bytes.fromhex(_stored(profile)["scrypt"])
    return hashlib.sha256(b"budget dashboard session\0" + stored_hash).digest()
