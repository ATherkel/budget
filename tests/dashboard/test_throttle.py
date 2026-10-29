# Copyright 2026 Therkel
"""The public login throttle stays bounded under repeated lockout cycles."""

from datetime import UTC, datetime, timedelta

from budget.dashboard.throttle import LoginThrottle


def test_repeated_lockouts_remain_capped_after_the_forty_third_cycle() -> None:
    throttle = LoginThrottle()
    now = datetime(2026, 5, 14, 9, tzinfo=UTC)
    waits = []

    for _ in range(50):
        for _ in range(5):
            throttle.failed(now)
        wait = throttle.seconds_locked(now)
        waits.append(wait)
        now += timedelta(seconds=wait)

    assert (waits[:7], set(waits[5:])) == (
        [30, 60, 120, 240, 480, 900, 900],
        {900},
    )
