# -*- coding: utf-8 -*-
"""
Aggregate assertions - questions about a GROUP of records.

Some controls cannot be answered one record at a time. "Two active reservations must not share
the same OTA confirmation number" is not a property of a reservation; it is a property of a set
of them. v1 declared `count_lte` and `overlaps` in its schema, used them in two controls, and
implemented neither - so duplicate detection returned zero answers while the fixtures contained
a confirmed real duplicate pattern (review finding F2).

TWO GUARDS DECIDE WHETHER THIS IS USEFUL OR LIBELLOUS, AND BOTH TRACE TO R7
--------------------------------------------------------------------------
An OTA modification in this provider is a CANCEL PLUS A RECREATE reusing the same portal id.
And 7 of 11 sandbox bookings are direct, carrying no portal id at all.

  * Cancelled records must leave the population BEFORE grouping, or every modified booking is
    reported as a duplicate of itself.
  * Records with no key must never be grouped, or every direct booking becomes a duplicate of
    every other direct booking - one enormous false group.

Both are exercised below on the shapes the real capture contains.
"""
import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import Bundle
from hotelcontrols.kernel import NOT_APPLICABLE, Outcome, Value
from hotelcontrols.spec import ControlIR


def duplicate_ir(limit=1):
    return ControlIR({
        "control_id": "duplicates", "entity": "reservation",
        "scope": [{"field": "reservation.status", "operator": "not_equals",
                   "value": "cancelled"}],
        "exceptions": [{"field": "reservation.channel_confirmation_id",
                        "operator": "not_exists"}],
        "assertion": {"mode": "aggregate",
                      "group_by": "reservation.channel_confirmation_id",
                      "predicates": [{"field": "reservation.id", "operator": "count_lte",
                                      "value": limit}]},
        "required_evidence": [{"field": "reservation.id", "source": "pms"},
                              {"field": "reservation.status", "source": "pms"},
                              {"field": "reservation.channel_confirmation_id",
                               "source": "pms"}],
    })


def reservation(rid, portal, status="confirmed"):
    portal_value = (Value.known(NOT_APPLICABLE) if portal is None
                    else portal if isinstance(portal, Value) else Value.known(portal))
    status_value = status if isinstance(status, Value) else Value.known(status)
    return Bundle("reservation", rid, {
        "reservation.id": Value.known(rid),
        "reservation.status": status_value,
        "reservation.channel_confirmation_id": portal_value}, {}, {})


def by_id(verdicts):
    return {v.record_id: v for v in verdicts}


class TestCountLte:
    def test_two_active_reservations_sharing_a_confirmation_number_both_fail(self):
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("A", "OTA-1"), reservation("B", "OTA-1"),
            reservation("C", "OTA-2")]))
        assert verdicts["A"].outcome is Outcome.FAIL
        assert verdicts["B"].outcome is Outcome.FAIL
        assert verdicts["C"].outcome is Outcome.PASS

    def test_a_failing_verdict_names_the_other_records_in_its_group(self):
        """The slice gate. An accusation that does not say who else is involved cannot be
        acted on - the front-office manager has to open both reservations."""
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("A", "OTA-1"), reservation("B", "OTA-1")]))
        rendered = " ".join(str(line) for line in verdicts["A"].evidence)
        assert "B" in rendered
        assert "OTA-1" in verdicts["A"].reason or "OTA-1" in rendered

    def test_the_same_reservation_appearing_twice_is_not_a_duplicate_of_itself(self):
        """A reservation can appear more than once in a population - several room stays, or a
        provider that repeats it. Counting rows rather than DISTINCT reservations would report
        every multi-room booking as a duplicate."""
        verdicts = evaluate_population(duplicate_ir(), [
            reservation("A", "OTA-1"), reservation("A", "OTA-1")])
        assert all(v.outcome is Outcome.PASS for v in verdicts)

    def test_a_higher_limit_permits_a_larger_group(self):
        verdicts = evaluate_population(duplicate_ir(limit=2), [
            reservation("A", "OTA-1"), reservation("B", "OTA-1")])
        assert all(v.outcome is Outcome.PASS for v in verdicts)


