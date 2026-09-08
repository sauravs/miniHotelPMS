# -*- coding: utf-8 -*-
"""
WHEN a control runs, and whether the evidence it ran on was still worth trusting.

Review finding F7: every IR has declared a trigger mode, its events, a minimum interval and a
maximum evidence age since the day it was written, and nothing has ever read any of it. Sections
4-12 and 22-23 of the requirements doc - arguably a third of it - were specified, encoded as
data, and dead. "Check every 30 minutes" is in the customer-facing mock-up.

TWO PURE FUNCTIONS, AND THE PURITY IS THE POINT
------------------------------------------------
    next_evaluation(ir, provider_events, clock, ...) -> Plan
    freshness_of(maximum_age, observed_at, now)      -> Freshness

A daemon is out of scope; the DECISION is not. Both functions are total functions of their
arguments with the clock injected, so every branch below is testable without a loop, a thread or
a sleep - and a real scheduler later is a thin loop around the first one.

THE RULE THAT CARRIES OVER FROM THE REST OF THE ENGINE
-------------------------------------------------------
Never invent an answer. A control whose events this provider does not publish and which
declares no fallback is UNSCHEDULABLE, and says so; it does not quietly acquire a plausible
interval. Evidence whose age cannot be established is STALE, not fresh. Both are the same rule
that makes UNKNOWN a first-class verdict, applied to time.
"""
from datetime import datetime, timedelta, timezone

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.runner.scheduling import (Freshness, ScheduleError, freshness_of,
                                             next_evaluation, parse_duration)
from hotelcontrols.spec import ControlIR

ZONE = "Asia/Jerusalem"
NOW = "2026-07-08T09:00"

# What the real PMS publishes, taken from the IR rationales rather than invented: reservation
# events and a dedicated room-occupancy one, and nothing for a room being taken out of service.
FULL = ("reservation.created", "reservation.updated", "room.occupancy_updated")


def clock(when=NOW):
    return FixedClock.at(when, ZONE)


def an_ir(execution, freshness="1h", control_id="a_control"):
    """A minimal IR carrying only what the scheduler reads.

    Built here rather than loaded from `spec/`, because the shipped controls use four of the
    six shapes the schema allows and the other two still have to work - `scheduled` and
    `before_event` are in the vocabulary and no control uses them yet.
    """
    return ControlIR({"control_id": control_id, "execution": execution,
                      "freshness_requirement": {"maximum_age": freshness}})


class TestDurations:
    def test_the_forms_the_shipped_controls_use(self):
        assert parse_duration("30m") == timedelta(minutes=30)
        assert parse_duration("1h") == timedelta(hours=1)
        assert parse_duration("24h") == timedelta(hours=24)
        assert parse_duration("90d") == timedelta(days=90)

    @pytest.mark.parametrize("text", ["", "1", "h", "1 h", "an hour", "1hour", "-1h", "1y",
                                      "1.5h", None])
    def test_anything_else_raises_rather_than_being_guessed_at(self, text):
        """The same rule the population layer applies to `today-1d`. A duration nobody can read
        must not become a plausible default: a control that quietly ran daily instead of hourly
        would look like it was working."""
        with pytest.raises(ScheduleError):
            parse_duration(text)


