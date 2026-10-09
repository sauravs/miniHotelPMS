# -*- coding: utf-8 -*-
"""
Slice 22 (G1 narrowed, G3a): the LATE_CHECKOUT decision table, rule by rule, with no provider.

`decide(request, policy, evidence, today)` is pure, so every rule in `spec/guest/late_checkout.json`
is exercised here against evidence built by hand - including evidence no capture holds (a
waitlisted guest, a guest still checked in after the stay ended). The same table against REAL
evidence, through both providers, is `tests/integration/test_guest_requests.py`.

What these protect:
  - V9: D2 §49's Definition of Done - 15:00 is APPROVED_WITH_FEE 25.00 USD as Money, and both
    sides of both thresholds (14:00, 14:01, 16:00, 16:01). D2 §1's policy as a second property.
  - V10: guest services never widens a decision. Blanking any single piece of evidence or any
    single parameter gives STAFF_REVIEW naming it - never APPROVED, DENIED or UNAVAILABLE.
  - D15: DENIED only from established evidence or stated policy; UNAVAILABLE never in v3.
  - The owner's five answers at the checkpoint (the file's `approval.answers`).
"""
from datetime import date, time
from decimal import Decimal

import pytest

from hotelcontrols.guest import (APPROVED, APPROVED_WITH_FEE, DENIED, STAFF_REVIEW, UNAVAILABLE,
                                 GuestRequest, Policy, ReservationEvidence, decide, load_template)
from hotelcontrols.kernel import Money, Value

TODAY = date(2026, 7, 8)
TEMPLATE = load_template()

# The two worked examples in the approved table, as test properties (never shipped tenants).
D2_49 = {"free_until": time(14, 0), "charge_from": time(14, 0),
         "approval_required_after": time(16, 0), "maximum_time": time(18, 0),
         "fee_per_hour": Money.parse("25.00", "USD"), "hour_rounding": "started_hour"}
D2_1 = {"free_until": time(12, 0), "charge_from": time(12, 0),
        "approval_required_after": time(15, 0), "maximum_time": time(15, 0),
        "fee_per_hour": Money.parse("25.00", "USD"), "hour_rounding": "started_hour"}


def policy(**overrides):
    values = dict(D2_49)
    values.update(overrides)
    return Policy(tenant_id="test_d2_49", values=values)


def checked_in(departure=TODAY, status="checked_in", reservation_id="007004343"):
    return ReservationEvidence(
        reservation_id=reservation_id,
        status=Value.known(status, source="pms:test/reservations"),
        departure_date=Value.known(departure.isoformat(), source="pms:test/reservations"))


def ask(at, reservation_id="007004343"):
    hour, minute = at.split(":")
    return GuestRequest(reservation_id=reservation_id, requested_time=time(int(hour), int(minute)))


def ruling(at, *, evidence=None, values=None):
    return decide(ask(at), values or policy(), evidence or checked_in(), TODAY)


# --------------------------------------------------------------------------- V9, D2 §49
class TestTheDefinitionOfDone:
    """D2 §49, made executable: free until 14:00, 25.00 USD per started hour from 14:00,
    approval after 16:00 (and, for the test property, nothing after 18:00)."""

    def test_three_pm_is_approved_with_a_fee_of_25_usd_as_money(self):
        """The exit test's headline case, exactly as plan-v3 §5 states it."""
        result = ruling("15:00")
        assert result.decision == APPROVED_WITH_FEE
        assert result.fee == Money(Decimal("25.00"), "USD")
        assert isinstance(result.fee, Money)
        assert str(result.fee) == "25.00 USD"
        assert result.rule == "LC11-fee"

    @pytest.mark.parametrize("at, decision, fee, rule", [
        ("14:00", APPROVED, None, "LC8-free"),               # the free threshold, inclusive
        ("14:01", APPROVED_WITH_FEE, "25.00", "LC11-fee"),   # one minute past it: a started hour
        ("16:00", APPROVED_WITH_FEE, "50.00", "LC11-fee"),   # the approval threshold, inclusive
        ("16:01", STAFF_REVIEW, None, "LC10-needs-approval"),  # past it: a person decides
        ("18:00", STAFF_REVIEW, None, "LC10-needs-approval"),
        ("18:01", DENIED, None, "LC9-after-maximum"),        # owner point 1
    ])
    def test_both_sides_of_both_thresholds(self, at, decision, fee, rule):
        result = ruling(at)
        assert (result.decision, result.rule) == (decision, rule)
        assert result.fee == (Money.parse(fee, "USD") if fee else None)

    def test_a_staff_review_after_the_approval_threshold_shows_the_fee_it_would_be(self):
        """LC10: the fee is computed and shown so the person approving sees it - in the
        reason, and not as the decision's fee, because nothing is charged by this decision."""
        result = ruling("16:01")
        assert "16:00" in result.reason and "75.00 USD" in result.reason
        assert result.fee is None
        assert "100.00 USD" in ruling("18:00").reason

    def test_an_approved_fee_names_the_hours_the_start_and_the_rate(self):
        reason = ruling("16:00").reason
        assert "2 charged hours" in reason and "14:00" in reason and "25.00 USD" in reason


