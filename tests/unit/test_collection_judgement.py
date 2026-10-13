# -*- coding: utf-8 -*-
"""
A collection judged record by record - issue #109 (#87's option 2), design points P1 and P3.

P1. A predicate reading a field of a `collection` reference - a room's occupancy segments - is
judged once PER RELATED RECORD, and only in an assertion of mode `none` ("no related record may
satisfy any predicate"). FAIL if any record satisfies one; else UNKNOWN if any could not be
judged; else PASS - but only if the collection is complete for the question (P3).

P3. The evidence layer records the window each collection was fetched for, and the day it was
asked on. A room PASSes only if the part of its question from that day onward lies inside the
window; an overlap seen inside it is FAIL whatever lies beyond; otherwise UNKNOWN, naming the
dates nobody looked at. An open-ended closure can FAIL and never PASS. A reference that could
not be fetched, or a key that could not be read, is UNKNOWN - never an empty collection read as
"no guests", which would be a widened PASS (CLAUDE.md: never widen a verdict).

Every bundle here is built by hand, so each test is about the evaluator and nothing else. The
dates are the refresh capture's: occupancy fetched for 2026-07-08..15 on 2026-07-08, and room
303's real segments (007004344 on 08..09, 007004367 from the 10th).
"""
import pytest

from hotelcontrols.evaluator import evaluate_record
from hotelcontrols.evidence import Bundle, FetchedWindow
from hotelcontrols.kernel import Outcome, Value
from hotelcontrols.spec import ControlIR

WINDOW = FetchedWindow("2026-07-08", "2026-07-15", "2026-07-08")

