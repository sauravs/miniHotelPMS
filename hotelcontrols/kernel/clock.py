# -*- coding: utf-8 -*-
"""
CLOCK - every date in this system is a question about the HOTEL's calendar.

Finding F11: v1 called `date.today()` and `datetime.now()`, naive, throughout. But every
control here is temporal and property-local:

    "reservations arriving within 24 hours"
    "reservations that checked out in the last 24 hours"
    "reservations created after the scheduled arrival time"

At 22:30 UTC on 7 July it is already 8 July in Jerusalem. A control asking "who checked out
today" gets a DIFFERENT POPULATION depending on which clock answers, and the hotel's clock is
the only one whose answer is correct. A run executed from a laptop in another timezone would
silently evaluate a different question - silently being the problem.

The requirements doc says so outright: `"time": "08:00", "timezone": "property"`.

THE CLOCK IS INJECTED, NEVER GLOBAL. A test sets it rather than depending on the machine the
test happens to run on, and `FixedClock` is what makes a run reproducible six months later -
the difference between an audit trail and an anecdote.

R3 is the related limitation this cannot fix: the provider's creation timestamp is DATE
ONLY, with no time
component, so any control needing same-day precision is unanswerable no matter how good the
clock is. That is stated by the evidence layer as UNKNOWN, not papered over here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@runtime_checkable
class Clock(Protocol):
    """What the rest of the engine is allowed to know about time."""

    def today(self) -> date:
        """The current date IN THE PROPERTY'S TIMEZONE."""

    def now(self) -> datetime:
        """The current instant, timezone-aware, in the property's timezone."""


def _zone(name: str) -> ZoneInfo:
    """Resolve an IANA timezone, or refuse.

    A typo in a tenant config must fail loudly. Falling back to UTC would shift every
    population window by a few hours and produce runs that are wrong in a way nobody notices
    until a control misses a checkout.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(
            "%r is not an IANA timezone - a property's timezone must be explicit and real, "
            "because it decides which records a control even looks at" % (name,)) from None


@dataclass(frozen=True, slots=True)
class PropertyClock:
    """The production clock: real time, read in one property's timezone.

    `instant` exists so the same class can be pinned in a test without a second
    implementation of the timezone arithmetic - two implementations is two chances to
    disagree about the thing that decides a population.
    """

    timezone: str
    instant: datetime | None = None

    def __post_init__(self) -> None:
        _zone(self.timezone)                      # validate at construction, not at first use

    def now(self) -> datetime:
        moment = self.instant if self.instant is not None else datetime.now(tz=timezone.utc)
        if moment.tzinfo is None:
            # A naive instant is ambiguous by definition; treating it as UTC would be a guess.
            raise ValueError("a clock's instant must be timezone-aware")
        return moment.astimezone(_zone(self.timezone))

    def today(self) -> date:
        return self.now().date()


@dataclass(frozen=True, slots=True)
class FixedClock:
    """A clock that does not move. The only clock any test may use.

    Determinism is the point: the same evidence must yield the same verdict forever, which is
    what lets a stored run be re-read and defended months after it was made.
    """

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("a fixed clock needs a timezone-aware instant, so that the date "
                             "it reports is a fact rather than an assumption")

    @classmethod
    def at(cls, when: str, timezone_name: str) -> FixedClock:
        """`FixedClock.at("2026-07-08T14:30", "Asia/Jerusalem")` - the readable form."""
        return cls(datetime.fromisoformat(when).replace(tzinfo=_zone(timezone_name)))

    def now(self) -> datetime:
        return self.instant

    def today(self) -> date:
        return self.instant.date()