class TestTheTwoR7Guards:
    def test_cancelled_records_leave_before_grouping(self):
        """R7. An OTA modification is a cancel plus a recreate reusing the same portal id, so
        the cancelled half must not be counted - otherwise every modified booking in the
        property is reported as a duplicate of itself."""
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("OLD", "OTA-1", status="cancelled"),
            reservation("NEW", "OTA-1")]))
        assert verdicts["OLD"].outcome is Outcome.EXCLUDED
        assert verdicts["NEW"].outcome is Outcome.PASS, (
            "the surviving half of a modification is not a duplicate")

    def test_records_with_no_confirmation_number_are_never_grouped_together(self):
        """R7, the other half. 7 of 11 sandbox bookings are direct and carry no portal id at
        all. Grouping them on a shared absence would produce one enormous false group in which
        every direct booking is a duplicate of every other."""
        verdicts = evaluate_population(duplicate_ir(), [
            reservation("D1", None), reservation("D2", None), reservation("D3", None)])
        assert all(v.outcome is Outcome.EXCLUDED for v in verdicts)
        assert all("exception applies" in v.reason for v in verdicts)

    def test_a_direct_booking_never_joins_a_real_group(self):
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("D1", None), reservation("A", "OTA-1"), reservation("B", "OTA-1")]))
        assert verdicts["D1"].outcome is Outcome.EXCLUDED
        assert verdicts["A"].outcome is Outcome.FAIL


class TestUnknownsDoNotCorruptOtherRecords:
    def test_a_record_whose_key_is_unknown_is_unknown_alone(self):
        """It must not join a group it might belong to, and it must not make its neighbours
        unknown either. One record's gap is one record's verdict."""
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("X", Value.unknown("the portal id could not be read")),
            reservation("A", "OTA-1"), reservation("B", "OTA-1")]))
        assert verdicts["X"].outcome is Outcome.UNKNOWN
        assert verdicts["A"].outcome is Outcome.FAIL

    def test_a_record_whose_scope_is_unknown_never_reaches_the_group(self):
        """A5. One reservation in five carries a status this engine refuses to name, so a
        control cannot tell whether it even applies - and an uncounted record must not silently
        make a group look smaller than it is."""
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("U", "OTA-1", status=Value.unknown("'OK4' is not in the status map",
                                                           risk="A5")),
            reservation("A", "OTA-1")]))
        assert verdicts["U"].outcome is Outcome.UNKNOWN
        # A is alone among records we could establish, so it passes - but the verdict has to
        # admit that a record we could not read shares its key.
        assert verdicts["A"].outcome in (Outcome.PASS, Outcome.UNKNOWN)

    def test_a_group_whose_membership_is_uncertain_says_so(self):
        """The honest answer when an unreadable record shares a key: we cannot say this
        reservation is unique, because we could not read the one next to it."""
        verdicts = by_id(evaluate_population(duplicate_ir(), [
            reservation("U", "OTA-1", status=Value.unknown("unmappable status", risk="A5")),
            reservation("A", "OTA-1")]))
        assert verdicts["A"].outcome is Outcome.UNKNOWN
        assert "could not be established" in verdicts["A"].reason.lower() \
            or "not established" in verdicts["A"].reason.lower()


