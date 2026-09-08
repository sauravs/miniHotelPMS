# -*- coding: utf-8 -*-
"""
The MiniHotel adapter against real captured responses.

The unit tests prove each transform and each path. This proves the adapter answers correctly
about the actual records the vendor returned - which is the only thing that matters, because
every finding in this project came from a response rather than from a document.

Fixtures are pseudonymised (decision D6): guest names, emails, phones and remarks are stable
fakes. Reservation ids, statuses, dates, amounts, currencies and every structural quirk are
EXACTLY as captured, so every assertion below is about real vendor behaviour.
"""
import json
import pathlib
from decimal import Decimal

import pytest

from hotelcontrols.kernel import NOT_APPLICABLE, Money
from hotelcontrols.providers.base import Request, ResponseUnavailable
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import TenantConfig

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"


def adapter(capture="sandbox2026"):
    return MiniHotelAdapter(TenantConfig.load("sandbox"), FrozenSource(capture))


@pytest.fixture(scope="module")
def provider_map():
    return json.loads((SPEC / "providers" / "minihotel.json").read_text())


class TestEveryMappingResolves:
    """Slice 2 gate: all 52 mappings resolve against their captured response.

    v1 performed this check in its spec validator; here it is enforced in the suite as well,
    because a mapping that silently matches nothing is an evidence gap that blames the hotel's
    data for a typo in our specification.
    """

    def test_all_fifty_two_mappings_find_their_field(self, provider_map):
        from hotelcontrols.providers.minihotel.paths import find_all, parse_document

        unresolved = []
        for mapping in provider_map["mappings"]:
            body = (pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "minihotel"
                    / mapping["probe"]).read_text(encoding="utf-8")
            found = find_all(parse_document(body), mapping["path"])
            if not found:
                unresolved.append("%s -> %s in %s"
                                  % (mapping["canonical"], mapping["path"], mapping["probe"]))
        assert not unresolved, "\n".join(unresolved)

    def test_a_field_never_comes_back_as_none(self, provider_map):
        """Absence is an answer and the registry says which one. None would be a second
        failure vocabulary - the one callers forget to check."""
        a = adapter("sandbox2024")
        record = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")[0]
        for mapping in provider_map["mappings"]:
            if mapping["endpoint"] != "GetReservationKey":
                continue
            value = a.resolve(mapping["canonical"], record)
            assert value is not None, mapping["canonical"]
            assert value.is_known or value.reason, mapping["canonical"]


class TestTheCurrencySplitIsVisible:
    """R9, the finding that shapes the whole codebase."""

    def test_a_folio_and_its_own_reservation_are_in_different_currencies(self):
        a = adapter("sandbox2024")
        folio = a.records(
            a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007003199"})),
            "folio")[0]
        balance = a.resolve("folio.balance_due", folio)
        assert balance.payload == Money(Decimal("3262.5"), "ILS")

        booking = next(
            r for r in a.records(a.fetch(Request("GetReservationKey", {})), "reservation")
            if a.resolve("reservation.id", r).payload == "007003199")
        assert a.resolve("reservation.currency", booking).payload == "USD"
        assert a.resolve("reservation.total_amount", booking).payload.currency == "USD"

    def test_those_two_amounts_refuse_to_be_compared(self):
        """The guard, end to end. There is no exchange rate anywhere in this API, so there is
        no honest answer to give and none is given."""
        from hotelcontrols.kernel import CurrencyMismatch
        a = adapter("sandbox2024")
        folio = a.records(
            a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007003199"})),
            "folio")[0]
        booking = next(
            r for r in a.records(a.fetch(Request("GetReservationKey", {})), "reservation")
            if a.resolve("reservation.id", r).payload == "007003199")
        with pytest.raises(CurrencyMismatch):
            a.resolve("folio.balance_due", folio).equals(
                a.resolve("reservation.total_amount", booking))

    def test_money_is_decimal_all_the_way_from_the_response(self):
        a = adapter("sandbox2024")
        folio = a.records(
            a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007003199"})),
            "folio")[0]
        assert isinstance(a.resolve("folio.balance_due", folio).payload.amount, Decimal)


class TestTheThreeCheckoutFolios:
    """The records that give the checkout controls a genuine PASS, FAIL and UNKNOWN."""

    def test_the_settled_folio(self):
        a = adapter()
        folio = a.records(
            a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007004351"})),
            "folio")[0]
        assert a.resolve("folio.balance_due", folio).payload == Money(Decimal("0"), "ILS")

    def test_the_overpaid_folio_is_negative(self):
        """Reservation 007004348 departed at -490.75 ILS: the guest overpaid and the hotel
        owes a refund. v1 reported this as an outstanding balance, which is why control 6 is
        two controls in v2 (decision D8)."""
        a = adapter()
        folio = a.records(
            a.fetch(Request("GetReservationBalance", {"ReservationNumber": "007004348"})),
            "folio")[0]
        balance = a.resolve("folio.balance_due", folio)
        assert balance.payload == Money(Decimal("-490.75"), "ILS")
        assert balance.payload.is_negative

    def test_a_folio_that_was_never_captured_is_unavailable_not_empty(self):
        """The evidence gap the control has to survive. One call per reservation is the cost
        this control is built around (R1) and the sandbox is someone else's server (R8), so
        only three folios were taken - and the rest must be UNKNOWN, never zero."""
        with pytest.raises(ResponseUnavailable):
            adapter().fetch(Request("GetReservationBalance",
                                    {"ReservationNumber": "007004365"}))


