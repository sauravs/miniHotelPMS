# -*- coding: utf-8 -*-
"""
A join on an absent key - issue #86.

The room join is `stay.room_number` -> `room.number`, and `evidence/reference.py` indexes and
looks up keys by `str(payload)`. Both ends were `absent_means: "false"`, so an absence on either
side became the string "False":

  * an UNASSIGNED stay joined to a room with NO NUMBER - both "False" - and was judged on that
    room's evidence. "A join never invents a match" is the module's own first rule;
  * with no such room, the unassigned stay read as a DEFINITE non-match, which `reference_exists`
    reports in control 1a's words for a stay assigned to a room the master does not hold - about
    a stay assigned to no room at all.

`stay.room_number`'s "false" is deliberate and stays: an empty one means "not yet assigned", and
every shipped rule joining on it scopes `stay.room_number exists` first, so it EXCLUDES those
stays. But the grammar compiles the same sentence without that clause, so a composed draft can
hold the unguarded form - which is what UNGUARDED below is. `room.number` has no such reason: a
room's number is its identity, and an empty one is missing evidence.

Found by the audit of #75's sixteen fields (follow-up 4). No committed capture has an unassigned
stay or a numberless room, so the documents are constructed, in each provider's own wire format.
"""
import copy

import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import gather
from hotelcontrols.evidence.budget import CallBudget
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import Request
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.spec import ControlIR, TenantConfig, load

AS_OF = "2026-07-08T09:00"
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}
ROOMS = {"minihotel": "getRooms", "demopms": "rooms"}
CONTROL = "room_assignment_type_validity"


# ---- each provider's documents ------------------------------------------------------------
def minihotel_room(number, room_type):
    return ('<rnm_struct_room is_mapped="true"><rm_serial>001</rm_serial>'
            '<rm_number>%s</rm_number><rm_type>%s</rm_type><rm_clsdt1 /><rm_clsdt2 />'
            '<rm_status>D</rm_status></rnm_struct_room>' % (number, room_type))


def minihotel(stay_room, rooms):
    booking = (
        '<Booking Portal_reservation_id="" Minihotel_reservation_id="007000009" type="Query" '
        'createDateTime="18/06/2026" Status="OK" ModifyAllowed="YES" NumofKeys="000" '
        'source="Web" arrival_time="14:00" departure_time="11:00" market_segment="" '
        'isGroupReservation="NO"><RoomStays><RoomStay roomNumber="%s" roomTypeID="DBL" '
        'roomTypeName="Double room" mealStatus="BB"></RoomStay></RoomStays>'
        '<ResGlobalInfo><GuestCount adult="1" child="0" baby="0" youth="0" />'
        '<Timespan arrival="10/07/2026" departure="12/07/2026" />'
        '<Total AmountAfterTaxes="300.00" CurrencyCode="USD" /></ResGlobalInfo></Booking>'
        % stay_room)
    return {
        "GetReservationKey": ('<?xml version="1.0" encoding="utf-8"?><Bookings>'
                              '<Hotel id="sandbox" />%s</Bookings>' % booking),
        "getRooms": ('<Response><ArrayOfRnm_struct_room>%s</ArrayOfRnm_struct_room></Response>'
                     % "".join(minihotel_room(n, t) for n, t in rooms)),
        "getRoomTypes": ('<Response><ArrayOfRoomTypes>'
                         '<RoomTypes><Type>DBL</Type><Description>Double room</Description>'
                         '</RoomTypes><RoomTypes><Type>STE</Type><Description>Suite'
                         '</Description></RoomTypes></ArrayOfRoomTypes></Response>'),
    }


def demopms(stay_room, rooms):
    booking = (
        '{"booking_ref": "007000009", "state": "BOOKED", "arrival": {"date": "10 Jul 2026", '
        '"time": "14:00"}, "departure": {"date": "12 Jul 2026"}, "created_on": "18 Jun 2026", '
        '"origin": {"external_ref": "", "channel": "Web"}, '
        '"total": {"amount": "300.00", "currency": "USD"}, "group_booking": false, '
        '"stays": [{"room_no": "%s", "room_class": "DBL", "board": "BB"}]}' % stay_room)
    room = ('{"room_no": "%s", "class": "%s", "out_of_service": {"from": null, "to": null}, '
            '"housekeeping": "CLEAN", "bookable": true, "limits": []}')
    return {
        "bookings": '{"schema": "demopms/v1", "endpoint": "bookings", "bookings": [%s]}'
                    % booking,
        "rooms": '{"schema": "demopms/v1", "endpoint": "rooms", "rooms": [%s]}'
                 % ", ".join(room % (n, t) for n, t in rooms),
        "room-types": ('{"schema": "demopms/v1", "endpoint": "room-types", "room_types": ['
                       '{"code": "DBL", "label": "Double room"}, '
                       '{"code": "STE", "label": "Suite"}]}'),
    }


