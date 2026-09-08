# -*- coding: utf-8 -*-
"""
Structured path resolution - the fix for review finding F4.

v1 addressed all 52 field mappings with REGEXES over the raw response text. It worked, and it
was silently fragile in two ways I reproduced against the v1 resolver before writing any of
this:

    attrs as captured | arrival = known('2026-07-01' date)
    attrs reordered   | arrival = unknown(reservation.arrival_date is absent...)
    escaped surname   | known('O&apos;Brien &amp; Sons')

1. `reservation.arrival_date` mapped to `<Timespan arrival="([^"]*)"`, which requires `arrival`
   to be the FIRST attribute. XML attribute order is explicitly not significant, so reordering
   two attributes in a semantically identical document turned a known date into UNKNOWN. Note
   HOW it failed: not with an exception, but as an evidence gap. In a scope predicate that is
   worse than a crash - the control silently stops applying to records it should judge.

2. XML entities were never decoded, so a guest named O'Brien resolved as `O&apos;Brien`. The
   `exists` test still passed, so nothing failed loudly - but the audit trail showed garbled
   evidence and any equality or duplicate comparison on that field was wrong.

The provider map already recorded a structured `path` for every field. v1 never executed it.
This module does, against a real document tree, and both failures become impossible rather
than merely fixed.
"""
import pytest

from hotelcontrols.providers.minihotel.paths import (PathError, find_all, find_elements,
                                                     parse_document)

BOOKING = """<?xml version="1.0" encoding="utf-8"?>
<Bookings>
  <Booking Minihotel_reservation_id="007003199" Status="OUT" source="Qwerty">
    <RoomStays>
      <RoomStay roomNumber="01" roomTypeID="DBL" mealStatus="BB">
        <Total AmountAfterTaxes="150" rateCode="Tourist-BB" CurrencyCode="USD" />
      </RoomStay>
    </RoomStays>
    <PrimaryGuest>
      <Name givenName="Bob" surname="O&apos;Brien &amp; Sons" />
      <Email>bob@example.example</Email>
      <IdNumber />
    </PrimaryGuest>
    <ResGlobalInfo>
      <GuestCount adult="2" child="0" />
      <Timespan arrival="28/08/2024" departure="01/09/2024" />
    </ResGlobalInfo>
  </Booking>
</Bookings>
"""

ROOM = """<Response><ArrayOfRnm_struct_room>
  <rnm_struct_room is_mapped="true">
    <rm_number>01</rm_number>
    <rm_type>DBL</rm_type>
    <rm_clsdt1 />
    <ArrayOfRec_rooms_gst_max>
      <rec_rooms_gst_max><rgm_gst_type>A</rgm_gst_type><rgm_max>2</rgm_max></rec_rooms_gst_max>
      <rec_rooms_gst_max><rgm_gst_type>C</rgm_gst_type><rgm_max>1</rgm_max></rec_rooms_gst_max>
      <rec_rooms_gst_max><rgm_gst_type>B</rgm_gst_type><rgm_max>0</rgm_max></rec_rooms_gst_max>
    </ArrayOfRec_rooms_gst_max>
  </rnm_struct_room>
</ArrayOfRnm_struct_room></Response>
"""


class TestTheV1FailuresAreNowImpossible:
    def test_attribute_order_cannot_change_a_resolved_value(self):
        """The regression guard on F4's first failure.

        Two semantically identical documents that differ only in attribute order must resolve
        identically. Under v1's regex the second one returned UNKNOWN.
        """
        as_captured = parse_document(
            '<Booking><ResGlobalInfo>'
            '<Timespan arrival="28/08/2024" departure="01/09/2024" />'
            '</ResGlobalInfo></Booking>')
        reordered = parse_document(
            '<Booking><ResGlobalInfo>'
            '<Timespan departure="01/09/2024" arrival="28/08/2024" />'
            '</ResGlobalInfo></Booking>')
        path = "Booking/ResGlobalInfo/Timespan@arrival"
        assert find_all(as_captured, path) == find_all(reordered, path) == ["28/08/2024"]

    def test_xml_entities_are_decoded(self):
        """The regression guard on F4's second failure. `exists` passed either way, which is
        exactly why nobody noticed: the evidence was garbled, not missing."""
        root = parse_document(BOOKING)
        assert find_all(root, "PrimaryGuest/Name@surname") == ["O'Brien & Sons"]

    def test_whitespace_between_attributes_does_not_matter_either(self):
        a = parse_document('<Booking><Timespan arrival="1" /></Booking>')
        b = parse_document('<Booking>\n  <Timespan\n     arrival="1"\n  />\n</Booking>')
        assert find_all(a, "Timespan@arrival") == find_all(b, "Timespan@arrival")


