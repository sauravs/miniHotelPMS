# -*- coding: utf-8 -*-
"""
DECISION - one guest request, judged by the approved LATE_CHECKOUT table, line by line.

    decide(request, policy, evidence, today) -> Ruling      pure: no provider, no store, no clock
    make_decision(template, ..., ruling)     -> Decision    the ruling, identified and versioned

The table is `spec/guest/late_checkout.json`, approved by the owner at slice 22's checkpoint.
Each rule below carries the id the table gives it, in the table's order, and `RULES` is checked
against the file when the template loads (`template.py`): a table edited without the engine, or
an engine edited without the table, refuses to run rather than deciding by whichever is newer.

STAFF_REVIEW IS GUEST SERVICES' UNKNOWN (plan-v3 §5)
----------------------------------------------------
The first rule collects EVERY gap - a reservation not found, a status nobody has named (`OK4`,
`WL`), a departure date that cannot be read, a parameter the hotel has not decided - and, if
there is one, the answer is STAFF_REVIEW naming all of them. Nothing below it can run on a
guess, so nothing below it can be reached from missing evidence: DENIED comes only from a status
or a date that was established, or from the hotel's stated maximum; APPROVED only from a stated
policy applied to a guest the PMS shows checked in and departing today. That is V10, and the
reason this rule is first rather than one check among many.

UNAVAILABLE IS NEVER REACHED IN v3. Late checkout is unavailable when another arrival needs the
room, and no evidence can establish that (availability is BLOCKED, G12a). An APPROVED decision
applies the hotel's policy; it does not claim the room is free, and its task says so.

ADVISORY, ALWAYS. A decision is a row in our store and, unless DENIED, a task a person performs.
Nothing here writes to a PMS and nothing posts the fee (G2(b) is rejected).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time

from ..actions import action_id_for
from ..kernel import EvidenceLine, Money
from .fee import charged_hours, fee_for

APPROVED = "APPROVED"
APPROVED_WITH_FEE = "APPROVED_WITH_FEE"
DENIED = "DENIED"
STAFF_REVIEW = "STAFF_REVIEW"
UNAVAILABLE = "UNAVAILABLE"
# D15's five, in the order the owner listed them.
DECISIONS = (APPROVED, APPROVED_WITH_FEE, DENIED, STAFF_REVIEW, UNAVAILABLE)

# THE TABLE AS THIS ENGINE IMPLEMENTS IT: (rule id, decision), in evaluation order. Compared with
# the approved file on every load. LC11 decides APPROVED instead when completed-hour rounding
# leaves nothing to charge - the file says so in that rule's own words.
RULES = (
    ("LC1-gaps", STAFF_REVIEW),
    ("LC2-cancelled", DENIED),
    ("LC3-checked-out", DENIED),
    ("LC4-stay-ended", DENIED),
    ("LC5-overstay", STAFF_REVIEW),
    ("LC6-not-today", STAFF_REVIEW),
    ("LC7-not-checked-in", STAFF_REVIEW),
    ("LC8-free", APPROVED),
    ("LC9-after-maximum", DENIED),
    ("LC10-needs-approval", STAFF_REVIEW),
    ("LC11-fee", APPROVED_WITH_FEE),
)

# What the rules read, by name. The template must declare exactly these (template.py).
PARAMETERS = ("free_until", "charge_from", "approval_required_after", "maximum_time",
              "fee_per_hour", "hour_rounding")
EVIDENCE_FIELDS = ("reservation.status", "reservation.departure_date")
# The canonical statuses (spec/canonical_fields.json). A status outside them is a gap, not a
# status this table can reason about.
STATUSES = frozenset({"confirmed", "checked_in", "checked_out", "cancelled", "waitlist",
                      "no_show"})


@dataclass(frozen=True, slots=True)
class Gap:
    """One thing a decision could not be made without: evidence, or a hotel decision."""

    name: str
    kind: str              # "evidence" | "parameter"
    reason: str

    @property
    def sentence(self) -> str:
        if self.name == "reservation":
            return self.reason
        if self.kind == "parameter":
            return "%s %s" % (self.name, self.reason)
        return "%s is not established (%s)" % (self.name, self.reason)


@dataclass(frozen=True, slots=True)
class Ruling:
    """What the table says: the decision, the rule that said it, and why.

    `fee` is the fee THIS decision applies, so it is set only on APPROVED_WITH_FEE. In the
    approval band (LC10) the would-be fee is in the reason, for the person deciding, and is not
    a fee: nothing is charged by a decision that has not been made.
    """

    decision: str
    rule: str
    reason: str
    fee: Money | None = None
    gaps: tuple[Gap, ...] = ()


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _hours(n: int) -> str:
    return "%d charged hour%s" % (n, "" if n == 1 else "s")


def decide(request, policy, evidence, today: date) -> Ruling:
    """The first rule in the table that matches, and nothing else. Pure."""
    # LC1 - every gap at once, before any rule that could decide without it.
    gaps = tuple(evidence.gaps()) + tuple(policy.gaps())
    if gaps:
        return Ruling(STAFF_REVIEW, "LC1-gaps",
                      "A person must decide: %s." % "; ".join(g.sentence for g in gaps),
                      gaps=gaps)

    status = evidence.status.payload
    departure = date.fromisoformat(evidence.departure_date.payload)     # checked by gaps()
    reservation = request.reservation_id

    if status == "cancelled":
        return Ruling(DENIED, "LC2-cancelled",
                      "Reservation %s is cancelled: there is no stay to extend." % reservation)
    if status == "checked_out":
        return Ruling(DENIED, "LC3-checked-out",
                      "The guest has already checked out of reservation %s." % reservation)
    if departure < today:
        if status != "checked_in":
            return Ruling(DENIED, "LC4-stay-ended",
                          "This stay ended on %s, so there is no checkout to extend."
                          % departure.isoformat())
        # Owner point 5: checked in AND departed yesterday cannot both be true. The guest has
        # overstayed, or the record lags - and a contradiction is not established evidence.
        return Ruling(STAFF_REVIEW, "LC5-overstay",
                      "The PMS shows the guest still checked in, but this stay ended on %s: the "
                      "two facts contradict each other, so a person must decide."
                      % departure.isoformat())
    if departure > today:
        return Ruling(STAFF_REVIEW, "LC6-not-today",
                      "This reservation departs on %s, not today (%s): a request ahead of the "
                      "day is for a person to decide." % (departure.isoformat(),
                                                          today.isoformat()))
    if status != "checked_in":
        # Owner point 4: ONLY a checked-in guest reaches the time rules. The draft caught
        # `confirmed` alone, and a waitlisted guest would have fallen through to APPROVED.
        return Ruling(STAFF_REVIEW, "LC7-not-checked-in",
                      "The guest is not checked in (the reservation is %s), so a person must "
                      "decide." % status)

    asked = request.requested_time
    if asked <= policy["free_until"]:
        return Ruling(APPROVED, "LC8-free",
                      "%s is within the free late checkout, until %s."
                      % (_hhmm(asked), _hhmm(policy["free_until"])))
    if asked > policy["maximum_time"]:
        return Ruling(DENIED, "LC9-after-maximum",
                      "%s is after the latest checkout this hotel grants, %s."
                      % (_hhmm(asked), _hhmm(policy["maximum_time"])))

    rate, start = policy["fee_per_hour"], policy["charge_from"]
    hours = charged_hours(start, asked, policy["hour_rounding"])
    fee = fee_for(rate, hours)
    if asked > policy["approval_required_after"]:
        would_be = ("the fee would be %s (%s from %s at %s per hour)"
                    % (fee, _hours(hours), _hhmm(start), rate) if fee is not None else
                    "no fee would be charged (%s from %s)" % (_hours(hours), _hhmm(start)))
        return Ruling(STAFF_REVIEW, "LC10-needs-approval",
                      "After %s a person must approve a late checkout; if approved, %s. "
                      "Nothing is charged by this decision."
                      % (_hhmm(policy["approval_required_after"]), would_be))
    if fee is None:
        return Ruling(APPROVED, "LC11-fee",
                      "%s is within the first hour after %s, and this hotel charges completed "
                      "hours only: no fee." % (_hhmm(asked), _hhmm(start)))
    return Ruling(APPROVED_WITH_FEE, "LC11-fee",
                  "%s is %s after %s at %s per hour: %s."
                  % (_hhmm(asked), _hours(hours), _hhmm(start), rate, fee), fee=fee)


# --------------------------------------------------------------------------- the record
@dataclass(frozen=True, slots=True)
class Decision:
    """A ruling, identified, versioned and attributed - what the store keeps and staff see."""

    decision_id: str
    tenant_id: str
    template_id: str
    template_name: str
    template_version: int
    template_digest: str
    parameters_digest: str
    reservation_id: str
    requested_time: time
    departure_date: str | None
    received_at: datetime
    received_on: date
    decision: str
    rule: str
    reason: str
    fee: Money | None
    gaps: tuple[Gap, ...]
    evidence: tuple[EvidenceLine, ...]
    provider: str
    evidence_label: str
    # The task this decision raises, from the table's `actions` block. All three are None for
    # DENIED, which raises none (owner point 3).
    severity: str | None
    audience: str | None
    action_id: str | None


def decision_id_for(*, tenant_id: str, template_id: str, template_version: int,
                    reservation_id: str, departure_date: str | None, requested_time: time,
                    received_on: date, parameters_digest: str) -> str:
    """The table's identity key, digested: the same request twice is one decision (D1 §65).

    `received_on` - the property's day the request arrived - is in it, so asking the day before
    and asking on the day are two questions with two answers; a double tap happens on one day.
    """
    seed = "|".join((tenant_id, template_id, str(template_version), reservation_id,
                     departure_date or "-", _hhmm(requested_time), received_on.isoformat(),
                     parameters_digest))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def make_decision(template, request, policy, evidence, ruling: Ruling, *, tenant_id: str,
                  received_at: datetime, provider: str, evidence_label: str,
                  received_on: date | None = None) -> Decision:
    """Attach identity, version and task routing to a ruling.

    `received_at` comes from the caller's injected clock. `received_on` is the property's day at
    that instant - pass the clock's `today()`; left out, it is the instant's own date, which is
    the property's day only when the instant is in the property's timezone (F11).
    """
    if received_at.tzinfo is None:
        raise ValueError("a decision's instant must carry its timezone: 'today' is the "
                         "property's day, and a naive instant has no day (F11)")
    if policy.tenant_id != tenant_id:
        raise ValueError("a decision for property %r cannot apply property %r's policy"
                         % (tenant_id, policy.tenant_id))
    departure = evidence.departure_date
    departure_date = departure.payload if departure.is_known and \
        isinstance(departure.payload, str) else None
    received_on = received_on or received_at.date()
    decision_id = decision_id_for(
        tenant_id=tenant_id, template_id=template.template_id,
        template_version=template.version, reservation_id=request.reservation_id,
        departure_date=departure_date, requested_time=request.requested_time,
        received_on=received_on, parameters_digest=policy.digest)
    action = template.actions.get(ruling.decision)
    return Decision(
        decision_id=decision_id, tenant_id=tenant_id, template_id=template.template_id,
        template_name=template.name, template_version=template.version,
        template_digest=template.digest, parameters_digest=policy.digest,
        reservation_id=request.reservation_id, requested_time=request.requested_time,
        departure_date=departure_date, received_at=received_at, received_on=received_on,
        decision=ruling.decision, rule=ruling.rule, reason=ruling.reason, fee=ruling.fee,
        gaps=ruling.gaps, evidence=evidence.lines(), provider=provider,
        evidence_label=evidence_label,
        severity=action["severity"] if action else None,
        audience=action.get("audience") if action else None,
        # The task's identity is slice 18's natural key with the decision as its record, so a
        # decision raises exactly one task however often it is submitted.
        action_id=(action_id_for(tenant_id=tenant_id, control_id=template.template_id,
                                 policy_version=template.version, record_id=decision_id)
                   if action else None))