OVERLAP = [
    {"field": "occupancy.from", "operator": "within",
     "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
    {"field": "room.closed_from", "operator": "within",
     "interval": {"start": "occupancy.from", "end": "occupancy.to"}},
]


def rule(predicates=None, mode="none"):
    return ControlIR({
        "control_id": "t", "entity": "room",
        "references": [{"entity": "occupancy", "kind": "collection",
                        "local_field": "room.number", "remote_field": "occupancy.room_number"}],
        "scope": [], "exceptions": [],
        "assertion": {"mode": mode, "predicates": predicates or OVERLAP},
        "required_evidence": [{"field": f, "source": "pms"} for f in (
            "room.number", "room.closed_from", "room.closed_to", "occupancy.room_number",
            "occupancy.reservation_id", "occupancy.from", "occupancy.to")]})


def day(text):
    return Value.known(text, unit="date")


def segment(reservation, start, end, room="303"):
    return {"occupancy.room_number": Value.known(room),
            "occupancy.reservation_id": Value.known(reservation),
            "occupancy.from": day(start), "occupancy.to": day(end)}


FIRST = segment("007004344", "2026-07-08", "2026-07-09")
INSIDE = segment("007004367", "2026-07-10", "2026-07-11")


def room(closed_from="2026-07-10", closed_to="2026-07-13", segments=(), join=None,
         window=WINDOW, unplaced=()):
    def bound(text):
        return Value.known(False) if text is None else day(text)
    collection = "a collection: each record is judged on its own"
    fields = {"room.number": Value.known("303"), "room.closed_from": bound(closed_from),
              "room.closed_to": bound(closed_to),
              # What the evidence layer leaves on the room itself for a collection's fields:
              # no single value, because no one record stands for the rest (#87).
              "occupancy.room_number": Value.unknown(collection),
              "occupancy.reservation_id": Value.unknown(collection),
              "occupancy.from": Value.unknown(collection),
              "occupancy.to": Value.unknown(collection)}
    joins = {"occupancy": join if join is not None else Value.known(bool(segments))}
    return Bundle("room", "303", fields, {"occupancy": tuple(segments)}, joins,
                  windows={"occupancy": window} if window else {},
                  unplaced={"occupancy": tuple(unplaced)} if unplaced else {})


def judge(bundle, predicates=None, mode="none"):
    return evaluate_record(rule(predicates, mode), bundle)


def line(verdict, name):
    return next(e for e in verdict.evidence if e.field == name)


class TestEveryRecordIsJudged:

    def test_a_guest_behind_a_clean_first_segment_is_a_fail(self):
        """#87 itself. Version 2 read the first segment only and PASSed this room."""
        verdict = judge(room(segments=(FIRST, INSIDE)))
        assert verdict.outcome is Outcome.FAIL, verdict

    def test_the_fail_names_the_segment_that_decided_it(self):
        verdict = judge(room(segments=(FIRST, INSIDE)))
        assert "007004367" in verdict.reason and "2 of 2" in verdict.reason, verdict.reason
        assert "007004344" not in verdict.reason, "the clean segment decided nothing"

    def test_the_evidence_table_shows_the_deciding_segment_not_the_first(self):
        verdict = judge(room(segments=(FIRST, INSIDE)))
        assert line(verdict, "occupancy.from").value.payload == "2026-07-10"
        assert line(verdict, "occupancy.reservation_id").value.payload == "007004367"

    def test_a_window_opening_during_a_stay_is_a_fail(self):
        """The second predicate: a guest already in the room when it closes."""
        staying = segment("007004259", "2026-07-04", "2026-07-12")
        verdict = judge(room(closed_from="2026-07-09", closed_to="2026-07-10",
                             segments=(staying,)))
        assert verdict.outcome is Outcome.FAIL, verdict
        assert "007004259" in verdict.reason

    def test_an_overlap_seen_inside_the_window_fails_whatever_lies_beyond_it(self):
        """Closed 10..20, fetched to the 15th: a guest on the 10th is a violation now, and
        what the 16th..20th hold cannot change that."""
        verdict = judge(room(closed_to="2026-07-20", segments=(FIRST, INSIDE)))
        assert verdict.outcome is Outcome.FAIL, verdict

    def test_an_open_ended_closure_can_fail(self):
        verdict = judge(room(closed_to=None, segments=(FIRST, INSIDE)))
        assert verdict.outcome is Outcome.FAIL, verdict

    def test_a_record_that_cannot_be_judged_makes_the_room_unknown(self):
        blind = dict(FIRST, **{"occupancy.from": Value.unknown("segment start unreadable")})
        verdict = judge(room(segments=(blind,)))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "segment start unreadable" in verdict.reason

    def test_a_definite_overlap_outranks_a_record_that_cannot_be_judged(self):
        """Kleene `none`: one True is a complete answer, as it is across predicates."""
        blind = dict(FIRST, **{"occupancy.from": Value.unknown("segment start unreadable")})
        verdict = judge(room(segments=(blind, INSIDE)))
        assert verdict.outcome is Outcome.FAIL, verdict

    def test_judging_does_not_change_the_bundle(self):
        bundle = room(segments=(FIRST, INSIDE))
        before = dict(bundle.fields)
        judge(bundle)
        assert bundle.fields == before


class TestAPassNeedsACompleteCollection:

    def test_no_overlap_inside_a_covered_window_is_a_pass(self):
        verdict = judge(room(closed_from="2026-07-14", closed_to="2026-07-15",
                             segments=(FIRST, INSIDE)))
        assert verdict.outcome is Outcome.PASS, verdict
        assert "2 " in verdict.reason and "2026-07-08..2026-07-15" in verdict.reason, \
            verdict.reason

    def test_a_room_with_no_segments_in_a_covered_window_is_a_pass(self):
        """The join was READ and matched nothing: known(False), a definite absence."""
        verdict = judge(room(segments=(), join=Value.known(False)))
        assert verdict.outcome is Outcome.PASS, verdict

    def test_a_pass_shows_no_single_segment_as_its_evidence(self):
        """A PASS is about every segment. Showing one - the first - is #87's display."""
        verdict = judge(room(closed_from="2026-07-14", closed_to="2026-07-15",
                             segments=(FIRST, INSIDE)))
        assert not any(e.field.startswith("occupancy.") for e in verdict.evidence), \
            verdict.evidence

    def test_a_closure_beyond_the_window_is_unknown_naming_the_dates(self):
        verdict = judge(room(closed_from="2026-07-16", closed_to="2026-07-20"))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "2026-07-16..2026-07-20" in verdict.reason, verdict.reason
        assert "2026-07-08..2026-07-15" in verdict.reason, verdict.reason

    def test_a_closure_running_past_the_window_is_unknown_for_the_rest(self):
        verdict = judge(room(closed_to="2026-07-20", segments=(FIRST,)))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "2026-07-16..2026-07-20" in verdict.reason, verdict.reason

    def test_an_open_ended_closure_never_passes(self):
        verdict = judge(room(closed_from="2026-07-14", closed_to=None))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "2026-07-16" in verdict.reason and "no end" in verdict.reason, verdict.reason

    def test_a_closure_that_began_before_today_is_judged_from_today(self):
        """Fetched from today, so the closure's past nights are not asked about - P3's
        "from today onward"; a closure that has ENDED is the scope clause's to exclude (P4)."""
        verdict = judge(room(closed_from="2026-07-05", closed_to="2026-07-07",
                             segments=()))
        assert verdict.outcome is Outcome.UNKNOWN, (
            "a closure wholly before the day asked is never a vacuous PASS", verdict)
        verdict = judge(room(closed_from="2026-07-05", closed_to="2026-07-12",
                             segments=(segment("007004399", "2026-07-13", "2026-07-14"),)))
        assert verdict.outcome is Outcome.PASS, verdict

    def test_a_window_starting_after_today_does_not_cover_today(self):
        later = FetchedWindow("2026-07-10", "2026-07-17", "2026-07-08")
        verdict = judge(room(closed_from="2026-07-08", closed_to="2026-07-12", window=later))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "2026-07-08..2026-07-09" in verdict.reason, verdict.reason

    def test_a_collection_fetched_for_no_window_never_passes(self):
        verdict = judge(room(segments=(FIRST,), window=None))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "window" in verdict.reason

    def test_a_question_not_bounded_by_dates_never_passes(self):
        """No fetched window can be complete for "no segment, ever, has this status"."""
        verdict = judge(room(segments=(FIRST,)), predicates=[
            {"field": "occupancy.reservation_id", "operator": "equals", "value": "nobody"}])
        assert verdict.outcome is Outcome.UNKNOWN, verdict


class TestAnAbsenceOfSegmentsIsNeverReadAsNoGuests:

    def test_an_unavailable_reference_is_unknown_with_its_reason(self):
        refused = Value.unknown("the occupancy reference could not be fetched: refused")
        verdict = judge(room(segments=(), join=refused))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "could not be fetched: refused" in verdict.reason

    def test_an_unreadable_key_is_unknown_with_its_reason(self):
        unread = Value.unknown("the key this record joins on is not established (no number)")
        verdict = judge(room(segments=(), join=unread))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "no number" in verdict.reason

    def test_a_missing_join_answer_is_unknown(self):
        bundle = room()
        del bundle.joins["occupancy"]
        assert judge(bundle).outcome is Outcome.UNKNOWN


class TestARecordWhoseRoomIsUnknownMayBeThisRooms:
    """The refresh capture holds two segments (007004312, 007004313, 08..13 Jul) whose room
    number is present but empty - an evidence gap, never a value (#75). Either may be the
    closed room's guest, so a room that looks empty is not shown empty while one of them falls
    in its window. One that cannot fall in it changes nothing."""

    UNPLACED = segment("007004312", "2026-07-08", "2026-07-13", room=None)

    def unplaced(self):
        return dict(self.UNPLACED, **{"occupancy.room_number": Value.unknown(
            "occupancy.room_number is present but empty in the provider response")})

    def test_one_inside_the_window_makes_an_empty_room_unknown(self):
        verdict = judge(room(join=Value.known(False), unplaced=(self.unplaced(),)))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "007004312" in verdict.reason and "present but empty" in verdict.reason

    def test_one_outside_the_window_changes_nothing(self):
        verdict = judge(room(closed_from="2026-07-14", closed_to="2026-07-15",
                             join=Value.known(False), unplaced=(self.unplaced(),)))
        assert verdict.outcome is Outcome.PASS, verdict

    def test_it_never_turns_a_seen_overlap_into_unknown(self):
        verdict = judge(room(segments=(INSIDE,), unplaced=(self.unplaced(),)))
        assert verdict.outcome is Outcome.FAIL, verdict


class TestOutsideModeNoneTheGuardStands:
    """#87's guard, kept everywhere P1 does not reach. The validator refuses these rules before
    they run (check 8); this is the lock for one that was not validated."""

    @pytest.mark.parametrize("mode", ["all", "any"])
    def test_a_collection_read_in_all_or_any_is_still_refused(self, mode):
        verdict = judge(room(segments=(FIRST, INSIDE)), mode=mode)
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "collection" in verdict.reason, verdict.reason

    def test_a_collection_read_in_scope_is_still_refused(self):
        ir = rule()
        ir.raw["scope"] = [OVERLAP[0]]
        verdict = evaluate_record(ir, room(segments=(FIRST, INSIDE)))
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "collection" in verdict.reason, verdict.reason


class TestTheEdgesOfP1AndP3:

    def test_a_record_level_predicate_beside_the_collection_is_judged_once(self):
        """Under `none` a predicate about the room itself is still one clause of the rule: if
        it holds the room FAILs, whatever its segments say."""
        own = {"field": "room.closed_from", "operator": "exists"}
        assert judge(room(closed_from="2026-07-14", closed_to="2026-07-15"),
                     predicates=[own, *OVERLAP]).outcome is Outcome.FAIL
        absent_end = {"field": "room.closed_to", "operator": "exists"}
        verdict = judge(room(closed_from="2026-07-14", closed_to=None),
                        predicates=[absent_end, *OVERLAP])
        assert verdict.outcome is Outcome.UNKNOWN, "still no end, so still never a PASS"

    def test_a_predicate_reading_two_collections_cannot_be_judged(self):
        bundle = room(segments=(FIRST,))
        bundle.related["folio"] = ()
        bundle.joins["folio"] = Value.known(False)
        verdict = judge(bundle, predicates=[
            {"field": "occupancy.from", "operator": "equals", "compare_to": "folio.currency"}])
        assert verdict.outcome is Outcome.UNKNOWN, verdict
        assert "two collections" in verdict.reason

    @pytest.mark.parametrize("predicate", [
        {"field": "occupancy.from", "operator": "not_within",
         "interval": {"start": "room.closed_from", "end": "room.closed_to"}},
        {"field": "occupancy.from", "operator": "within",
         "interval": {"start": "room.closed_from", "end": "occupancy.to"}},
        {"field": "room.number", "operator": "within",
         "interval": {"start": "occupancy.from", "end": "occupancy.to"}},
    ], ids=["not_within", "a_bound_from_each_side", "a_point_that_is_no_date"])
    def test_a_shape_no_window_can_be_complete_for_never_passes(self, predicate):
        verdict = judge(room(closed_from="2026-07-14", closed_to="2026-07-15",
                             join=Value.known(False)), predicates=[predicate])
        assert verdict.outcome is not Outcome.PASS, verdict

    def test_a_window_bound_that_is_no_date_never_passes(self):
        bundle = room(join=Value.known(False))
        bundle.fields["room.closed_to"] = Value.known("soon")
        assert judge(bundle).outcome is not Outcome.PASS