class TestPathGrammar:
    def test_an_attribute_on_the_record_element_itself(self):
        """The record IS the Booking, and `Booking@Status` addresses it rather than a child."""
        booking = find_elements(parse_document(BOOKING), "Booking")[0]
        assert find_all(booking, "Booking@Status") == ["OUT"]

    def test_a_nested_element_attribute(self):
        assert find_all(parse_document(BOOKING),
                        "Booking/ResGlobalInfo/Timespan@departure") == ["01/09/2024"]

    def test_element_text_with_no_attribute(self):
        assert find_all(parse_document(BOOKING), "PrimaryGuest/Email") == \
            ["bob@example.example"]

    def test_a_predicate_selects_by_a_sibling_elements_text(self):
        """`rec_rooms_gst_max[rgm_gst_type=A]/rgm_max` - how MiniHotel stores per-guest-type
        capacity. Three sibling blocks distinguished only by a child element's value."""
        root = parse_document(ROOM)
        assert find_all(root, "rec_rooms_gst_max[rgm_gst_type=A]/rgm_max") == ["2"]
        assert find_all(root, "rec_rooms_gst_max[rgm_gst_type=C]/rgm_max") == ["1"]
        assert find_all(root, "rec_rooms_gst_max[rgm_gst_type=B]/rgm_max") == ["0"]

    def test_every_match_is_returned_in_document_order(self):
        """A booking can hold several room stays with different rooms, types and rates - which
        is why `stay` is a separate entity. The resolver takes the first; the caller that wants
        them one at a time cuts records instead."""
        many = parse_document(
            "<Booking><RoomStays>"
            '<RoomStay roomNumber="01" /><RoomStay roomNumber="02" /></RoomStays></Booking>')
        assert find_all(many, "RoomStay@roomNumber") == ["01", "02"]


class TestAbsenceIsDistinctFromEmptiness:
    def test_a_missing_element_yields_nothing(self):
        assert find_all(parse_document(BOOKING), "PrimaryGuest/Phone") == []

    def test_a_missing_attribute_yields_nothing(self):
        assert find_all(parse_document(BOOKING), "Booking@market_segment") == []

    def test_a_self_closing_element_yields_an_empty_string_not_nothing(self):
        """MiniHotel writes both `rateCode=""` and `<rm_clsdt1 />`, and they mean the same
        thing - but the resolver decides that, not the path layer. Conflating them here would
        hide which form the provider actually used."""
        assert find_all(parse_document(ROOM), "rnm_struct_room/rm_clsdt1") == [""]
        assert find_all(parse_document(BOOKING), "PrimaryGuest/IdNumber") == [""]

    def test_an_empty_attribute_yields_an_empty_string(self):
        root = parse_document('<Booking><Total rateCode="" /></Booking>')
        assert find_all(root, "Total@rateCode") == [""]


class TestRefusals:
    def test_a_malformed_path_raises_rather_than_matching_nothing(self):
        """A path that silently matches nothing is an evidence gap that blames the hotel for a
        typo in our own spec."""
        with pytest.raises(PathError):
            find_all(parse_document(BOOKING), "")
        with pytest.raises(PathError):
            find_all(parse_document(BOOKING), "Booking@")
        with pytest.raises(PathError):
            find_all(parse_document(BOOKING), "Booking[broken/x")

    def test_malformed_xml_raises(self):
        with pytest.raises(PathError):
            parse_document("<Booking><unclosed>")

    def test_find_elements_refuses_a_path_that_names_an_attribute(self):
        """An attribute is a value, not a node. Returning its owning element instead would
        quietly answer a different question from the one asked."""
        with pytest.raises(PathError):
            find_elements(parse_document(BOOKING), "Booking@Status")

    def test_a_namespaced_document_is_still_addressable(self):
        """The captures declare xsd/xsi prefixes without using them, but a provider is free to
        start emitting a default namespace, and every path in the spec would stop matching."""
        root = parse_document(
            '<Bookings xmlns="urn:example"><Booking Status="OUT" /></Bookings>')
        assert find_all(root, "Booking@Status") == ["OUT"]
