# -*- coding: utf-8 -*-
"""
THE LIVE REQUEST FORM - transcribed from calls that worked, not from documentation.

Every request this file asserts is the one that produced a response in `fixtures/minihotel/`.
That provenance is the whole argument for the file existing: the vendor's documentation never
states how to encode a request at all, and probing the WSDL showed the operations declare empty
parameter types, so the service reads the raw body rather than named parameters. Nobody could
have derived these forms from the docs, and this project's rule is that a captured response
beats a document.

Which means the tests below are not "does the encoder do what I wrote". They are "does the
encoder still emit the request that is known to have worked". A change that breaks one of them
is a change that would go out to somebody else's server as a question they have never been
asked (R8).

NOTHING HERE HAS BEEN RE-VERIFIED SINCE THE CAPTURES WERE TAKEN. The sandbox has moved on once
already (open question 1.2), so a live call is approved individually, bounded and staged (D3).
"""
import pytest

from hotelcontrols.providers.base import Request, ResponseUnavailable
from hotelcontrols.providers.minihotel import live
from hotelcontrols.providers.transport import Credentials

CREDENTIALS = Credentials(user="U", password="P", hotel="H", base_url="https://host.invalid/")


def body_for(endpoint, params=None):
    return live.encode(Request(endpoint, params or {}), CREDENTIALS).body


class TestTheCallsThatProducedTheCaptures:

    def test_the_room_type_master(self):
        call = live.encode(Request("getRoomTypes"), CREDENTIALS)
        assert call.method == "POST"
        assert call.url == "https://host.invalid/agents/ws/settings/rooms/RoomsMain.asmx/getRoomTypes"
        assert '<Settings name="getRoomTypes">' in call.body
        assert '<Authentication username="U" password="P" />' in call.body
        assert '<Hotel id="H" />' in call.body

    def test_the_room_master_asks_for_every_room_with_an_empty_room_number(self):
        """An EMPTY `<room_number>` means "return all rooms" - the documented way to fetch the
        whole master in one call rather than iterating room by room. It is the one place in
        this encoder where an empty element is meaningful rather than lazy."""
        body = body_for("getRooms")
        assert "<room_number></room_number>" in body

    def test_a_reservation_query_carries_its_window(self):
        body = body_for("GetReservationKey",
                        {"ArrivalDate": {"From": "2024-08-01", "To": "2024-08-31"}})
        assert '<ArrivalDate From="2024-08-01" To="2024-08-31" />' in body

    def test_a_reservation_query_carries_a_status_filter_when_the_control_asks_for_one(self):
        """`BookingSearch Status="OUT"` is what narrows 65 bookings to 1 - the filter control 6
        declared for a year before any call exercised it."""
        body = body_for("GetReservationKey",
                        {"DepartureDate": {"From": "2026-07-01", "To": "2026-07-02"},
                         "BookingSearch": {"Status": "OUT"}})
        assert '<DepartureDate From="2026-07-01" To="2026-07-02" />' in body
        assert '<BookingSearch Status="OUT" />' in body

    def test_the_price_flag_is_sent_when_a_control_needs_rate_codes(self):
        """Without it there is no pricing and no rate code at all, so the two controls that
        need `stay.rate_code` would come back UNKNOWN for a reason that was really a
        malformed question."""
        body = body_for("GetReservationKey", {"ArrivalDate": {"From": "a", "To": "b"},
                                              "IncludeRoomPrices": "true"})
        assert "<IncludeRoomPrices>true</IncludeRoomPrices>" in body

    def test_a_folio_names_exactly_one_reservation(self):
        """R1, in the request itself. One reservation per call, no bulk journal endpoint, and
        this is where that cost is incurred."""
        call = live.encode(Request("GetReservationBalance",
                                   {"ReservationNumber": "007003199"}), CREDENTIALS)
        assert call.url.endswith("/agents/ws/sci/sciMain.asmx/GetReservationBalance")
        assert "<ReservationNumber>007003199</ReservationNumber>" in call.body

    def test_the_occupancy_endpoint_is_selected_by_a_response_type_not_by_its_path(self):
        """It lives on the ARI API at `/gds` and is chosen by `ResponseType="03"`. Nobody would
        guess that, which is why it is transcribed rather than derived."""
        call = live.encode(Request("RoomStatusInquiry",
                                   {"DateRange": {"from": "2024-08-14", "to": "2024-08-17"}}),
                           CREDENTIALS)
        assert call.url.endswith("/gds")
        assert 'ResponseType="03"' in call.body
        assert '<DateRange from="2024-08-14" to="2024-08-17" />' in call.body

    def test_every_call_is_posted_as_xml(self):
        for endpoint, params in (("getRooms", {}), ("getRoomTypes", {}),
                                 ("GetReservationKey", {}),
                                 ("GetReservationBalance", {"ReservationNumber": "1"}),
                                 ("RoomStatusInquiry", {"DateRange": {"from": "a", "to": "b"}})):
            call = live.encode(Request(endpoint, params), CREDENTIALS)
            assert call.method == "POST"
            assert call.headers["Content-Type"].startswith("text/xml")