class TestEventMode:
    """Type A in the requirements doc: the control fires when something happens."""

    def test_a_control_whose_events_the_provider_publishes_subscribes_to_them(self):
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["reservation.updated"],
                   "fallback": {"mode": "periodic", "minimum_interval": "1h"}}),
            FULL, clock())
        assert plan.mode == "event"
        assert plan.events == ("reservation.updated",)
        assert plan.fell_back is False
        assert plan.next_run_at is None, "a subscription waits; it does not schedule"

    def test_an_event_the_provider_does_not_publish_falls_back_and_says_why(self):
        """The gate. A provider without the webhook must not silently never run - and must not
        silently pretend it subscribed either."""
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["room.occupancy_updated"],
                   "fallback": {"mode": "periodic", "minimum_interval": "1h"}}),
            ("reservation.created",), clock())
        assert plan.mode == "periodic"
        assert plan.fell_back is True
        assert plan.interval == timedelta(hours=1)
        assert "room.occupancy_updated" in plan.reason, (
            "the reason must name the missing event, or nobody can ask the vendor for it")

    def test_a_partly_supported_event_set_still_falls_back(self):
        """All or nothing. A control declaring two events needs both: subscribing to one and
        calling it done would miss exactly the transitions the other one covers."""
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["reservation.created", "room.occupancy_updated"],
                   "fallback": {"mode": "daily"}}),
            ("reservation.created",), clock())
        assert plan.fell_back is True and plan.mode == "daily"

    def test_no_webhook_and_no_fallback_is_unschedulable_rather_than_invented(self):
        """The rule that keeps this honest. There is no sensible default interval to reach for,
        and reaching for one would produce a control that appears to be running."""
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["room.occupancy_updated"]}), (), clock())
        assert plan.mode == "unschedulable"
        assert plan.next_run_at is None and plan.events == ()
        assert "room.occupancy_updated" in plan.reason


class TestPeriodicMode:
    """Type C: the state can change with no event at all, so it has to be re-checked."""

    def test_a_control_that_has_never_run_is_due_immediately(self):
        plan = next_evaluation(
            an_ir({"mode": "periodic", "minimum_interval": "6h"}), FULL, clock())
        assert plan.mode == "periodic"
        assert plan.next_run_at == clock().now()
        assert plan.is_due is True

    def test_the_next_run_is_one_interval_after_the_last(self):
        last = datetime.fromisoformat("2026-07-08T06:00+03:00")
        plan = next_evaluation(
            an_ir({"mode": "periodic", "minimum_interval": "6h"}), FULL, clock(),
            last_run_at=last)
        assert plan.next_run_at == last + timedelta(hours=6)
        assert plan.is_due is False, "06:00 plus six hours is noon, and it is nine"

    def test_a_run_that_is_overdue_says_it_is_due(self):
        last = datetime.fromisoformat("2026-07-07T06:00+03:00")
        plan = next_evaluation(
            an_ir({"mode": "periodic", "minimum_interval": "6h"}), FULL, clock(),
            last_run_at=last)
        assert plan.is_due is True

    def test_a_periodic_control_with_no_interval_is_a_spec_error(self):
        """`minimum_interval` is what the mode MEANS. A periodic control without one has not
        said anything, and defaulting would be this module deciding a hotel's policy."""
        with pytest.raises(ScheduleError):
            next_evaluation(an_ir({"mode": "periodic"}), FULL, clock())


class TestDailyMode:
    """Type D: a review queue rather than an alert. `checkout_unrefunded_credit` is one."""

    def test_a_control_that_has_not_run_today_is_due(self):
        plan = next_evaluation(an_ir({"mode": "daily"}), FULL, clock(),
                               last_run_at=datetime.fromisoformat("2026-07-07T23:00+03:00"))
        assert plan.mode == "daily" and plan.is_due is True

    def test_a_control_that_has_already_run_today_waits_for_tomorrow(self):
        plan = next_evaluation(an_ir({"mode": "daily"}), FULL, clock(),
                               last_run_at=datetime.fromisoformat("2026-07-08T02:00+03:00"))
        assert plan.is_due is False
        assert plan.next_run_at == datetime.fromisoformat("2026-07-09T00:00+03:00")

    def test_daily_means_the_property_s_day_and_not_the_machine_s(self):
        """F11, and the whole reason the clock is injected. At 23:30 in Jerusalem it is already
        the next day - and it is still the previous day almost everywhere else. A run "today"
        means the hotel's today or it means nothing.
        """
        # 2026-07-08 21:00 UTC is 2026-07-09 00:00 in Jerusalem: a new property day has begun,
        # so a control last run at 20:00 UTC has NOT yet run "today" by the hotel's calendar.
        last = datetime(2026, 7, 8, 20, 0, tzinfo=timezone.utc)
        jerusalem = FixedClock(datetime(2026, 7, 8, 21, 30, tzinfo=timezone.utc)
                               .astimezone(clock().instant.tzinfo))
        plan = next_evaluation(an_ir({"mode": "daily"}), FULL, jerusalem, last_run_at=last)
        assert plan.is_due is True, (
            "by the hotel's calendar this is a new day, and the machine's UTC date has not "
            "changed - which is exactly the disagreement F11 is about")