class TestZeroMeansUnconfigured:
    def test_most_rooms_have_no_configured_adult_capacity(self):
        """R12 - 23 of 28 sandbox rooms report adult capacity 0. Reading those as real zeroes
        turns a configuration gap into a wall of FAILs for control 4."""
        a = adapter()
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        assert len(rooms) == 28
        unknown = [r for r in rooms if not a.resolve("room.max_guests.adults", r).is_known]
        assert len(unknown) == 23

    def test_the_closed_date_mechanism_has_never_been_observed_working(self):
        """Open question 2.4, and the reason controls 1d, 2 and 13 are rated Medium. All 28
        rooms return an empty window, so if the format differs from the docs those controls
        would silently pass everything."""
        a = adapter()
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        populated = [r for r in rooms if a.resolve("room.closed_from", r).payload]
        assert populated == []

    def test_a_room_type_the_master_does_not_define(self):
        """R11 - rooms 9900/9901/9902 carry type 'Double', which getRoomTypes does not define.
        A real latent defect in live data, found by running control 1 rather than by reading."""
        a = adapter()
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        types = {a.resolve("room.type", r).payload for r in rooms}
        defined = {a.resolve("room_type.code", t).payload
                   for t in a.records(a.fetch(Request("getRoomTypes", {})), "room_type")}
        assert "double" in types and "double" not in defined


class TestRecordIsolation:
    """R7. A record may read the record CONTAINING it, and never a sibling."""

    def test_a_stay_reads_its_own_reservations_currency_from_the_booking_above_it(self):
        """A room stay's amount is inside <RoomStay> while the currency it is denominated in
        sits on the <Booking>. Reading upwards is required."""
        a = adapter("sandbox2024")
        response = a.fetch(Request("GetReservationKey", {}))
        stay = a.records(response, "stay")[0]
        assert a.resolve("reservation.currency", stay).payload == "USD"
        assert a.resolve("reservation.id", stay).is_known

    def test_a_direct_booking_never_borrows_another_bookings_channel_id(self):
        """THE record-isolation test. 7 of 11 sandbox bookings are direct and carry no portal
        id at all. A resolver that wandered sideways looking for a better answer would report
        every direct booking as a duplicate of every other one."""
        a = adapter("sandbox2024")
        bookings = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")
        ids = [a.resolve("reservation.channel_confirmation_id", b) for b in bookings]
        direct = [v for v in ids if v.payload is NOT_APPLICABLE]
        assert direct, "the 2024 capture should contain direct bookings"
        for value in direct:
            assert value.is_known, "a direct booking's missing channel id is a FACT, not a gap"

    def test_an_absent_field_does_not_climb_out_into_the_whole_response(self):
        a = adapter("sandbox2024")
        response = a.fetch(Request("GetReservationKey", {}))
        for booking in a.records(response, "reservation"):
            own = a.resolve("reservation.id", booking).payload
            assert own, "every booking resolves its OWN id"


class TestOccupancyHasARecordBoundary:
    """Issue #3. v1 declared this entity uncuttable; the response disproves it."""

    def test_each_reservation_element_is_a_complete_occupancy_segment(self):
        a = adapter()
        segments = a.records(a.fetch(Request("RoomStatusInquiry", {})), "occupancy")
        assert len(segments) == 2
        for segment in segments:
            for field_name in ("occupancy.room_number", "occupancy.reservation_id",
                               "occupancy.from", "occupancy.to", "occupancy.status"):
                assert a.resolve(field_name, segment).is_known, field_name

    def test_one_reservation_appearing_as_two_segments_keeps_its_own_dates(self):
        """The behaviour v1 read as an obstacle is exactly what an overlap check needs."""
        a = adapter()
        segments = a.records(a.fetch(Request("RoomStatusInquiry", {})), "occupancy")
        assert {a.resolve("occupancy.reservation_id", s).payload for s in segments} == \
            {"007003204"}
        assert [a.resolve("occupancy.from", s).payload for s in segments] == \
            ["2024-08-10", "2024-08-15"]
        assert {a.resolve("occupancy.room_number", s).payload for s in segments} == {"303"}


class TestStatusVocabulary:
    def test_documented_codes_resolve_and_undocumented_ones_do_not(self):
        """A5. One reservation in five carries a status nobody has documented, and a status we
        cannot name must not decide whether a control applies."""
        a = adapter()
        bookings = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")
        statuses = [a.resolve("reservation.status", b) for b in bookings]
        assert any(v.is_known for v in statuses)
        unknown = [v for v in statuses if not v.is_known]
        assert unknown, "the 2026 capture contains OK4 and WL"
        for value in unknown:
            assert value.risk == "A5"


