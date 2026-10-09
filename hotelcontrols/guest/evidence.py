# -*- coding: utf-8 -*-
"""
EVIDENCE - one reservation's status and departure date, through the existing evidence layer.

    look_up(template, reservation_id, adapter, tenant, clock, budget) -> ReservationEvidence

D2 §30's template needs two facts, `reservation.status` and `reservation.departure_date`, and
asks them through `evidence.gather` - by import, unchanged - so both providers answer the same
canonical question the way every control does (criterion 7, applied to a decision). The
template's population is carried as data, per provider, exactly like an IR's: this module hands
it to `gather` and never reads it, so no endpoint, filter or vendor name appears here (the
canonical-boundary test walks this package too).

ONE CALL, NOT ONE PER RESERVATION (R1). No captured endpoint answers for a single reservation,
so the template asks for the reservations departing yesterday, today or tomorrow - one bulk call
- and picks the guest's out of it. The window is what lets the stay-ended, overstay and
departs-another-day rules be decided from evidence rather than from absence.

EVERY WAY THIS CAN FAIL IS A GAP, NEVER A DECISION. A reservation outside the window, a lookup
the capture cannot answer, a budget exhausted, two records with one id: each becomes evidence
that is not established, with its reason, and the decision is STAFF_REVIEW naming it (LC1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..evidence import BudgetExceeded, CallBudget, gather
from ..kernel import Clock, EvidenceLine, Value
from ..providers.base import ProviderError
from ..spec import ControlIR, TenantConfig
from .decision import EVIDENCE_FIELDS, STATUSES, Gap

_RELATIVE = re.compile(r"^today(?:([+-])(\d+)d)?$")


@dataclass(frozen=True, slots=True)
class ReservationEvidence:
    """What the PMS said about one reservation - each fact a `Value`, known or reasoned.

    `absent` is set when the reservation itself could not be established (not found, or the
    lookup failed): then neither field is about anything, and the one gap is the reservation.
    """

    reservation_id: str
    status: Value
    departure_date: Value
    absent: str | None = None
    # Provider calls this lookup spent - accounting, not evidence, so not part of equality.
    calls: int = field(default=0, compare=False)

    @classmethod
    def missing(cls, reservation_id: str, reason: str, calls: int = 0) -> ReservationEvidence:
        gone = Value.unknown(reason)
        return cls(reservation_id, status=gone, departure_date=gone, absent=reason, calls=calls)

    def lines(self) -> tuple[EvidenceLine, ...]:
        """The evidence table a decision carries, in the template's field order."""
        return (EvidenceLine("reservation.status", self.status),
                EvidenceLine("reservation.departure_date", self.departure_date))

    def gaps(self) -> tuple[Gap, ...]:
        """Every fact the decision cannot be made without, with its own reason."""
        if self.absent is not None:
            return (Gap("reservation", "evidence", self.absent),)
        gaps = []
        if not self.status.is_known:
            gaps.append(Gap("reservation.status", "evidence", self.status.reason))
        elif self.status.payload not in STATUSES:
            # A canonical status is one of six. Anything else reaching here is a status this
            # table cannot reason about, and guessing which one it resembles is the error.
            gaps.append(Gap("reservation.status", "evidence",
                            "%r is not a status this template knows" % (self.status.payload,)))
        if not self.departure_date.is_known:
            gaps.append(Gap("reservation.departure_date", "evidence",
                            self.departure_date.reason))
        elif not _is_date(self.departure_date.payload):
            gaps.append(Gap("reservation.departure_date", "evidence",
                            "%r is not a date this template can read"
                            % (self.departure_date.payload,)))
        return tuple(gaps)


def _is_date(payload) -> bool:
    try:
        date.fromisoformat(payload)
    except (TypeError, ValueError):
        return False
    return True


def window(template, today: date) -> tuple[date, date]:
    """The days the template's population covers, from its own declared `window` tokens - the
    same tokens each provider's query carries (pinned by a test), resolved on the property's
    calendar. Only to SAY which days were looked at; the query itself is never read here."""
    bounds = []
    for token in (template.population["window"]["from"], template.population["window"]["to"]):
        match = _RELATIVE.match(token)
        if match is None:
            raise ValueError("unrecognised relative date %r in the template's window" % token)
        sign, days = match.groups()
        bounds.append(today + timedelta(days=int(days or 0) * (-1 if sign == "-" else 1)))
    return bounds[0], bounds[1]


def look_up(template, reservation_id: str, adapter, tenant: TenantConfig, clock: Clock,
            budget: CallBudget | None = None) -> ReservationEvidence:
    """The reservation's two facts, or a reasoned admission that they could not be had."""
    budget = budget or CallBudget(tenant.call_budget)
    if adapter.name not in template.population["provider_query"]:
        return ReservationEvidence.missing(
            reservation_id, "this template declares no way to look a reservation up on this "
            "property's provider, so nothing about it can be established")

    # A rule-shaped view of the template, so `gather` - unchanged - can read it. Not a control:
    # it has no assertion and is never run, stored or counted as one.
    view = ControlIR({"control_id": template.template_id, "entity": "reservation",
                      "population": template.population,
                      "required_evidence": [{"field": name} for name in EVIDENCE_FIELDS]})
    try:
        evidence = gather(view, adapter, tenant, clock, budget)
    except BudgetExceeded as exc:
        return ReservationEvidence.missing(
            reservation_id, "the reservation could not be looked up within this property's call "
            "budget (%s)" % exc, calls=budget.spent)
    except ProviderError as exc:
        return ReservationEvidence.missing(
            reservation_id, "the reservation could not be looked up: %s" % exc,
            calls=budget.spent)

    matches = [bundle for bundle in evidence.bundles if bundle.record_id == reservation_id]
    if not matches:
        first, last = window(template, clock.today())
        return ReservationEvidence.missing(
            reservation_id, "reservation %s was not found among the reservations departing "
            "%s to %s in this body of evidence" % (reservation_id, first.isoformat(),
                                                   last.isoformat()), calls=budget.spent)
    if len(matches) > 1:
        return ReservationEvidence.missing(
            reservation_id, "reservation %s appears %d times in this body of evidence, so "
            "which record the request means cannot be said" % (reservation_id, len(matches)),
            calls=budget.spent)
    (bundle,) = matches
    return ReservationEvidence(reservation_id,
                               status=bundle.fields["reservation.status"],
                               departure_date=bundle.fields["reservation.departure_date"],
                               calls=budget.spent)
