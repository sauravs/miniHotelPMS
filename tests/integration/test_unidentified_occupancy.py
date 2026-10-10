# -*- coding: utf-8 -*-
"""
An occupancy segment with no reservation id - issue #84.

`occupancy.reservation_id` is the IDENTITY `resource_occupancy_consistency` checks overlaps by:
`no_overlap` skips a pair whose identities are equal, because one reservation cannot double-book
itself (007003204 holds two segments in room 303). It was declared `absent_means: "false"`, so an
EMPTY id resolved to a known `False` - and two id-less segments in one room were the same
reservation "False", never compared, and PASSed "alone" while overlapping each other. A real
double-booking, reported clean.

Found by the audit of #75's sixteen fields (follow-up 4). No committed capture has an id-less
segment, so the documents below are constructed - the smallest that show it, in each provider's
own wire format: two id-less segments overlapping in room 303, and one identified segment alone
in room 304 whose PASS must not move.

An id-less segment is missing evidence: UNKNOWN, through both providers (criterion 7).
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
<Rooms><Room Number="303" Rmtype="DBL" /><Room Number="304" Rmtype="DBL" /></Rooms>
<RoomsTypes><RoomType Code="DBL" Description="Double room" /></RoomsTypes>
<Reservations>
<Reservation ResNumber="" RoomNumber="303" RoomType="DBL" FromYmd="20260708" ToYmd="20260713" RoomsQty="0001" Status="IN" Board="HB" />
<Reservation ResNumber="" RoomNumber="303" RoomType="DBL" FromYmd="20260709" ToYmd="20260712" RoomsQty="0001" Status="IN" Board="HB" />
<Reservation ResNumber="007004351" RoomNumber="304" RoomType="DBL" FromYmd="20260708" ToYmd="20260710" RoomsQty="0001" Status="IN" Board="HB" />
</Reservations>
</AvailRaters>"""

DEMOPMS = """{
  "schema": "demopms/v1",
  "endpoint": "occupancy",
  "rooms": [
    {"room_no": "303", "occupancy": [
      {"booking_ref": "", "from": "08 Jul 2026", "to": "13 Jul 2026", "state": "IN_HOUSE"},
      {"booking_ref": "", "from": "09 Jul 2026", "to": "12 Jul 2026", "state": "IN_HOUSE"}]},
    {"room_no": "304", "occupancy": [
      {"booking_ref": "007004351", "from": "08 Jul 2026", "to": "10 Jul 2026", "state": "IN_HOUSE"}]}
  ]
}"""

DOCUMENTS = {"minihotel": MINIHOTEL, "demopms": DEMOPMS}
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}
ENDPOINT = {"minihotel": "RoomStatusInquiry", "demopms": "occupancy"}
AS_OF = "2026-07-08T09:00"


class Canned:
    """Hands back one document whatever it is asked - a stand-in for a source, no network."""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def fetch(self, request):
        self.calls.append(request)
        return self.body


def subject(provider, body=None):
    tenant = TenantConfig.load(PROPERTY[provider])
    package = next(p for p in all_providers() if p.name == provider)
    return tenant, package.adapter(tenant, Canned(body or DOCUMENTS[provider]))


def verdicts(provider, body=None):
    tenant, adapter = subject(provider, body)
    result = run("resource_occupancy_consistency", tenant, adapter,
                 FixedClock.at(AS_OF, tenant.timezone))
    return result.verdicts


@pytest.mark.parametrize("provider", sorted(DOCUMENTS))
class TestAnIdLessSegment:

    def test_its_reservation_id_is_unknown_never_a_known_false(self, provider):
        """CLAUDE.md, never widen: an empty reservation id is missing evidence (#84)."""
        _tenant, adapter = subject(provider)
        segments = adapter.records(adapter.fetch(Request(ENDPOINT[provider], {})), "occupancy")
        ids = [adapter.resolve("occupancy.reservation_id", s) for s in segments]
        assert [v.is_known for v in ids] == [False, False, True]
        assert ids[2].payload == "007004351"
        assert all(v.reason for v in ids[:2]), "an UNKNOWN must say why"

    def test_two_id_less_segments_that_overlap_do_not_pass(self, provider):
        """The defect: both PASSed "False holds occupancy.room_number 303 alone" while
        overlapping each other. Neither identity is established, so neither can be cleared."""
        outcomes = Counter((v.record_id, v.outcome.value) for v in verdicts(provider))
        assert outcomes == Counter({(None, "UNKNOWN"): 2, ("007004351", "PASS"): 1})

    def test_an_id_less_segment_is_never_named_false(self, provider):
        """It was the record's identity too (IDENTITY_FIELD), so the verdict was filed under
        the boolean False - a name no front office can open."""
        assert not any(v.record_id is False for v in verdicts(provider))

    def test_an_identified_neighbour_of_an_id_less_segment_does_not_pass(self, provider):
        """The other side of the same gap. An id-less segment overlapping 007004343 might be a
        second reservation (a double-booking) or 007004343's own split segment (no conflict at
        all, as 007003204 shows). Neither is established, so 007004343 is not cleared."""
        if provider == "minihotel":
            body = MINIHOTEL.replace('ResNumber="" RoomNumber="303" RoomType="DBL" '
                                     'FromYmd="20260708"',
                                     'ResNumber="007004343" RoomNumber="303" RoomType="DBL" '
                                     'FromYmd="20260708"')
        else:
            body = DEMOPMS.replace('{"booking_ref": "", "from": "08 Jul 2026"',
                                   '{"booking_ref": "007004343", "from": "08 Jul 2026"')
        assert "007004343" in body
        outcomes = Counter((v.record_id, v.outcome.value) for v in verdicts(provider, body))
        assert outcomes == Counter({("007004343", "UNKNOWN"): 1, (None, "UNKNOWN"): 1,
                                    ("007004351", "PASS"): 1})
