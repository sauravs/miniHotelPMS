# -*- coding: utf-8 -*-
"""
The tokens the evidence layer works with, and the ways the adapter refuses.

Everything here is what slice 3 will call. The point of each token is that the layer above
COMPARES it and never interprets it: `source_key` says "these two fields come from the same
call" without ever revealing what the call is, which is how the canonical boundary survives
contact with a real cost model (R1 - a folio takes one call per reservation).
"""
import pytest

from hotelcontrols.kernel import Value
from hotelcontrols.providers.base import Request, RecordBoundaryUnknown, ResponseUnavailable
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import SpecError, TenantConfig


@pytest.fixture
def a():
    return MiniHotelAdapter(TenantConfig.load("sandbox"), FrozenSource("sandbox2026"))


class TestCallGrouping:
    def test_two_fields_from_one_response_share_a_source_key(self, a):
        """R1. Sharing the key is what lets the evidence layer fetch once and read twice
        rather than paying for each field separately."""
        assert a.source_key("reservation.id") == a.source_key("reservation.status")

    def test_fields_from_different_responses_do_not(self, a):
        assert a.source_key("reservation.id") != a.source_key("folio.balance_due")
        assert a.source_key("room.number") != a.source_key("room_type.code")

    def test_the_folio_is_fetched_one_reservation_at_a_time(self, a):
        """R1, the fact the whole population design exists for: GetReservationBalance takes one
        reservation per call and there is no bulk journal endpoint."""
        request = a.follow_up("folio.balance_due", "007004348")
        assert isinstance(request, Request)
        assert request.params == {"ReservationNumber": "007004348"}

    def test_a_property_wide_field_has_no_per_record_call(self, a):
        """Room capacity answers for the whole property. Saying None here is what makes the
        evidence layer fetch it ONCE as a reference rather than once per record (F1)."""
        assert a.follow_up("room.max_guests.adults", "01") is None

    def test_a_reference_request_exists_for_the_joinable_entities(self, a):
        """The joins that unlock the four room-based controls."""
        for entity in ("room", "room_type", "occupancy"):
            assert isinstance(a.reference_request(entity), Request), entity
        assert a.reference_request("rate_plan") is None, (
            "R13 - no MiniHotel endpoint resolves a rate plan, so this must be tenant-supplied "
            "or UNKNOWN, never a call we pretend to be able to make")

    def test_a_request_key_is_order_independent(self):
        """Two spellings of the same question must share one cache entry, or the run-scoped
        cache silently pays twice (R1)."""
        one = Request("X", {"a": {"From": "1", "To": "2"}, "b": 3})
        two = Request("X", {"b": 3, "a": {"To": "2", "From": "1"}})
        assert one.key() == two.key()


class TestProvenance:
    def test_provenance_names_the_system_and_the_call_but_no_field_path(self, a):
        """The one thing carrying a provider name that crosses the canonical boundary, and it
        crosses as data. An auditor must know which system and which call produced a number;
        no PMS FIELD PATH is ever in it."""
        provenance = a.provenance("folio.balance_due")
        assert provenance == "pms:minihotel/GetReservationBalance"
        assert "TotalDebit" not in provenance

    def test_every_value_carries_its_provenance(self, a):
        record = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")[0]
        assert a.resolve("reservation.status", record).source == \
            "pms:minihotel/GetReservationKey"


class TestRepeatedValues:
    def test_resolve_all_returns_every_transaction_on_a_folio(self, a):
        """A folio holds many transactions; `resolve` takes the first and `resolve_all` takes
        them all. Control 19 needs the second."""
        folio = a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007004348"}))
        amounts = a.resolve_all("folio.transactions[].amount", folio)
        assert len(amounts) >= 2
        assert all(v.is_known for v in amounts)

    def test_resolve_all_on_a_field_from_another_call_says_so_rather_than_raising(self, a):
        response = a.fetch(Request("getRooms", {}))
        answer = a.resolve_all("folio.balance_due", response)
        assert len(answer) == 1 and not answer[0].is_known

    def test_resolve_all_of_an_absent_field_returns_one_reasoned_unknown(self, a):
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        answer = a.resolve_all("room.closed_from", rooms[0])
        assert len(answer) == 1


class TestRefusals:
    def test_a_field_with_no_mapping_is_a_spec_error_not_an_evidence_gap(self, a):
        """The distinction that matters: an evidence gap is a statement about a HOTEL, and a
        missing mapping is a statement about US. Conflating them sends somebody looking for
        data that was never the problem."""
        with pytest.raises(SpecError):
            a.source_key("reservation.vip")

    def test_asking_a_response_for_a_field_it_cannot_hold_is_an_unknown(self, a):
        """Not a crash: a control whose evidence spans two calls asks each record for
        everything, and the answer 'not from this one' is ordinary."""
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        answer = a.resolve("folio.balance_due", rooms[0])
        assert not answer.is_known and "not available" in answer.reason

    def test_an_entity_this_response_cannot_be_cut_into_is_named_rather_than_guessed(self, a):
        """A gap in this engine, reported as which gap it is - so a runner can show a sentence
        instead of a stack trace."""
        with pytest.raises(RecordBoundaryUnknown):
            a.records(a.fetch(Request("getRooms", {})), "folio")

    def test_an_unknown_transform_in_the_spec_raises(self, a):
        """An unapplied transform is a wrong value that LOOKS right, which is worse than a
        crash - so the adapter refuses rather than passing the raw string through."""
        a.mappings["reservation.status"] = dict(a.mappings["reservation.status"],
                                                transform="no_such_transform")
        record = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")[0]
        with pytest.raises(SpecError):
            a.resolve("reservation.status", record)

    def test_identity_of_an_entity_with_no_identity_field_is_unknown(self, a):
        from hotelcontrols.providers.minihotel.records import Record
        import xml.etree.ElementTree as ET
        made_up = Record("getRooms", ET.Element("x"), entity="unicorn")
        assert not a.identity(made_up).is_known

    def test_a_capture_that_does_not_exist_is_refused_at_construction(self):
        with pytest.raises(ResponseUnavailable):
            FrozenSource("sandbox1999")

    def test_a_capture_holding_no_such_response_says_which_capture(self, a):
        source = FrozenSource("sandbox2024")
        with pytest.raises(ResponseUnavailable) as caught:
            source.fetch(Request("SomeEndpointNobodyCaptured", {}))
        assert "sandbox2024" in str(caught.value)


class TestCaptureMetadata:
    def test_a_capture_describes_itself_for_the_audit_trail(self):
        """A run has to be able to say WHICH body of evidence produced it, six months later."""
        source = FrozenSource("sandbox2026")
        assert "sandbox2026" in source.origin and "pseudonymised" in source.origin
        assert source.as_of == "2026-07-08"

    def test_nothing_in_this_repository_is_invented(self):
        """v1 shipped hand-written fixtures to reach outcomes its captures could not. Every
        fixture here is a real captured response, so the flag is False and stays False - and a
        run over invented records that did not announce itself would be a lie by omission."""
        assert FrozenSource("sandbox2026").is_synthetic is False
        assert FrozenSource("sandbox2024").is_synthetic is False
