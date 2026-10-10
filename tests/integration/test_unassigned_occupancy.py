# -*- coding: utf-8 -*-
"""
An occupancy segment with no room assigned - issue #75.

`occupancy.room_number` is the key `resource_occupancy_consistency` groups by. It was declared
`absent_means: "false"`, so an EMPTY room number resolved to a known `False`, and every
unassigned segment landed in one shared "room" called False. Two of them with overlapping dates
then FAILed against each other; one on its own would have PASSed - a verdict about a room nobody
established. The refresh capture of v3 slice 23 found the live case: reservations 007004312 and
007004313, both checked in for 2026-07-08..07-13, neither with a room.

An unassigned segment is missing evidence, so it is UNKNOWN, and it is UNKNOWN through both
providers (criterion 7). The documents below are the smallest that show it, in each provider's
own wire format: two unassigned segments that overlap, and one assigned segment that does not.
"""
from collections import Counter

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import Request
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig

MINIHOTEL = """<?xml version="1.0" encoding="UTF-8" ?>
<AvailRaters>
<Hotel id="h" />
<DateRange from="2026-07-08" to="2026-07-15" />
<Rooms><Room Number="303" Rmtype="DBL" /></Rooms>
<RoomsTypes><RoomType Code="DBL" Description="Double room" /></RoomsTypes>
<Reservations>
<Reservation ResNumber="007004312" RoomNumber="" RoomType="" FromYmd="20260708" ToYmd="20260713" RoomsQty="0001" Status="IN" Board="HB" />
<Reservation ResNumber="007004313" RoomNumber="" RoomType="" FromYmd="20260708" ToYmd="20260713" RoomsQty="0001" Status="IN" Board="HB" />
<Reservation ResNumber="007004351" RoomNumber="303" RoomType="DBL" FromYmd="20260708" ToYmd="20260710" RoomsQty="0001" Status="IN" Board="HB" />
</Reservations>
</AvailRaters>"""

# The nested form, as `tools/transcode_demopms.py` writes an unassigned segment: under a room
# whose number is empty, because this wire format has nowhere else to put it.
DEMOPMS = """{
  "schema": "demopms/v1",
  "endpoint": "occupancy",
  "rooms": [
    {"room_no": "", "occupancy": [
      {"booking_ref": "007004312", "from": "08 Jul 2026", "to": "13 Jul 2026", "state": "IN_HOUSE"},
      {"booking_ref": "007004313", "from": "08 Jul 2026", "to": "13 Jul 2026", "state": "IN_HOUSE"}]},
    {"room_no": "303", "occupancy": [
      {"booking_ref": "007004351", "from": "08 Jul 2026", "to": "10 Jul 2026", "state": "IN_HOUSE"}]}
  ]
}"""

DOCUMENTS = {"minihotel": MINIHOTEL, "demopms": DEMOPMS}
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}


class Canned:
    """Hands back one document whatever it is asked - a stand-in for a source, no network."""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def fetch(self, request):
        self.calls.append(request)
        return self.body


def subject(provider):
    tenant = TenantConfig.load(PROPERTY[provider])
    package = next(p for p in all_providers() if p.name == provider)
    return tenant, package.adapter(tenant, Canned(DOCUMENTS[provider]))


@pytest.mark.parametrize("provider", sorted(DOCUMENTS))
class TestAnUnassignedSegment:

    def test_its_room_number_is_unknown_never_a_known_false(self, provider):
        """CLAUDE.md, never widen: an empty room number is missing evidence (#75)."""
        _tenant, adapter = subject(provider)
        endpoint = "RoomStatusInquiry" if provider == "minihotel" else "occupancy"
        segments = adapter.records(adapter.fetch(Request(endpoint, {})), "occupancy")
        rooms = {adapter.resolve("occupancy.reservation_id", s).payload:
                 adapter.resolve("occupancy.room_number", s) for s in segments}
        assert not rooms["007004312"].is_known and not rooms["007004313"].is_known
        assert rooms["007004351"].is_known and rooms["007004351"].payload == "303"

    def test_two_unassigned_segments_are_not_an_overlap_in_a_shared_room(self, provider):
        """The live case: they were FAILed against each other in a room called False."""
        tenant, adapter = subject(provider)
        result = run("resource_occupancy_consistency", tenant, adapter,
                     FixedClock.at("2026-07-08T09:00", tenant.timezone))
        outcomes = {v.record_id: v.outcome.value for v in result.verdicts}
        assert outcomes["007004312"] == "UNKNOWN"
        assert outcomes["007004313"] == "UNKNOWN"
        assert outcomes["007004351"] == "PASS"

    def test_a_lone_unassigned_segment_does_not_pass(self, provider):
        """The other direction, and the one never-widen is about: alone in the "False" group,
        an unassigned segment used to PASS a check about a room nobody established."""
        tenant, adapter = subject(provider)
        if provider == "minihotel":
            body = MINIHOTEL.replace(
                '<Reservation ResNumber="007004313" RoomNumber="" RoomType="" FromYmd="20260708" '
                'ToYmd="20260713" RoomsQty="0001" Status="IN" Board="HB" />\n', "")
        else:
            body = DEMOPMS.replace(
                ',\n      {"booking_ref": "007004313", "from": "08 Jul 2026", "to": "13 Jul 2026",'
                ' "state": "IN_HOUSE"}', "")
        assert "007004313" not in body
        adapter.source.body = body
        result = run("resource_occupancy_consistency", tenant, adapter,
                     FixedClock.at("2026-07-08T09:00", tenant.timezone))
        outcomes = Counter((v.record_id, v.outcome.value) for v in result.verdicts)
        assert outcomes == Counter({("007004312", "UNKNOWN"): 1, ("007004351", "PASS"): 1})
