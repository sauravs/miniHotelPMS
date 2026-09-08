# -*- coding: utf-8 -*-
"""
Clock - every date in this system is a question about the HOTEL's calendar.

Finding F11 from the v1 review: v1 called `date.today()` and `datetime.now()`, naive,
throughout. But every control here is temporal and property-local. "Arriving within 24 hours",
"checked out in the last 24 hours", "created after the scheduled arrival time" are all
questions about the property's clock, and a run executed from a different timezone silently
evaluates a different population.

The requirements doc says so explicitly: `"time": "08:00", "timezone": "property"`.

The clock is INJECTED, never global, so a test sets it rather than depending on the machine
the test happens to run on.
"""
from datetime import date, datetime

import pytest

from hotelcontrols.kernel import Clock, FixedClock, PropertyClock


class TestFixedClock:
    def test_a_fixed_clock_is_a_clock(self):
        assert isinstance(FixedClock.at("2026-07-08T14:30", "Asia/Jerusalem"), Clock)

    def test_a_fixed_clock_does_not_move(self):
        """Determinism is the whole point: the same bundle must yield the same verdict forever."""
        clock = FixedClock.at("2026-07-08T14:30", "Asia/Jerusalem")
        assert clock.today() == date(2026, 7, 8)
        assert clock.today() == date(2026, 7, 8)

    def test_now_is_timezone_aware(self):
        """A naive datetime is a bug waiting for a daylight-saving boundary."""
        assert FixedClock.at("2026-07-08T14:30", "Asia/Jerusalem").now().tzinfo is not None


class TestPropertyTimezone:
    def test_the_property_timezone_decides_the_date_not_the_machine(self):
        """The test that makes F11 concrete.

        At 22:30 UTC on 7 July it is already 8 July in Jerusalem. A control asking "who
        checked out today" gets a different population depending on which clock answers, and
        the hotel's clock is the only one whose answer is correct.
        """
        instant = datetime.fromisoformat("2026-07-07T22:30:00+00:00")
        assert PropertyClock("Asia/Jerusalem", instant=instant).today() == date(2026, 7, 8)
        assert PropertyClock("UTC", instant=instant).today() == date(2026, 7, 7)
        assert PropertyClock("America/New_York", instant=instant).today() == date(2026, 7, 7)

    def test_an_unknown_timezone_is_refused_at_construction(self):
        """A typo in a tenant config must fail loudly, not silently fall back to UTC and
        shift every population window by a few hours."""
        with pytest.raises(ValueError):
            PropertyClock("Middle/Earth")

    def test_a_property_clock_without_a_fixed_instant_reads_the_wall_clock(self):
        """The production path. Asserted only for shape - a test that asserts the actual
        time is a test that fails at midnight."""
        assert isinstance(PropertyClock("Asia/Jerusalem").today(), date)

    def test_a_clock_is_immutable(self):
        clock = PropertyClock("Asia/Jerusalem")
        with pytest.raises((AttributeError, TypeError)):
            clock.timezone = "UTC"
