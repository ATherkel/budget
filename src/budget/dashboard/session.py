# Copyright 2026 Therkel
"""Session cookies: an expiry signed with a key derived from the passphrase hash.

The dashboard keeps no session store (`operations.md` "Dashboard Access"), so
a cookie carries everything needed to check it, and cannot be forged.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

# A login lasts while it is used: each request renews it for this long.
LOGIN_LIFETIME = timedelta(days=30)


def _signature(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def issue(key: bytes, now: datetime) -> str:
    """Return a cookie value for a login made at `now`."""
    payload = str(int((now + LOGIN_LIFETIME).timestamp()))
    return f"{payload}.{_signature(key, payload)}"


def is_valid(key: bytes, value: str, now: datetime) -> bool:
    """Report whether `value` is a cookie signed with `key` that lasts past `now`."""
    payload, _, signature = value.partition(".")
    if not hmac.compare_digest(signature, _signature(key, payload)):
        return False
    return int(payload) > now.timestamp()
