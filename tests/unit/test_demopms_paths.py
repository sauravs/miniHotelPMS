# -*- coding: utf-8 -*-
"""
Addressing a value inside a DemoPMS response.

The same job `minihotel/paths.py` does for a document tree, for a wire format that has no
attributes, no tags and no text nodes - only keys, arrays and JSON scalars. Written as its own
grammar rather than reused, because the whole point of the second provider is that nothing
above the adapter had to learn what either wire format is.

TWO DISTINCTIONS THIS LAYER KEEPS, AND THE RESOLVER DECIDES ABOUT
-----------------------------------------------------------------
  * "no such key" is an empty list; "the key is there holding null" is `[None]`. DemoPMS writes
    `null` where MiniHotel writes an empty element, and whether those mean the same thing is
    the registry's decision per field, not this module's.
  * A prefix is stripped explicitly rather than guessed. `strip_prefix` is how a record cut
    deep in the response reads a path written from the response root - and how it is stopped
    from reading one that belongs to a DIFFERENT branch (R7).
"""
import pytest

from hotelcontrols.providers.demopms.paths import PathError, find_all, parse_document, strip_prefix

DOC = {
    "bookings": [
        {"booking_ref": "A1", "state": "BOOKED", "external_ref": None,
         "total": {"amount": "870.00", "currency": "USD"},
         "stays": [{"room_no": "101"}, {"room_no": "102"}]},
        {"booking_ref": "A2", "state": "VOID", "stays": []},
    ],
    "rooms": [
        {"room_no": "01", "limits": [{"kind": "adults", "max": 6},
                                     {"kind": "children", "max": -1}]},
    ],
}


class TestAddressing:
    def test_a_plain_key_addresses_one_value(self):
        assert find_all(DOC["bookings"][0], "booking_ref") == ["A1"]

    def test_a_nested_key_descends(self):
        assert find_all(DOC["bookings"][0], "total.currency") == ["USD"]

    def test_an_array_segment_addresses_every_element(self):
        assert find_all(DOC, "bookings[].booking_ref") == ["A1", "A2"]

    def test_a_predicate_segment_selects_by_a_sibling_key(self):
        """DemoPMS stores per-guest-type capacity as a list of objects distinguished by a key,
        the same shape MiniHotel uses with sibling elements. There is no other way to say
        'the adult one'."""
        assert find_all(DOC, "rooms[].limits[kind=adults].max") == [6]

    def test_a_predicate_that_matches_nothing_addresses_nothing(self):
        assert find_all(DOC, "rooms[].limits[kind=youth].max") == []


class TestAbsenceIsNotEmptiness:
    def test_a_missing_key_addresses_nothing(self):
        """An empty list. The resolver turns that into the registry's `absent_means`."""
        assert find_all(DOC["bookings"][1], "external_ref") == []

    def test_a_key_holding_null_addresses_a_null(self):
        """`[None]`, not `[]`. DemoPMS writes null where MiniHotel writes `<x />`, and both
        mean 'present, empty' - which for some fields is a different answer from absent."""
        assert find_all(DOC["bookings"][0], "external_ref") == [None]

    def test_descending_through_a_missing_key_addresses_nothing_rather_than_raising(self):
        assert find_all(DOC["bookings"][1], "total.currency") == []

    def test_an_array_segment_over_a_non_array_addresses_nothing(self):
        """A wire format that changed shape must not be read as if it had not."""
        assert find_all(DOC["bookings"][0], "booking_ref[].x") == []


class TestPrefixStripping:
    """Anchoring. Paths are written from the response root; records are cut deeper."""

    def test_a_path_under_the_prefix_is_trimmed_to_the_remainder(self):
        assert strip_prefix("bookings[].stays[].room_no", "bookings[].stays[]") == "room_no"

    def test_a_path_on_an_enclosing_record_is_trimmed_to_that_records_remainder(self):
        """How a stay reads its own booking's currency - the upward walk, made explicit."""
        assert strip_prefix("bookings[].total.currency", "bookings[]") == "total.currency"

    def test_a_path_on_a_different_branch_is_refused(self):
        """R7, structurally. A stay must never resolve a path that belongs to the room list -
        returning None here is what makes the resolver walk on rather than read a stranger."""
        assert strip_prefix("rooms[].room_no", "bookings[].stays[]") is None

    def test_an_empty_prefix_leaves_the_path_whole(self):
        """A whole response nobody has cut yet stands at the root."""
        assert strip_prefix("ledger.balance", "") == "ledger.balance"

    def test_a_prefix_equal_to_the_path_leaves_nothing_to_read(self):
        """The record IS the value. `ledger` cut as a folio record, asked for `ledger`."""
        assert strip_prefix("ledger", "ledger") == ""

    def test_a_partial_segment_is_not_a_prefix(self):
        """`rooms[]` must not look like a prefix of `rooms_archive[].x`, or a record would
        read from a list that merely starts with the same letters."""
        assert strip_prefix("rooms_archive[].room_no", "rooms[]") is None


class TestRefusals:
    def test_a_malformed_response_is_named_rather_than_crashing_somewhere_later(self):
        with pytest.raises(PathError):
            parse_document("{not json")

    def test_an_empty_path_addresses_nothing_and_says_so(self):
        with pytest.raises(PathError):
            find_all(DOC, "")

    def test_a_segment_the_grammar_does_not_define_is_refused(self):
        """A path that silently matches nothing blames the hotel's data for our own typo."""
        with pytest.raises(PathError):
            find_all(DOC, "bookings[].{oops}")

    def test_a_well_formed_response_parses_to_its_own_shape(self):
        assert parse_document('{"a": [1, 2]}') == {"a": [1, 2]}