DOCUMENTS = {"minihotel": minihotel, "demopms": demopms}
NUMBERED = [("01", "DBL")]
WITH_A_NUMBERLESS_ROOM = [("01", "DBL"), ("", "STE")]


class ByEndpoint:
    """One canned document per endpoint - a stand-in for a source, no network."""

    def __init__(self, bodies):
        self.bodies = bodies

    def fetch(self, request):
        return self.bodies[request.endpoint]


def guarded():
    return load(CONTROL)


def unguarded():
    """The shipped rule without `stay.room_number exists` - a draft the grammar accepts."""
    raw = copy.deepcopy(load(CONTROL).raw)
    raw["scope"] = [p for p in raw["scope"] if p["field"] != "stay.room_number"]
    assert len(raw["scope"]) == len(load(CONTROL).raw["scope"]) - 1
    return ControlIR(raw)


def judged(provider, ir, stay_room, rooms):
    tenant = TenantConfig.load(PROPERTY[provider])
    package = next(p for p in all_providers() if p.name == provider)
    adapter = package.adapter(tenant, ByEndpoint(DOCUMENTS[provider](stay_room, rooms)))
    evidence = gather(ir, adapter, tenant, FixedClock.at(AS_OF, tenant.timezone),
                      CallBudget(50))
    [bundle] = evidence.bundles
    [verdict] = evaluate_population(ir, evidence.bundles, tenant.settings)
    return bundle, verdict


@pytest.mark.parametrize("provider", sorted(DOCUMENTS))
class TestAnAbsentKeyNeverJoins:

    def test_a_room_with_no_number_has_an_unknown_number_never_a_known_false(self, provider):
        """A room's number is its identity (IDENTITY_FIELD): an empty one is missing evidence."""
        tenant = TenantConfig.load(PROPERTY[provider])
        package = next(p for p in all_providers() if p.name == provider)
        adapter = package.adapter(tenant, ByEndpoint(
            DOCUMENTS[provider]("01", WITH_A_NUMBERLESS_ROOM)))
        rooms = adapter.records(adapter.fetch(Request(ROOMS[provider], {})), "room")
        numbers = [adapter.resolve("room.number", r) for r in rooms]
        assert [v.is_known for v in numbers] == [True, False]
        assert numbers[1].reason, "an UNKNOWN must say why"

    def test_an_unassigned_stay_never_acquires_a_numberless_rooms_evidence(self, provider):
        """The defect: both keys were "False", so the stay read room.type `ste` - the
        numberless room's - and was FAILed on it. A join never invents a match."""
        bundle, verdict = judged(provider, unguarded(), "", WITH_A_NUMBERLESS_ROOM)
        assert not bundle.fields["room.type"].is_known
        assert not bundle.joins["room"].is_known
        assert verdict.outcome.value == "UNKNOWN"

    def test_an_unassigned_stay_is_not_a_definite_non_match(self, provider):
        """Without that room it read "room.number does not resolve in this property's room
        records" - control 1a's FAIL for a stay assigned to a room the master does not hold.
        This stay is assigned to no room; that is not established either way."""
        bundle, verdict = judged(provider, unguarded(), "", NUMBERED)
        assert not bundle.joins["room"].is_known
        assert "stay.room_number" in bundle.joins["room"].reason
        assert verdict.outcome.value == "UNKNOWN"

    def test_the_shipped_rule_still_excludes_an_unassigned_stay(self, provider):
        """Unchanged: the shipped scope asks `stay.room_number exists`, and an absent one is
        the deliberate "not yet assigned" - EXCLUDED, never a gap."""
        _bundle, verdict = judged(provider, guarded(), "", WITH_A_NUMBERLESS_ROOM)
        assert verdict.outcome.value == "EXCLUDED"

    def test_an_assigned_stay_still_joins_its_room(self, provider):
        bundle, verdict = judged(provider, unguarded(), "01", WITH_A_NUMBERLESS_ROOM)
        assert bundle.joins["room"].is_known and bundle.joins["room"].payload is True
        assert str(bundle.fields["room.type"].payload).casefold() == "dbl"
        assert verdict.outcome.value == "PASS"
