# -*- coding: utf-8 -*-
"""
RECORD BOUNDARIES - where one DemoPMS record ends and the next begins.

The same structural knowledge `minihotel/records.py` holds, for a wire format where a record is
an object in an array rather than an element in a tree. Getting it wrong pairs field 3 of
booking 1 with field 7 of booking 2, so it lives here explicitly, per (endpoint, entity), and
is never inferred.

A RECORD MAY READ UPWARDS, NEVER SIDEWAYS - AND JSON MAKES THAT EASIER TO GUARANTEE
-----------------------------------------------------------------------------------
MiniHotel's version has to be careful: XML gives every element the same shape, so a room with
no capacity block could climb into `<ArrayOfRnm_struct_room>` and read the NEXT room's limit -
a sibling leak wearing an ancestor's clothes, which happened and cost two rooms their true
capacity before a test caught it.

Here a record's ancestors are the objects that literally contain it, collected while cutting,
and an array is not a readable node. So an ancestor is always a genuine container. What still
has to be prevented is a record resolving a path that belongs to a DIFFERENT branch of the
response - `paths.strip_prefix` returns None for those, and the resolver walks on rather than
reading a stranger's value. That is R7 in this wire format's terms.

THE QUIRK THAT MATTERS HERE: OCCUPANCY IS NESTED, NOT SIBLING
--------------------------------------------------------------
MiniHotel returns rooms and reservations as two sibling lists, so an occupancy segment carries
its own room number and stands alone. DemoPMS nests each segment inside the room it belongs to,
so an occupancy record has NO room number of its own and must read it from the room containing
it. That is the upward walk being exercised in a shape the other provider never produces - and
the canonical answer, `occupancy.room_number`, is identical either way, which is the entire
point of the boundary above.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import RecordBoundaryUnknown
from .paths import find_all

# (endpoint, entity) -> the path selecting one node per record, in the paths.py grammar.
RECORD_SELECTORS: dict[tuple[str, str], str] = {
    ("bookings", "reservation"): "bookings[]",
    ("bookings", "stay"): "bookings[].stays[]",
    ("rooms", "room"): "rooms[]",
    ("room-types", "room_type"): "room_types[]",
    ("ledger", "folio"): "ledger",
    ("ledger", "folio_transaction"): "ledger.postings[]",
    # The nested quirk. One room-date segment per element, inside its room.
    ("occupancy", "occupancy"): "rooms[].occupancy[]",
}

# How a record of each entity identifies itself, in canonical names. Identical to the other
# provider's table, because this is a statement about the CANONICAL vocabulary rather than
# about either API: a stay is identified by the reservation it belongs to on any PMS.
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

    `prefix` is the path this record was cut at, and it is what makes anchoring explicit. An
    XML element knows its own tag, so MiniHotel can trim a path by looking for it; a JSON
    object knows nothing about itself - `{"room_no": "01"}` could be a room, a stay or an
    occupancy segment - so the record has to carry where it came from.

    `ancestors` is the chain of containing OBJECTS, nearest first, excluding the document root.
    The root is excluded deliberately: including it would let a stay resolve
    `bookings[].booking_ref` from the top of the response and get the FIRST booking's
    reference, which is precisely the sideways read R7 describes.
    """

    endpoint: str
    node: Any
    entity: str | None = None
    prefix: str = ""
    ancestors: tuple[tuple[str, Any], ...] = ()

    @property
    def is_whole_response(self) -> bool:
        """A response nobody has cut yet."""
        return self.entity is None

    @property
    def lineage(self) -> tuple[tuple[str, Any], ...]:
        """This record, then every object containing it, each with the path it sits at."""
        return ((self.prefix, self.node),) + self.ancestors

    def __repr__(self) -> str:
        return "Record(%s %s)" % (self.endpoint, self.entity or "<whole response>")


def cut(document: Any, endpoint: str, entity: str) -> list[Record]:
    """Every record of `entity` in this response, each knowing what encloses it."""
    frontier: list[tuple[tuple, Any, str]] = [((), document, "")]

    for step in selector_for(endpoint, entity).split("."):
        found: list[tuple[tuple, Any, str]] = []
        for chain, node, prefix in frontier:
            # The node being descended FROM becomes an ancestor of everything below it - unless
            # it is the document root, which contains every record equally and is therefore no
            # record's container.
            enclosing = chain + (((prefix, node),) if prefix and isinstance(node, dict) else ())
            child_prefix = step if not prefix else "%s.%s" % (prefix, step)
            for child in find_all(node, step):
                found.append((enclosing, child, child_prefix))
        frontier = found

    return [Record(endpoint, node, entity, prefix, tuple(reversed(chain)))
            for chain, node, prefix in frontier]


def selector_for(endpoint: str, entity: str) -> str:
    try:
        return RECORD_SELECTORS[(endpoint, entity)]
    except KeyError:
        raise RecordBoundaryUnknown(
            "this engine cannot cut a %s response into %r records - the response has no single "
            "object per record, and pairing the wrong ones would be worse than declining"
            % (endpoint, entity)) from None
