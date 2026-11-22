# Copyright 2026 Therkel
"""Login slowing: repeated failed logins lock login for a while.

One counter for the whole server, since there is one household passphrase
(#103 decisions).
"""

import math
import threading
from datetime import datetime, timedelta

# Failed logins in a row before login locks.
FAILURES_BEFORE_LOCK = 5
FIRST_LOCK = timedelta(seconds=30)
LONGEST_LOCK = timedelta(minutes=15)


class LoginThrottle:
    """Counts failed logins in a row and locks login after too many."""

    def __init__(self) -> None:
        """Start with no failures and no lock."""
        # Logins run on parallel threads. Hold `guard` from the lock check
        # through recording the outcome, or guesses sent together all pass the
        # check before any is counted, and five becomes forty.
        self.guard = threading.Lock()
        self._failures = 0
        self._lock_duration = FIRST_LOCK
        self._locked_until: datetime | None = None

    def seconds_locked(self, now: datetime) -> int:
        """Return how many whole seconds login stays locked, 0 when open."""
        if self._locked_until is None or now >= self._locked_until:
            return 0
        return math.ceil((self._locked_until - now).total_seconds())

    def succeeded(self) -> None:
        """Record a successful login: forget the failures and the doubling."""
        self._failures = 0
        self._lock_duration = FIRST_LOCK

    def failed(self, now: datetime) -> None:
        """Record a failed login made at `now`.

        Every fifth failure in a row locks login, each lock twice as long as
        the one before, up to `LONGEST_LOCK`.
        """
        self._failures += 1
        if self._failures >= FAILURES_BEFORE_LOCK:
            self._failures = 0
            self._locked_until = now + self._lock_duration
            self._lock_duration = min(self._lock_duration * 2, LONGEST_LOCK)