class TestNoOverlap:
    """Control 20: a room's occupancy must be consistent with the reservations on it."""

    @staticmethod
    def occupancy_ir():
        return ControlIR({
            "control_id": "occupancy", "entity": "occupancy",
            "scope": [{"field": "occupancy.status", "operator": "not_equals",
                       "value": "cancelled"}],
            "exceptions": [],
            "assertion": {"mode": "aggregate", "group_by": "occupancy.room_number",
                          "predicates": [{"field": "occupancy.reservation_id",
                                          "operator": "no_overlap",
                                          "interval": {"start": "occupancy.from",
                                                       "end": "occupancy.to"}}]},
            "required_evidence": [{"field": f, "source": "pms"} for f in (
                "occupancy.room_number", "occupancy.reservation_id", "occupancy.from",
                "occupancy.to", "occupancy.status")],
        })

    @staticmethod
    def segment(rid, room, start, end, status="confirmed"):
        return Bundle("occupancy", rid, {
            "occupancy.reservation_id": Value.known(rid),
            "occupancy.room_number": Value.known(room),
            "occupancy.from": Value.known(start, unit="date"),
            "occupancy.to": Value.known(end, unit="date"),
            "occupancy.status": Value.known(status)}, {}, {})

    def test_two_reservations_double_booked_on_one_room_both_fail(self):
        verdicts = by_id(evaluate_population(self.occupancy_ir(), [
            self.segment("A", "303", "2026-07-08", "2026-07-12"),
            self.segment("B", "303", "2026-07-10", "2026-07-14")]))
        assert verdicts["A"].outcome is Outcome.FAIL
        assert verdicts["B"].outcome is Outcome.FAIL

    def test_back_to_back_bookings_on_one_room_pass(self):
        """The room is vacated and re-let the same day. Counting the end inclusively would
        report a violation on every back-to-back booking in the property."""
        verdicts = evaluate_population(self.occupancy_ir(), [
            self.segment("A", "303", "2026-07-08", "2026-07-11"),
            self.segment("B", "303", "2026-07-11", "2026-07-14")])
        assert all(v.outcome is Outcome.PASS for v in verdicts)

    def test_one_reservation_with_two_segments_does_not_conflict_with_itself(self):
        """Reservation 007003204 appears twice on room 303 in the capture. A reservation
        cannot double-book itself, and reporting that would be the first thing anybody saw."""
        verdicts = evaluate_population(self.occupancy_ir(), [
            self.segment("007003204", "303", "2024-08-10", "2024-08-16"),
            self.segment("007003204", "303", "2024-08-12", "2024-08-18")])
        assert all(v.outcome is Outcome.PASS for v in verdicts)

    def test_overlapping_stays_in_different_rooms_are_not_a_conflict(self):
        verdicts = evaluate_population(self.occupancy_ir(), [
            self.segment("A", "303", "2026-07-08", "2026-07-12"),
            self.segment("B", "304", "2026-07-08", "2026-07-12")])
        assert all(v.outcome is Outcome.PASS for v in verdicts)

    def test_a_segment_with_an_unreadable_date_is_unknown_not_a_conflict(self):
        verdicts = by_id(evaluate_population(self.occupancy_ir(), [
            Bundle("occupancy", "A", {
                "occupancy.reservation_id": Value.known("A"),
                "occupancy.room_number": Value.known("303"),
                "occupancy.from": Value.unknown("unparseable date", risk="R2"),
                "occupancy.to": Value.known("2026-07-12", unit="date"),
                "occupancy.status": Value.known("confirmed")}, {}, {}),
            self.segment("B", "303", "2026-07-10", "2026-07-14")]))
        assert verdicts["A"].outcome is Outcome.UNKNOWN
        assert verdicts["B"].outcome is not Outcome.FAIL, (
            "B cannot be convicted on a segment we could not read")


class TestNonAggregateControlsAreUntouched:
    def test_a_record_level_control_is_evaluated_record_by_record(self):
        """`evaluate_population` is the single entry point a runner calls, so it has to hand
        non-aggregate controls straight to the record evaluator."""
        from hotelcontrols.kernel import Money
        ir = ControlIR({
            "control_id": "balance", "entity": "reservation", "scope": [], "exceptions": [],
            "assertion": {"mode": "all", "predicates": [
                {"field": "folio.balance_due", "operator": "lte", "value": 0}]},
            "required_evidence": [{"field": "folio.balance_due", "source": "pms"}]})
        bundles = [
            Bundle("reservation", "A",
                   {"folio.balance_due": Value.known(Money.parse("0", "ILS"))}, {}, {}),
            Bundle("reservation", "B",
                   {"folio.balance_due": Value.known(Money.parse("812.5", "ILS"))}, {}, {})]
        verdicts = by_id(evaluate_population(ir, bundles))
        assert verdicts["A"].outcome is Outcome.PASS
        assert verdicts["B"].outcome is Outcome.FAIL