class TestTheOtherWorkedExample:
    """D2 §1: 'Guests can request late checkout up to 3 PM. After noon, charge $25 per hour.'
    A second property's parameters with its own answers - plan-v3 §6 contradiction #3,
    dissolved rather than ruled."""

    @pytest.mark.parametrize("at, decision, fee", [
        ("12:00", APPROVED, None),
        ("12:01", APPROVED_WITH_FEE, "25.00"),
        ("15:00", APPROVED_WITH_FEE, "75.00"),
        ("15:01", DENIED, None),
    ])
    def test_up_to_three_charged_after_noon(self, at, decision, fee):
        result = ruling(at, values=Policy(tenant_id="test_d2_1", values=dict(D2_1)))
        assert result.decision == decision
        assert result.fee == (Money.parse(fee, "USD") if fee else None)

    def test_with_no_approval_band_a_request_after_the_maximum_is_denied_not_reviewed(self):
        """approval_required_after == maximum_time is a tie the table allows: no approval
        band. LC9 is checked before LC10, so 15:01 is the stated maximum, declined."""
        result = ruling("15:01", values=Policy(tenant_id="test_d2_1", values=dict(D2_1)))
        assert result.rule == "LC9-after-maximum"


class TestCompletedHourRounding:
    def test_a_part_hour_is_not_charged(self):
        result = ruling("14:59", values=policy(hour_rounding="completed_hour"))
        assert result.decision == APPROVED and result.fee is None
        assert result.rule == "LC11-fee"          # the fee rule decided it, and says so
        assert "completed" in result.reason

    def test_completed_hours_are_charged(self):
        result = ruling("16:00", values=policy(hour_rounding="completed_hour"))
        assert (result.decision, result.fee) == (APPROVED_WITH_FEE, Money.parse("50.00", "USD"))


# --------------------------------------------------------------------------- established evidence
class TestEstablishedEvidence:

    def test_a_cancelled_reservation_is_denied(self):
        result = ruling("15:00", evidence=checked_in(status="cancelled"))
        assert (result.decision, result.rule) == (DENIED, "LC2-cancelled")

    def test_a_guest_who_checked_out_is_denied(self):
        result = ruling("15:00", evidence=checked_in(status="checked_out"))
        assert (result.decision, result.rule) == (DENIED, "LC3-checked-out")

    @pytest.mark.parametrize("status", ["confirmed", "waitlist", "no_show"])
    def test_a_stay_that_ended_is_denied_when_the_guest_is_not_in_house(self, status):
        result = ruling("15:00", evidence=checked_in(date(2026, 7, 7), status=status))
        assert (result.decision, result.rule) == (DENIED, "LC4-stay-ended")
        assert "2026-07-07" in result.reason

    def test_a_guest_still_checked_in_after_the_stay_ended_is_a_contradiction_for_a_person(self):
        """Owner point 5. The draft would have DENIED this. Checked in AND departed yesterday
        are two facts that contradict each other, and D15 lets DENIED come only from
        established evidence."""
        result = ruling("15:00", evidence=checked_in(date(2026, 7, 7)))
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC5-overstay")
        assert "still checked in" in result.reason and "2026-07-07" in result.reason

    def test_a_request_ahead_of_the_day_is_for_a_person(self):
        """Owner point 2: asking ahead breaks no rule, so it is not DENIED."""
        result = ruling("15:00", evidence=checked_in(date(2026, 7, 9)))
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC6-not-today")
        assert "2026-07-09" in result.reason

    @pytest.mark.parametrize("status", ["confirmed", "waitlist", "no_show"])
    def test_only_a_checked_in_guest_reaches_the_time_rules(self, status):
        """Owner point 4. The draft caught `confirmed` alone, so `waitlist` and `no_show`
        would have fallen through to LC8 and been APPROVED for a guest who never arrived."""
        result = ruling("12:00", evidence=checked_in(status=status))
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC7-not-checked-in")
        assert status in result.reason