class TestWhatItRefusesToAsk:
    """Three refusals, and each one is a place where guessing would have been easy."""

    def test_an_endpoint_whose_request_was_never_captured_is_refused_by_name(self):
        """`BulkARI`'s RESPONSE is in the fixture set; the request that produced it was not
        recorded. Inventing a request to somebody else's server is worse than an unbuildable
        control - and the control that would use it is structurally unresolvable anyway
        (R13, open question 1.6)."""
        with pytest.raises(ResponseUnavailable) as refusal:
            live.encode(Request("BulkARI"), CREDENTIALS)
        assert "BulkARI" in str(refusal.value)
        assert "captured" in str(refusal.value)

    def test_an_occupancy_query_with_no_window_is_refused(self):
        """The reference join asks for occupancy with no parameters, which is a fine question
        to put to a frozen capture and is exactly the wide unbounded range the vendor asked
        integrators not to send to a live server (R8)."""
        with pytest.raises(ResponseUnavailable) as refusal:
            live.encode(Request("RoomStatusInquiry"), CREDENTIALS)
        assert "R8" in str(refusal.value)

    def test_a_folio_query_with_no_reservation_is_refused(self):
        with pytest.raises(ResponseUnavailable) as refusal:
            live.encode(Request("GetReservationBalance"), CREDENTIALS)
        assert "R1" in str(refusal.value)

    def test_a_filter_with_no_captured_form_is_refused_rather_than_dropped(self):
        """The same rule the frozen replay follows. Silently ignoring a filter hands back a
        WIDER population than the control asked for, which is the one failure a bounded query
        exists to prevent - and against a live server it is also the wide range R8 forbids."""
        with pytest.raises(ResponseUnavailable) as refusal:
            live.encode(Request("GetReservationKey", {"GuestName": "Cohen"}), CREDENTIALS)
        assert "GuestName" in str(refusal.value)


class TestCredentialsAreEscapedAndNotLeaked:

    def test_a_credential_with_an_xml_metacharacter_cannot_break_the_document(self):
        """A password is whatever the vendor issued, and `&` in one would produce a request
        that is not well-formed XML - which the server would reject with an error about the
        request rather than about the password, sending an operator to the wrong place."""
        awkward = Credentials(user='O"Brien & co', password="a<b>c", hotel="H",
                              base_url="https://host.invalid")
        body = live.encode(Request("getRooms"), awkward).body
        assert "a<b>c" not in body
        assert "&lt;b&gt;" in body

    def test_the_encoder_does_not_read_the_environment(self):
        """Credentials arrive as an argument. An encoder that reached for the environment would
        make every plan and every test depend on what happened to be exported."""
        import ast
        import pathlib

        source = pathlib.Path(live.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert "environ" not in names
        assert "getenv" not in names
