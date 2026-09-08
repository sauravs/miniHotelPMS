# -*- coding: utf-8 -*-
"""
Interval arithmetic, and the one business rule hidden inside it.

`overlaps` decides control 20: whether two reservations hold the same room on the same nights.
The rule that matters is the END BOUNDARY.

A guest departing on the 11th and a guest arriving on the 11th do NOT overlap. The room is
vacated and re-let the same day, and that is how a hotel counts nights. Counting the end
inclusively would report a violation on every back-to-back booking in the property - a wall of
false FAILs on the busiest rooms, which is precisely the shape of wrongness this engine exists
to avoid.

It is tested here rather than in slice 5 because the semantics is a decision, not an
implementation detail.
"""
from hotelcontrols.evaluator import overlaps, within
from hotelcontrols.kernel import Value


def date(text):
    return Value.known(text, unit="date")


class TestOverlap:
    def test_back_to_back_bookings_do_not_overlap(self):
        """THE rule. One guest leaves on the 11th, the next arrives on the 11th."""
        assert overlaps("2026-07-08", "2026-07-11", "2026-07-11", "2026-07-14") is False
        assert overlaps("2026-07-11", "2026-07-14", "2026-07-08", "2026-07-11") is False

    def test_a_shared_night_overlaps(self):
        assert overlaps("2026-07-08", "2026-07-12", "2026-07-11", "2026-07-14") is True

    def test_one_stay_entirely_inside_another_overlaps(self):
        assert overlaps("2026-07-01", "2026-07-30", "2026-07-10", "2026-07-12") is True

    def test_identical_stays_overlap(self):
        assert overlaps("2026-07-10", "2026-07-12", "2026-07-10", "2026-07-12") is True

    def test_separated_stays_do_not(self):
        assert overlaps("2026-07-01", "2026-07-05", "2026-07-20", "2026-07-25") is False

    def test_the_two_captured_segments_of_one_reservation_do_not_overlap(self):
        """Reservation 007003204 appears twice on room 303 - 10-11 August and 15-16 August.
        v1 read that repetition as an obstacle to cutting occupancy into records; it is
        actually the ordinary case, and the two segments are correctly disjoint."""
        assert overlaps("2024-08-10", "2024-08-11", "2024-08-15", "2024-08-16") is False


class TestWithinEdges:
    def test_an_unknown_subject_cannot_be_placed(self):
        assert within(Value.unknown("no arrival date"), date("2026-07-01"),
                      date("2026-07-31")) is None

    def test_a_start_after_the_end_matches_nothing(self):
        """A window nobody could have meant. Refusing to match is safer than silently
        inverting it into a window that covers the rest of time."""
        assert within(date("2026-07-15"), date("2026-07-31"), date("2026-07-01")) is False

    def test_an_open_start_with_a_closed_end(self):
        """A room closed until a date, with no recorded beginning."""
        assert within(date("2026-06-01"), Value.known(False), date("2026-07-31")) is True
        assert within(date("2026-08-01"), Value.known(False), date("2026-07-31")) is False

    def test_an_empty_string_bound_counts_as_unset_like_a_false_one(self):
        """MiniHotel writes both `rateCode=""` and `<rm_clsdt1 />`; the registry maps the
        absence to known(False), but a present-and-empty value must read the same way."""
        assert within(date("2027-01-01"), Value.known(""), Value.known("")) is False