# --------------------------------------------------------------------------- V10
class TestNeverWidened:
    """V10: blanking any single piece of evidence or any single parameter gives STAFF_REVIEW
    naming it. Asked at every time the worked example decides differently, so a gap is shown to
    outrank APPROVED, APPROVED_WITH_FEE, DENIED and the review band alike."""

    TIMES = ("12:00", "14:00", "15:00", "16:01", "18:01")

    @pytest.mark.parametrize("at", TIMES)
    @pytest.mark.parametrize("field", ["reservation.status", "reservation.departure_date"])
    def test_blanking_one_piece_of_evidence(self, field, at):
        values = {"status": Value.known("checked_in"),
                  "departure_date": Value.known(TODAY.isoformat())}
        values[field.split(".")[1]] = Value.unknown("blanked by the test", source="pms:test/x")
        evidence = ReservationEvidence(reservation_id="007004343", **values)
        result = ruling(at, evidence=evidence)
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC1-gaps")
        assert field in result.reason and "blanked by the test" in result.reason
        assert [gap.name for gap in result.gaps] == [field]
        assert result.fee is None

    @pytest.mark.parametrize("at", TIMES)
    @pytest.mark.parametrize("parameter", sorted(D2_49))
    def test_blanking_one_parameter(self, parameter, at):
        result = ruling(at, values=policy(**{parameter: None}))
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC1-gaps")
        assert parameter in result.reason
        assert [gap.name for gap in result.gaps] == [parameter]
        assert result.fee is None

    @pytest.mark.parametrize("status", ["cancelled", "checked_out"])
    def test_a_gap_outranks_a_denial_that_could_have_been_made_without_it(self, status):
        """LC1 is checked FIRST. A cancelled reservation with an undecided fee is still a
        STAFF_REVIEW: the table says a gap can never be outranked."""
        result = ruling("15:00", evidence=checked_in(status=status),
                        values=policy(fee_per_hour=None))
        assert result.decision == STAFF_REVIEW and "fee_per_hour" in result.reason

    def test_every_gap_is_named_at_once(self):
        evidence = ReservationEvidence(
            reservation_id="007004258",
            status=Value.unknown("'OK4' is not in this property's status map"),
            departure_date=Value.known(TODAY.isoformat()))
        undecided = Policy(tenant_id="sandbox", values={name: None for name in D2_49})
        result = decide(ask("15:00", "007004258"), undecided, evidence, TODAY)
        assert [gap.name for gap in result.gaps] == [
            "reservation.status", "free_until", "charge_from", "approval_required_after",
            "maximum_time", "fee_per_hour", "hour_rounding"]
        assert "OK4" in result.reason

    def test_a_reservation_that_was_not_found_is_a_gap_and_not_a_denial(self):
        evidence = ReservationEvidence.missing("123", "reservation 123 was not found")
        result = decide(ask("15:00", "123"), policy(), evidence, TODAY)
        assert (result.decision, result.rule) == (STAFF_REVIEW, "LC1-gaps")
        assert [gap.name for gap in result.gaps] == ["reservation"]
        assert "was not found" in result.reason

    def test_an_unreadable_departure_date_is_a_gap(self):
        evidence = ReservationEvidence(reservation_id="1", status=Value.known("checked_in"),
                                       departure_date=Value.known("08/07/2026"))
        result = decide(ask("15:00", "1"), policy(), evidence, TODAY)
        assert result.decision == STAFF_REVIEW and "reservation.departure_date" in result.reason

    def test_a_status_the_template_does_not_know_is_a_gap(self):
        evidence = checked_in(status="in_limbo")
        result = ruling("12:00", evidence=evidence)
        assert result.decision == STAFF_REVIEW and "in_limbo" in result.reason

    def test_unavailable_is_never_reached(self):
        """G12a: no evidence can establish that another arrival needs the room, so the table
        declares UNAVAILABLE unreachable in v3. Swept over every minute of the day and every
        status, for both worked examples."""
        seen = set()
        for values in (policy(), Policy(tenant_id="b", values=dict(D2_1))):
            for status in ("confirmed", "checked_in", "checked_out", "cancelled", "waitlist",
                           "no_show"):
                for departure in (date(2026, 7, 7), TODAY, date(2026, 7, 9)):
                    for minute in range(0, 24 * 60, 7):
                        result = decide(GuestRequest("1", time(minute // 60, minute % 60)),
                                        values, checked_in(departure, status), TODAY)
                        seen.add(result.decision)
        assert UNAVAILABLE not in seen
        assert seen == {APPROVED, APPROVED_WITH_FEE, DENIED, STAFF_REVIEW}


class TestEveryDecisionNamesItsRule:

    def test_the_rule_is_one_of_the_tables(self):
        ids = [rule["rule"] for rule in TEMPLATE.raw["rules"]]
        for at in ("12:00", "14:30", "16:30", "19:00"):
            assert ruling(at).rule in ids

    def test_a_decision_always_has_a_reason(self):
        for at in ("00:00", "12:00", "14:30", "16:30", "23:59"):
            assert ruling(at).reason.strip()