class TestScheduledMode:
    """The semantic schedule the requirements doc asks for: `before_event(arrival, 24h)` rather
    than a wall-clock time. No shipped control uses it yet; the vocabulary allows it, so it has
    to work or the schema is lying."""

    def test_before_event_subtracts_the_lead_time_from_the_event(self):
        arrival = datetime.fromisoformat("2026-07-10T14:00+03:00")
        plan = next_evaluation(
            an_ir({"mode": "scheduled",
                   "before_event": {"event": "arrival", "lead_time": "24h"}}),
            FULL, clock(), event_at=arrival)
        assert plan.mode == "scheduled"
        assert plan.next_run_at == datetime.fromisoformat("2026-07-09T14:00+03:00")

    def test_the_result_is_expressed_in_the_property_s_timezone_not_utc(self):
        """F11 again. A front-office manager reading "run at 11:00" needs that to be eleven
        o'clock in the hotel's lobby, not in a datacentre."""
        arrival_utc = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)   # 14:00 in Jerusalem
        plan = next_evaluation(
            an_ir({"mode": "scheduled",
                   "before_event": {"event": "arrival", "lead_time": "24h"}}),
            FULL, clock(), event_at=arrival_utc)
        assert plan.next_run_at.utcoffset() == timedelta(hours=3)
        assert plan.next_run_at.hour == 14

    def test_a_naive_event_time_is_refused_rather_than_assumed_to_be_local(self):
        """An instant without a timezone is ambiguous by definition, and guessing shifts the
        whole schedule by however many hours the guess was wrong."""
        with pytest.raises(ScheduleError):
            next_evaluation(
                an_ir({"mode": "scheduled",
                       "before_event": {"event": "arrival", "lead_time": "24h"}}),
                FULL, clock(), event_at=datetime(2026, 7, 10, 14, 0))

    def test_without_a_record_to_hang_it_on_the_plan_says_so_rather_than_guessing(self):
        """`before_event(arrival, 24h)` is a question about ONE reservation's arrival. Asked
        about the control in general, the honest answer is that it depends on the record."""
        plan = next_evaluation(
            an_ir({"mode": "scheduled",
                   "before_event": {"event": "arrival", "lead_time": "24h"}}),
            FULL, clock())
        assert plan.next_run_at is None
        assert "arrival" in plan.reason and "record" in plan.reason

    def test_a_scheduled_control_with_no_before_event_is_a_spec_error(self):
        with pytest.raises(ScheduleError):
            next_evaluation(an_ir({"mode": "scheduled"}), FULL, clock())


class TestFallbackShapes:
    def test_a_fallback_may_itself_be_event_driven(self):
        """`ooo_room_protection` is periodic first and event-driven underneath: the trigger is a
        room being blocked, which no provider here emits, so reservation events are the backstop
        rather than the primary. The shape has to be allowed in both directions."""
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["room.blocked"],
                   "fallback": {"mode": "event", "events": ["reservation.updated"]}}),
            FULL, clock())
        assert plan.mode == "event" and plan.fell_back is True
        assert plan.events == ("reservation.updated",)

    def test_a_fallback_that_also_cannot_run_ends_as_unschedulable(self):
        plan = next_evaluation(
            an_ir({"mode": "event", "events": ["room.blocked"],
                   "fallback": {"mode": "event", "events": ["room.inspected"]}}),
            FULL, clock())
        assert plan.mode == "unschedulable"
        assert "room.blocked" in plan.reason and "room.inspected" in plan.reason

    def test_a_mode_the_schema_does_not_define_raises(self):
        with pytest.raises(ScheduleError):
            next_evaluation(an_ir({"mode": "whenever"}), FULL, clock())


