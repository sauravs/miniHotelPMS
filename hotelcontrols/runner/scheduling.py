# -*- coding: utf-8 -*-
"""
SCHEDULING & FRESHNESS - when a control runs, and whether what it ran on was still worth
trusting.

    next_evaluation(ir, provider_events, clock, last_run_at=None, event_at=None) -> Plan
    freshness_of(maximum_age, observed_at, now)                                  -> Freshness

Review finding F7. Every IR has declared a trigger mode, its events, a minimum interval and a
maximum evidence age since the day it was written, and until this module nothing read any of it.
Sections 4-12 and 22-23 of `control_rule_architecture.docx` - arguably a third of it - were
specified, encoded as data, and dead.

BOTH FUNCTIONS ARE PURE, AND THAT IS THE DESIGN RATHER THAN A CONVENIENCE
-------------------------------------------------------------------------
A daemon is out of scope; the DECISION is not. `next_evaluation` is a total function of the IR,
what the provider publishes, an injected clock and two optional instants - so every branch is
testable without a loop, a thread or a sleep, and a real scheduler later is a `while True` around
it. Nothing here reads a wall clock; a test asserts that for the whole engine.

THE RULE THAT CARRIES OVER FROM THE REST OF THE ENGINE
-------------------------------------------------------
Never invent an answer.

  * A control whose events this provider does not publish, and which declares no fallback, is
    UNSCHEDULABLE and says which event is missing. There is no sensible default interval to
    reach for, and reaching for one would produce a control that merely APPEARS to be running -
    the scheduling form of turning an UNKNOWN into a PASS.
  * Evidence whose age cannot be established is STALE. An unknown age is not a fresh age.

WHY THE PROVIDER IS ASKED WHAT IT PUBLISHES
--------------------------------------------
Because it differs, and the difference is not a defect. The real PMS publishes reservation
events and a dedicated room-occupancy one, and emits nothing at all when a room is taken out of
service. A control declaring `room.occupancy_updated` therefore runs in real time on one
provider and on a timer on another - the same rule, the same verdicts, a different trigger, and
the plan says which and why. Event names are CANONICAL, like every other name above the
adapter; what each provider publishes is a capability it declares.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Iterable

from ..kernel import Clock

# The duration grammar the IRs use: a whole number of minutes, hours or days. Deliberately
# small - every shipped control is expressed in it, and a wider grammar is a wider surface for
# a duration to be misread.
_DURATION = re.compile(r"^(\d+)(m|h|d)$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}

MODES = ("event", "scheduled", "periodic", "daily")

# How deep a fallback chain may go. The schema allows a fallback to declare any execution
# block, including its own fallback; one level of backstop is a design and three is a maze
# nobody can predict the behaviour of.
_MAX_FALLBACK_DEPTH = 2


class ScheduleError(ValueError):
    """This control's execution block cannot be turned into a plan.

    A spec error, not an evidence gap - the distinction the whole engine keeps. "Nobody said
    how often" is a statement about US; "the provider does not publish that event" is a
    statement about a PMS, and that one produces a Plan rather than an exception.
    """


# --------------------------------------------------------------------------- durations
def parse_duration(text: Any) -> timedelta:
    """`30m`, `1h`, `24h`, `90d` - or a refusal.

    Raises rather than defaulting, for the same reason the population layer raises on a
    relative-date token it does not recognise. A duration nobody can read must not quietly
    become a plausible one: a control that ran daily where it meant hourly would look exactly
    like a control that was working.
    """
    match = _DURATION.match(text) if isinstance(text, str) else None
    if match is None:
        raise ScheduleError(
            "%r is not a duration this engine reads - use a whole number of minutes, hours or "
            "days (30m, 1h, 90d). Guessing would silently change how often a control runs"
            % (text,))
    return timedelta(**{_UNITS[match.group(2)]: int(match.group(1))})


# --------------------------------------------------------------------------- the plan
@dataclass(frozen=True, slots=True)
class Plan:
    """When this control will next be evaluated, and why that is the answer."""

    control_id: str
    declared_mode: str
    # What will ACTUALLY happen: one of MODES, or "unschedulable". Kept separate from
    # `declared_mode` so a run page can show "asked for real time, got hourly, here is why"
    # rather than either one alone.
    mode: str
    as_of: datetime
    events: tuple[str, ...] = ()
    next_run_at: datetime | None = None
    interval: timedelta | None = None
    fell_back: bool = False
    reason: str = ""

    @property
    def is_subscription(self) -> bool:
        """Whether this control waits for the PMS to tell it something happened."""
        return self.mode == "event"

    @property
    def is_schedulable(self) -> bool:
        return self.mode != "unschedulable"

    @property
    def is_due(self) -> bool:
        """Whether it should run now. A subscription is never 'due'; it is waiting."""
        return self.next_run_at is not None and self.next_run_at <= self.as_of

    @property
    def headline(self) -> str:
        """The line that goes next to the control's name."""
        if self.mode == "unschedulable":
            return "This control has no trigger on this provider. %s" % self.reason
        if self.is_subscription:
            return "Waiting for %s. %s" % (", ".join(self.events), self.reason)
        if self.next_run_at is None:
            return "Scheduled per record. %s" % self.reason
        when = "due now" if self.is_due else "due %s" % self.next_run_at.isoformat()
        return "Runs %s, %s. %s" % (self.mode, when, self.reason)

    def __repr__(self) -> str:
        return "Plan(%s, %s%s)" % (self.control_id, self.mode,
                                   ", fell back" if self.fell_back else "")


