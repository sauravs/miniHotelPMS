# -*- coding: utf-8 -*-
"""
RECORD BOUNDARIES - where one record ends and the next begins.

This is the one piece of provider-shaped knowledge that is structural rather than per-field,
and getting it wrong pairs field 3 of booking 1 with field 7 of booking 2. So it lives here,
explicitly, per (endpoint, entity) - never inferred.

A `Record` keeps a reference to the record CONTAINING it, and to nothing else. That asymmetry
is deliberate and is pinned by a test:

  * A room stay's amount sits inside its own <RoomStay> block while the currency it is
    denominated in sits on the <Booking> above it, and a stay-entity control needs the
    reservation's id and status too. So a record may read upwards.
  * A record may NEVER read a sibling. R7 is why: 7 of 11 sandbox bookings are direct and carry
    no portal id at all, and a resolver that wandered sideways looking for a better answer
    would hand one booking another booking's channel confirmation - the quietest possible way
    to report a duplicate that does not exist.

ON OCCUPANCY (issue #3)
-----------------------
v1 declared this entity to have no record boundary, reasoning that rooms and reservations are
sibling lists and one reservation appears as several date segments. Opening the response
disproves it: every <Reservation> element carries RoomNumber, ResNumber, FromYmd, ToYmd and
Status on ITSELF. It is a complete occupancy segment, and several segments per reservation is
exactly what an overlap check wants. v1's provider map sourced occupancy.room_number from the
room master list instead, and the conclusion followed from the mapping rather than the data.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..base import RecordBoundaryUnknown

# (endpoint, entity) -> the path selecting one element per record, in the paths.py grammar.
RECORD_SELECTORS: dict[tuple[str, str], str] = {
    ("GetReservationKey", "reservation"): "Booking",
    ("GetReservationKey", "stay"): "RoomStay",
    ("getRooms", "room"): "rnm_struct_room",
    ("getRoomTypes", "room_type"): "RoomTypes",
    ("GetReservationBalance", "folio"): "Balance",
    ("GetReservationBalance", "folio_transaction"): "Transaction",
    # Issue #3. Each <Reservation> is one room-date segment and carries its own room number.
    ("RoomStatusInquiry", "occupancy"): "Reservations/Reservation",
    ("BulkARI", "rate_plan"): "RoomTypes",
}

# How a record of each entity identifies itself, in canonical names. For a stay it is the
# reservation the stay belongs to, which sits on the record above it - hence the upward walk.
IDENTITY_FIELD: dict[str, str] = {
    "reservation": "reservation.id",
    "stay": "reservation.id",
    "room": "room.number",
    "room_type": "room_type.code",
    "folio": "reservation.id",
    "occupancy": "occupancy.reservation_id",
    "rate_plan": "rate_plan.code",
}


@dataclass(frozen=True, slots=True)
class Record:
    """One record cut from a response, or a whole response treated as one.

    Opaque above the provider layer: a caller may hold one and hand it back, and may ask the
    adapter about it, but may not read it.

    `ancestors` is the chain of enclosing elements that are THEMSELVES RECORD BOUNDARIES for
    this endpoint, nearest first. That is the record-isolation rule made mechanical:

      * A <RoomStay> can reach the <Booking> that contains it, because the currency its amount
        is denominated in lives up there (R9) and a stay-entity control needs the reservation's
        id and status too.
      * It climbs ONLY through record-shaped ancestors, never through list wrappers. This is
        the subtlety, and a test caught it: "stop before the document root" is not enough,
        because <ArrayOfRnm_struct_room> is not the root. A room with no configured capacity
        block climbed into that wrapper and found ANOTHER ROOM'S capacity - a sibling leak
        wearing an ancestor's clothes, and exactly the failure R7 describes for channel ids.
        Two rooms silently acquired a neighbour's occupancy limit before the count came out
        at 21 instead of the 23 the captures actually hold.

    v1 tracked this by nesting Record objects, which meant a record cut straight out of a
    response had the response as its parent and could not see the element that actually
    contained it. Ancestry through record boundaries is what the rule was always describing.
    """

    endpoint: str
    element: ET.Element
    entity: str | None = None
    ancestors: tuple[ET.Element, ...] = ()

    @property
    def is_whole_response(self) -> bool:
        """A response nobody has cut yet."""
        return self.entity is None

    @property
    def lineage(self) -> tuple[ET.Element, ...]:
        """This element, then everything containing it, up to but excluding the root."""
        return (self.element,) + self.ancestors

    def __repr__(self) -> str:
        return "Record(%s %s)" % (self.endpoint, self.entity or "<whole response>")


def ancestry(root: ET.Element) -> dict[int, ET.Element]:
    """child id -> parent element, for one response. Built once, because ElementTree keeps no
    parent pointers and walking the tree per lookup would be quadratic."""
    return {id(child): parent for parent in root.iter() for child in parent}


def record_tags(endpoint: str) -> frozenset[str]:
    """Element names that are record boundaries for this endpoint.

    Only these may be climbed into. Anything else enclosing a record is a list wrapper, and
    reading from a list wrapper is reading a sibling.
    """
    return frozenset(selector.split("/")[-1].split("[")[0]
                     for (name, _entity), selector in RECORD_SELECTORS.items()
                     if name == endpoint)


def selector_for(endpoint: str, entity: str) -> str:
    try:
        return RECORD_SELECTORS[(endpoint, entity)]
    except KeyError:
        raise RecordBoundaryUnknown(
            "this engine cannot cut a %s response into %r records - the response has no single "
            "block per record, and pairing the wrong ones would be worse than declining"
            % (endpoint, entity)) from None
