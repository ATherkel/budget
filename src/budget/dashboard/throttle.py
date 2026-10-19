# Copyright 2026 Therkel
"""Login slowing: repeated failed logins lock login for a while.

One counter for the whole server, since there is one household passphrase
(#103 decisions).
"""

import math
from datetime import datetime, timedelta

# Failed logins in a row before login locks.
FAILURES_BEFORE_LOCK = 5
FIRST_LOCK = timedelta(seconds=30)


class LoginThrottle:
    """Counts failed logins in a row and locks login after too many."""

    def __init__(self) -> None:
        """Start with no failures and no lock."""
        self._failures = 0
        self._locked_until: datetime | None = None

    def seconds_locked(self, now: datetime) -> int:
        """Return how many whole seconds login stays locked, 0 when open."""
        if self._locked_until is None or now >= self._locked_until:
            return 0
        return math.ceil((self._locked_until - now).total_seconds())

    def failed(self, now: datetime) -> None:
        """Record a failed login made at `now`."""
        self._failures += 1
        if self._failures >= FAILURES_BEFORE_LOCK:
            self._failures = 0
            self._locked_until = now + FIRST_LOCK