def next_evaluation(ir, provider_events: Iterable[str], clock: Clock,
                    last_run_at: datetime | None = None,
                    event_at: datetime | None = None) -> Plan:
    """When this control should next be evaluated on this provider.

    `provider_events` is what the PMS publishes, in canonical names. `event_at` is the instant
    of the event a `scheduled` control hangs off - a specific reservation's arrival - and is
    absent when the question is about the control in general rather than about one record.
    """
    published = frozenset(provider_events or ())
    execution = ir["execution"]
    control_id = ir.get("control_id", "this control")
    return _plan(control_id, execution, execution.get("mode"), published, clock,
                 last_run_at, event_at, missing=(), depth=0)


def _plan(control_id, execution, declared_mode, published, clock, last_run_at, event_at,
          missing, depth) -> Plan:
    """One execution block, as a plan - recursing into the fallback when it cannot be used."""
    mode = execution.get("mode")
    now = clock.now()
    common = dict(control_id=control_id, declared_mode=declared_mode, as_of=now,
                  fell_back=depth > 0)

    if mode not in MODES:
        raise ScheduleError(
            "%s declares execution mode %r, which is not one of %s"
            % (control_id, mode, ", ".join(MODES)))

    if mode == "event":
        declared = tuple(execution.get("events", ()))
        unpublished = tuple(e for e in declared if e not in published)
        if not unpublished:
            if not declared:
                # Event mode with no events is a control that waits for nothing. Not a spec
                # error - the schema allows it - but it will never run, and saying so is the
                # difference between a quiet subscription and a control nobody notices is dead.
                return Plan(mode="unschedulable", **common,
                            reason=("this control is event-driven and declares no event, so "
                                    "nothing would ever cause it to run"))
            return Plan(mode="event", events=declared, **common,
                        reason=("This provider publishes %s, so the control runs when the "
                                "hotel's data actually changes." % ", ".join(declared)))
        return _fall_back(control_id, execution, declared_mode, published, clock, last_run_at,
                          event_at, missing + unpublished, depth)

    if mode == "periodic":
        interval = parse_duration(execution.get("minimum_interval"))
        due = (last_run_at + interval) if last_run_at is not None else now
        return Plan(mode="periodic", interval=interval, next_run_at=due,
                    reason=_why(missing, "re-checked every %s, because the state it watches "
                                         "can change with no event at all" % _human(interval)),
                    **common)

    if mode == "daily":
        return Plan(mode="daily", interval=timedelta(days=1),
                    next_run_at=_next_daily(last_run_at, clock),
                    reason=_why(missing, "a review queue rather than an alert, so once per "
                                         "property day is enough"),
                    **common)

    # `scheduled` - the semantic form the requirements doc asks for: before_event(arrival, 24h)
    # rather than a wall-clock time, because the hotel's rule is about the guest's arrival and
    # not about half past two.
    before = execution.get("before_event")
    if not before:
        raise ScheduleError(
            "%s is scheduled but declares no `before_event`. A scheduled control with nothing "
            "to be scheduled BEFORE has not said when it runs" % control_id)
    lead = parse_duration(before.get("lead_time"))
    event_name = before.get("event", "the event")

    if event_at is None:
        return Plan(mode="scheduled", interval=lead,
                    reason=_why(missing, "runs %s before each %s, so when it runs depends on "
                                         "the record - ask again with one"
                                         % (_human(lead), event_name)),
                    **common)
    if event_at.tzinfo is None:
        raise ScheduleError(
            "the %s used to schedule %s has no timezone. An instant without one is ambiguous "
            "by definition, and guessing shifts the whole schedule by however many hours the "
            "guess was wrong (F11)" % (event_name, control_id))

    # Expressed in the PROPERTY's timezone. A manager reading "run at 11:00" needs that to be
    # eleven o'clock in the hotel's lobby rather than in a datacentre.
    local = event_at.astimezone(now.tzinfo)
    return Plan(mode="scheduled", interval=lead, next_run_at=local - lead,
                reason=_why(missing, "%s before this record's %s" % (_human(lead), event_name)),
                **common)