class TestReplayHonesty:
    """Finding F19c - a fixture has to know what question it was asked."""

    def test_a_status_filter_narrows_the_population_the_way_the_server_did(self):
        """Sending BookingSearch Status='OUT' narrowed 65 bookings to 1 on the live server."""
        a = adapter()
        everyone = a.records(a.fetch(Request("GetReservationKey", {})), "reservation")
        checked_out = a.records(
            a.fetch(Request("GetReservationKey", {"BookingSearch": {"Status": "OUT"}})),
            "reservation")
        assert 0 < len(checked_out) < len(everyone)
        for booking in checked_out:
            assert a.resolve("reservation.status", booking).payload == "checked_out"

    def test_a_window_the_capture_never_covered_is_refused_not_answered_emptily(self):
        """The important one. An empty population renders identically to 'we looked and
        everything was fine', so a question this capture cannot answer must say so."""
        a = adapter()
        with pytest.raises(ResponseUnavailable) as caught:
            a.fetch(Request("GetReservationKey",
                            {"DepartureDate": {"From": "2019-01-01", "To": "2019-01-31"}}))
        assert "cannot answer that question" in str(caught.value)

    def test_an_unrecognised_filter_is_refused_rather_than_ignored(self):
        """Silently dropping a filter hands the caller a WIDER population than it asked for,
        which is the one failure a bounded query exists to prevent (R1)."""
        a = adapter()
        with pytest.raises(ResponseUnavailable):
            a.fetch(Request("GetReservationKey", {"SomeFilterWeInvented": "x"}))

    def test_every_call_is_recorded_so_a_test_can_count_them(self):
        """R1. The call count is asserted, never assumed."""
        source = FrozenSource("sandbox2026")
        a = MiniHotelAdapter(TenantConfig.load("sandbox"), source)
        a.fetch(Request("GetReservationKey", {}))
        a.fetch(Request("getRooms", {}))
        assert len(source.calls) == 2


class TestTransportIndependence:
    def test_the_same_bytes_through_a_different_transport_give_identical_values(self):
        """The gate that proves nothing depends on the frozen path specifically - which is
        what makes a live transport a drop-in rather than a rewrite (slice 11)."""
        frozen = FrozenSource("sandbox2024")
        body = frozen.fetch(Request("GetReservationKey", {}))

        class ReplayTransport:
            """A stand-in for a live source: hands back bytes it was given."""
            calls = []

            def fetch(self, request):
                self.calls.append(request)
                return body

        tenant = TenantConfig.load("sandbox")
        a_frozen = MiniHotelAdapter(tenant, FrozenSource("sandbox2024"))
        a_replay = MiniHotelAdapter(tenant, ReplayTransport())

        records_frozen = a_frozen.records(
            a_frozen.fetch(Request("GetReservationKey", {})), "reservation")
        records_replay = a_replay.records(
            a_replay.fetch(Request("GetReservationKey", {})), "reservation")

        for one, two in zip(records_frozen, records_replay):
            for field_name in ("reservation.id", "reservation.status",
                               "reservation.arrival_date", "reservation.total_amount"):
                assert a_frozen.resolve(field_name, one) == a_replay.resolve(field_name, two)


class TestNoSiblingLeakThroughListWrappers:
    """The bug the capacity count caught, kept as a regression test.

    A record may climb to the record CONTAINING it, but a list wrapper is not a container in
    that sense - it is where the siblings live. Climbing into `<ArrayOfRnm_struct_room>` let a
    room with no configured capacity read the NEXT room's limit, which is R7's failure mode
    (a direct booking acquiring another booking's channel id) arriving through a different door.
    """

    def test_a_room_with_no_capacity_block_does_not_borrow_a_neighbours(self):
        a = adapter()
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        from hotelcontrols.providers.minihotel.paths import find_all
        without_block = [r for r in rooms
                         if not find_all(r.element, "rec_rooms_gst_max[rgm_gst_type=A]/rgm_max")]
        assert without_block, "the capture holds rooms with no adult-capacity block at all"
        for room in without_block:
            value = a.resolve("room.max_guests.adults", room)
            assert not value.is_known, (
                "a room with no capacity block must be UNKNOWN, not another room's number")

    def test_the_capacity_counts_match_the_capture_exactly(self):
        """21 rooms configured 0 (R12) plus 2 with no block at all = 23 unknown of 28."""
        a = adapter()
        rooms = a.records(a.fetch(Request("getRooms", {})), "room")
        from hotelcontrols.providers.minihotel.paths import find_all
        configured_zero = [r for r in rooms
                           if find_all(r.element,
                                       "rec_rooms_gst_max[rgm_gst_type=A]/rgm_max") == ["0"]]
        no_block = [r for r in rooms
                    if not find_all(r.element, "rec_rooms_gst_max[rgm_gst_type=A]/rgm_max")]
        assert (len(configured_zero), len(no_block), len(rooms)) == (21, 2, 28)