class TestPurity:
    def test_the_same_inputs_give_the_same_plan_every_time(self):
        ir = an_ir({"mode": "periodic", "minimum_interval": "6h"})
        first = next_evaluation(ir, FULL, clock())
        second = next_evaluation(ir, FULL, clock())
        assert first == second

    def test_the_plan_moves_only_when_the_clock_does(self):
        ir = an_ir({"mode": "periodic", "minimum_interval": "6h"})
        assert next_evaluation(ir, FULL, clock("2026-07-08T09:00")) != \
            next_evaluation(ir, FULL, clock("2026-07-08T10:00"))

    def test_the_provider_s_event_list_is_read_as_a_set_not_by_order(self):
        ir = an_ir({"mode": "event", "events": ["reservation.updated"]})
        assert next_evaluation(ir, FULL, clock()) == \
            next_evaluation(ir, tuple(reversed(FULL)), clock())


class TestFreshness:
    """Evidence older than `maximum_age` is marked stale on the run."""

    def test_evidence_within_the_maximum_age_is_fresh(self):
        answer = freshness_of("1h", _at("2026-07-08T08:30"), _at("2026-07-08T09:00"))
        assert answer.is_stale is False
        assert answer.age == timedelta(minutes=30)

    def test_evidence_older_than_the_maximum_age_is_stale_and_says_by_how_much(self):
        answer = freshness_of("1h", _at("2026-07-08T05:00"), _at("2026-07-08T09:00"))
        assert answer.is_stale is True
        assert "4:00" in answer.headline and "1:00" in answer.headline

    def test_evidence_exactly_at_the_limit_is_not_yet_stale(self):
        assert freshness_of("1h", _at("2026-07-08T08:00"), _at("2026-07-08T09:00")).is_stale \
            is False

    def test_evidence_whose_age_cannot_be_established_is_stale_rather_than_assumed_fresh(self):
        """The rule that makes this module part of the same system as the rest. An unknown age
        is not a fresh age, and a run that could not tell must not render as one that could."""
        answer = freshness_of("1h", None, _at("2026-07-08T09:00"))
        assert answer.is_stale is True and answer.is_known is False
        assert "could not" in answer.headline

    def test_a_maximum_age_nobody_can_read_is_stale_rather_than_ignored(self):
        answer = freshness_of("", _at("2026-07-08T08:30"), _at("2026-07-08T09:00"))
        assert answer.is_stale is True and answer.is_known is False

    def test_evidence_captured_after_the_instant_asked_about_is_not_called_stale(self):
        """Replaying a capture against a historical clock produces a negative age. It is not
        staleness - the evidence is newer than the question, not older - but it is worth
        saying, because it means the records may describe a state after the one asked about."""
        answer = freshness_of("1h", _at("2026-09-08T12:00"), _at("2026-07-08T09:00"))
        assert answer.is_stale is False
        assert "after" in answer.headline.lower()

    def test_a_freshness_verdict_is_a_sentence_a_person_can_act_on(self):
        for observed in (_at("2026-07-08T08:30"), _at("2026-07-08T05:00"), None):
            headline = freshness_of("1h", observed, _at("2026-07-08T09:00")).headline
            assert headline.endswith(".") and len(headline) > 25

    def test_freshness_is_a_pure_function_of_its_three_arguments(self):
        assert freshness_of("1h", _at("2026-07-08T08:30"), _at("2026-07-08T09:00")) == \
            freshness_of("1h", _at("2026-07-08T08:30"), _at("2026-07-08T09:00"))
        assert isinstance(
            freshness_of("1h", None, _at("2026-07-08T09:00")), Freshness)


def _at(when: str) -> datetime:
    return datetime.fromisoformat(when).replace(tzinfo=FixedClock.at(NOW, ZONE).instant.tzinfo)