def _fall_back(control_id, execution, declared_mode, published, clock, last_run_at, event_at,
               missing, depth) -> Plan:
    """What to do when the declared trigger is not available on this provider."""
    fallback = execution.get("fallback")
    if not fallback or depth >= _MAX_FALLBACK_DEPTH:
        # No backstop. The honest answer is that this control has no trigger here - NOT a
        # plausible interval, which would produce a control that appears to be running.
        return Plan(control_id=control_id, declared_mode=declared_mode, mode="unschedulable",
                    as_of=clock.now(), fell_back=depth > 0,
                    reason=("this provider publishes no %s, and no fallback trigger is "
                            "declared, so nothing would ever cause it to run"
                            % ", ".join(dict.fromkeys(missing))))
    return _plan(control_id, fallback, declared_mode, published, clock, last_run_at, event_at,
                 missing, depth + 1)


def _next_daily(last_run_at: datetime | None, clock: Clock) -> datetime:
    """Midnight at the start of the next PROPERTY day, or now if today's run has not happened.

    F11, and the case that makes the injected clock load-bearing rather than tidy. At 21:30 UTC
    it is already tomorrow in Jerusalem, so a control last run at 20:00 UTC has not yet run
    "today" by the hotel's calendar - and the hotel's calendar is the only one whose answer to
    "has this run today" is correct.
    """
    now = clock.now()
    if last_run_at is None or last_run_at.astimezone(now.tzinfo).date() < clock.today():
        return now
    tomorrow = clock.today() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=now.tzinfo)


def _why(missing: tuple[str, ...], because: str) -> str:
    """One sentence saying why this plan and not another.

    When the control fell back, the sentence NAMES the event that was missing. That is the
    whole usefulness of the field: "runs every six hours" is a schedule, and "runs every six
    hours because this PMS publishes no room.occupancy_updated" is something a hotel can take
    to its vendor.
    """
    if not missing:
        return "It is %s." % because
    return ("This provider publishes no %s, so instead it is %s."
            % (", ".join(dict.fromkeys(missing)), because))


def _human(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    for size, name in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds % size == 0 and seconds >= size:
            count = seconds // size
            return "%d %s%s" % (count, name, "" if count == 1 else "s")
    return str(delta)


# --------------------------------------------------------------------------- freshness
@dataclass(frozen=True, slots=True)
class Freshness:
    """How old the evidence behind a run was, against what the control asks for.

    A run reusing evidence older than `freshness_requirement.maximum_age` has to say so. It is
    still a real answer about real records - staleness is not an error - but an hourly control
    answering from yesterday's snapshot is making a claim about yesterday, and a reader deciding
    whether to act on it needs to know which.
    """

    maximum_age: timedelta | None
    observed_at: datetime | None
    as_of: datetime

    @property
    def age(self) -> timedelta | None:
        if self.observed_at is None:
            return None
        return self.as_of - self.observed_at

    @property
    def is_known(self) -> bool:
        """Whether the age could be established at all."""
        return self.observed_at is not None and self.maximum_age is not None

    @property
    def is_stale(self) -> bool:
        """UNKNOWN DOES NOT MEAN FRESH. An age nobody could establish is treated as stale, for
        the same reason a value nobody could establish is not a PASS."""
        if not self.is_known:
            return True
        return self.age > self.maximum_age

    @property
    def headline(self) -> str:
        if not self.is_known:
            return ("The age of this run's evidence could not be established, so it is treated "
                    "as stale rather than assumed to be current.")
        if self.age < timedelta(0):
            return ("This evidence was captured %s AFTER the instant this run asks about, so "
                    "it may describe a later state than the question."
                    % _human(-self.age))
        if self.is_stale:
            return ("This run's evidence was %s old and this control asks for evidence under "
                    "%s. It is a real answer about real records, and it is out of date."
                    % (self.age, self.maximum_age))
        return ("This run's evidence was %s old, within the %s this control asks for."
                % (self.age, self.maximum_age))


def freshness_of(maximum_age: Any, observed_at: datetime | None,
                 now: datetime) -> Freshness:
    """How stale one run's evidence is. A pure function of three values and nothing else.

    An unreadable `maximum_age` yields an unknown-and-therefore-stale answer rather than an
    exception: unlike an execution mode, this one is reached while RENDERING a run that already
    happened, and a page that raises tells a reader less than a page that says it cannot tell.
    """
    try:
        limit = parse_duration(maximum_age)
    except ScheduleError:
        limit = None
    return Freshness(maximum_age=limit, observed_at=observed_at, as_of=now)
