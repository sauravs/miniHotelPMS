# -*- coding: utf-8 -*-
"""
THE LIVE REQUEST FORM - what one of these calls actually looks like on the wire.

This is adapter knowledge and it lives here for the same reason every other quirk does: above
this directory nothing may know that a request is XML, that authentication is two attributes on
an element, or that one of these endpoints is selected by a response-type code rather than by
its own path. The transport carries a body it did not write to a URL it did not compose.

WHERE THESE FORMS COME FROM, AND WHY THAT MATTERS
--------------------------------------------------
Every request below is TRANSCRIBED FROM A CALL THAT ACTUALLY WORKED - the calls that produced
the responses in `fixtures/minihotel/`. Not from documentation. The vendor's docs never state
how to encode a request at all, and probing the WSDL showed the operations declare empty
parameter types:

    <s:element name="getRooms"><s:complexType /></s:element>

which means the service reads the raw request body rather than named parameters. So: POST the
plain XML as the body with `Content-Type: text/xml`. That was discovered by trying it, and it
is the kind of thing that makes "do not trust documentation over a captured response" a rule in
this project rather than a slogan.

Two consequences worth stating plainly.

**`BulkARI` is refused.** Its response is in the fixture set; the request that produced it was
not recorded, so the form is not known. Guessing at it would be inventing a request to somebody
else's server, which is worse than an unbuildable control - and `rate_room_category_consistency`
is structurally unresolvable anyway (R13, open question 1.6).

**An occupancy query with no window is refused.** The vendor asks integrators not to query wide
ranges without prior agreement (R8), and the ARI endpoint with no `DateRange` is exactly that
query. The reference join asks for occupancy with no parameters, which is fine against a frozen
capture and is not a thing to send to a live server.

**Nothing here has been re-verified since the captures were taken.** The sandbox has moved on
once already (open question 1.2). A live call is approved individually, bounded and staged
(decision D3), and `tools/probe.py` prints its plan before making one.
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from ..base import Request, ResponseUnavailable
from ..transport import Credentials, HttpCall

# Endpoint -> the path it is POSTed to. Two different API generations in one vendor: the older
# `.asmx` services, the newer `/api/Agents/...` one, and a third that is not selected by path
# at all.
PATHS = {
    "getRoomTypes": "/agents/ws/settings/rooms/RoomsMain.asmx/getRoomTypes",
    "getRooms": "/agents/ws/settings/rooms/RoomsMain.asmx/getRooms",
    "GetReservationKey": "/api/Agents/Sci/Reservation/GetReservationKey",
    "GetReservationBalance": "/agents/ws/sci/sciMain.asmx/GetReservationBalance",
    "RoomStatusInquiry": "/gds",
}

CONTENT_TYPE = "text/xml; charset=utf-8"
HEADERS = {
    "Content-Type": CONTENT_TYPE,
    "Accept": "text/xml,application/xml,*/*",
    "User-Agent": "hotelcontrols/2",
}

# Reservation-query filters that are a date window, and the element each is written as.
DATE_FILTERS = ("ArrivalDate", "DepartureDate", "CreateDate")

# Filters that widen or narrow the CONTENT of each record rather than selecting records.
CONTENT_FLAGS = ("IncludeRoomPrices", "IncludeHouseKeepingRemarks", "Cancellations",
                 "NotIncludeModifications", "Prices")


def encode(request: Request, credentials: Credentials) -> HttpCall:
    """One canonical-layer `Request` as the call this vendor actually accepts."""
    if request.endpoint not in PATHS:
        raise ResponseUnavailable(
            "no request form for %r has ever been captured, so this engine does not know how "
            "to ask for it. Its response is in the fixture set; the question that produced it "
            "was not recorded, and guessing at a request to somebody else's server is worse "
            "than an unbuildable control" % (request.endpoint,))

    builder = _BUILDERS[request.endpoint]
    return HttpCall("POST", credentials.base_url.rstrip("/") + PATHS[request.endpoint],
                    dict(HEADERS), builder(request, credentials))


# --------------------------------------------------------------------------- bodies
def _settings_call(name: str, extra: str = "") -> str:
    """The older `.asmx` shape: everything nested inside a named `<Settings>` wrapper."""
    def build(request: Request, credentials: Credentials) -> str:
        _refuse_unknown(request, allowed=())
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Request>\n"
            "    <Settings name=%s>\n"
            "    %s\n"
            "    %s\n%s"
            "</Settings>\n"
            "</Request>" % (quoteattr(name), _authentication(credentials),
                            _hotel(credentials), extra))
    return build


def _reservations(request: Request, credentials: Credentials) -> str:
    """The newer shape, and the only endpoint that takes a window.

    An unknown filter RAISES rather than being dropped. Silently ignoring one hands back a
    WIDER population than the control asked for, which is the single failure a bounded query
    exists to prevent (R1) - and a wider population against a live server is also the wide
    range the vendor asked us not to send (R8).
    """
    _refuse_unknown(request, allowed=DATE_FILTERS + CONTENT_FLAGS + ("BookingSearch",))

    lines = ["\t%s" % _authentication(credentials), "\t%s" % _hotel(credentials)]
    for name in DATE_FILTERS:
        window = request.params.get(name)
        if window:
            lines.append('\t<%s From=%s To=%s />'
                         % (name, quoteattr(str(window.get("From", ""))),
                            quoteattr(str(window.get("To", "")))))
    search = request.params.get("BookingSearch") or {}
    for key, value in sorted(search.items()):
        lines.append("\t<BookingSearch %s=%s />" % (key, quoteattr(str(value))))
    for flag in CONTENT_FLAGS:
        if flag in request.params:
            lines.append("\t<%s>%s</%s>"
                         % (flag, escape(_boolean(request.params[flag])), flag))

    return ('<?xml version="1.0" encoding="UTF-8"?>\n<GetReservationKey>\n%s\n'
            "</GetReservationKey>" % "\n".join(lines))


def _balance(request: Request, credentials: Credentials) -> str:
    """One reservation per call. R1, and the main scalability constraint on the whole design."""
    _refuse_unknown(request, allowed=("ReservationNumber",))
    number = request.params.get("ReservationNumber")
    if not number:
        raise ResponseUnavailable(
            "a folio call names one reservation and there is no bulk journal endpoint (R1); "
            "asking for all of them is not a call this API has")
    return ("<Request>\n<Payment language=\"ENG\">\n\t%s\n\t%s\n"
            "\t<ReservationNumber>%s</ReservationNumber>\n</Payment>\n</Request>"
            % (_hotel(credentials), _authentication(credentials), escape(str(number))))


def _occupancy(request: Request, credentials: Credentials) -> str:
    """The ARI endpoint, selected by `ResponseType` rather than by its path.

    A window is REQUIRED here. The reference join asks for occupancy with no parameters, which
    is a perfectly good question to put to a frozen capture and is exactly the wide, unbounded
    range the vendor asked integrators not to send to a live server (R8).
    """
    _refuse_unknown(request, allowed=("DateRange",))
    window = request.params.get("DateRange") or {}
    if not (window.get("from") and window.get("to")):
        raise ResponseUnavailable(
            "an occupancy query with no date window asks this property for everything it has. "
            "The vendor asks integrators not to query wide ranges without prior agreement "
            "(R8), so it is refused here rather than sent")
    return ('<?xml version="1.0" encoding="UTF-8" ?>\n'
            '<AvailRaters xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '<Authentication username=%s password=%s ResponseType="03" />\n'
            "%s\n"
            "<DateRange from=%s to=%s />\n"
            "</AvailRaters>"
            % (quoteattr(credentials.user), quoteattr(credentials.password),
               _hotel(credentials), quoteattr(str(window["from"])),
               quoteattr(str(window["to"]))))


_BUILDERS = {
    "getRoomTypes": _settings_call("getRoomTypes"),
    # An EMPTY room number means "every room" - the documented way to fetch the whole room
    # master in one call rather than iterating room by room. It is also the one place in this
    # file where an empty element is meaningful rather than lazy.
    "getRooms": _settings_call("getRooms", extra="    <room_number></room_number>\n"),
    "GetReservationKey": _reservations,
    "GetReservationBalance": _balance,
    "RoomStatusInquiry": _occupancy,
}


# --------------------------------------------------------------------------- helpers
def _authentication(credentials: Credentials) -> str:
    return "<Authentication username=%s password=%s />" % (
        quoteattr(credentials.user), quoteattr(credentials.password))


def _hotel(credentials: Credentials) -> str:
    return "<Hotel id=%s />" % quoteattr(credentials.hotel)


def _boolean(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _refuse_unknown(request: Request, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(request.params) - set(allowed))
    if unknown:
        raise ResponseUnavailable(
            "%s has no captured request form carrying %s, so this engine cannot ask for it "
            "without inventing one" % (request.endpoint, ", ".join(repr(u) for u in unknown)))
