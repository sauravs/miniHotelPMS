# -*- coding: utf-8 -*-
"""
TOKEN BUCKET - how fast this engine is allowed to be a guest on someone else's server.

R8: the vendor asks integrators not to query wide ranges without prior agreement, and the
sandbox we hold credentials for belongs to them. R1 says the same thing from the other side: a
folio is one call per reservation and there is no bulk journal endpoint, so a control over a
hundred checkouts is a hundred calls whether or not anybody thought about pacing.

The bucket is a PURE FUNCTION OF ITS CLOCK. It never sleeps and never reads a wall clock: it is
asked "may I go now?" and answers "yes" or "wait this long", and the caller does the waiting.
Two reasons, and the second one is why F11 turns up in a rate limiter at all:

  * a limiter that slept could not be tested without a test that also slept, so it would be
    tested loosely or not at all - and a rate limiter that is wrong is wrong in production, on
    somebody else's infrastructure, at a moment when nobody is watching;
  * a limiter reading `time.monotonic()` behaves differently on every machine and cannot be
    replayed, which is the same defect as a run whose population depended on which laptop asked.
"""
from __future__ import annotations

from datetime import timedelta

from ...kernel import Clock

ZERO = timedelta(0)


class TokenBucket:
    """`capacity` calls may go at once; one more is earned every `interval`.

    A burst is allowed on purpose - a run's population call, its reference calls and its first
    follow-up should not be spaced out for the sake of it - but the bucket never banks more
    than its capacity, so an idle hour cannot buy an hour's worth of calls in one go. That
    burst is exactly the traffic shape the vendor asked not to receive.
    """

    __slots__ = ("capacity", "interval", "clock", "_tokens", "_at")

    def __init__(self, capacity: int, interval: timedelta, clock: Clock,
                 tokens: float | None = None) -> None:
        if capacity < 1:
            raise ValueError("a bucket that lets nothing through is a bucket that stops a run "
                             "without saying so - use the call budget to refuse instead")
        if interval <= ZERO:
            raise ValueError("an interval of zero is not a rate limit")
        self.capacity = capacity
        self.interval = interval
        self.clock = clock
        self._tokens = float(capacity if tokens is None else tokens)
        self._at = clock.now()

    def take(self) -> timedelta:
        """How long the caller must wait before making its call. Zero means go now.

        The wait is ACCOUNTED FOR HERE, not merely reported: the bucket advances its own idea
        of the time by however long it just told the caller to sleep. Without that, a caller
        who obeyed would be told to wait the same interval again on its next call, and the
        limiter would stall a run rather than pace it.
        """
        now = max(self.clock.now(), self._at)
        earned = (now - self._at) / self.interval
        self._tokens = min(float(self.capacity), self._tokens + earned)
        self._at = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return ZERO

        wait = (1.0 - self._tokens) * self.interval
        self._tokens = 0.0
        self._at = now + wait
        return wait

    def __repr__(self) -> str:
        return "TokenBucket(%.2f/%d tokens, one per %s)" % (
            self._tokens, self.capacity, self.interval)
