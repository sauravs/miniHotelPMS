# -*- coding: utf-8 -*-
"""
FROZEN SOURCE - captured responses, replayed as if the server had answered.

No network, ever. `fixtures/minihotel/` holds real responses, pseudonymised, listed with the
captures they belong to in its `index.json` - the list, rather than a count in prose that goes
stale with the next capture (#106). They are the test evidence and the ground truth. MiniHotel
asks integrators not to query wide date ranges without agreement (R8), and a suite that needs
someone else's server to be up is not a suite.

TWO THINGS THIS DOES THAT v1's DID NOT
--------------------------------------
1. IT KNOWS WHAT EACH FIXTURE WAS ASKED. `index.json` records the request that produced every
   response. v1 replayed filters against a fixture without that, so a control querying a window
   the capture never covered got an empty population - which on screen is indistinguishable
   from "no violations" (review finding F19c). Here, a request whose window is not covered by
   the capture RAISES, because "no data" and "nothing wrong" are different answers.

2. IT REPLAYS FILTERS THE WAY THE LIVE SERVER WOULD. A frozen file was captured with ONE set of
   parameters and a control asks with another, so the narrowing has to happen somewhere. It
   belongs here, in the provider adapter, because knowing that `DepartureDate` narrows on
   `<Timespan departure=...>` is MiniHotel knowledge. Above this layer the filters are opaque
   data carried in the IR.
"""
from __future__ import annotations

import json
import pathlib
import xml.etree.ElementTree as ET
from typing import Any

from ..base import Request, ResponseUnavailable
from .paths import parse_document
from .transforms import date_ddmmyyyy_to_iso

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[3] / "fixtures" / "minihotel"

# Where each booking-level date filter reads from, on one <Booking> element. This table is
# about REPLAYING a filter - narrowing the captured bookings the way the server would have -
# and it is deliberately NOT the list of filters the window guard checks. Issue #9 is what
# happens when those two are the same list: the occupancy endpoint's window is spelled
# `DateRange {from,to}`, appears in no table here, and was replayed entirely unguarded.
BOOKING_DATE_FILTERS = {
    "ArrivalDate": ("ResGlobalInfo/Timespan", "arrival"),
    "DepartureDate": ("ResGlobalInfo/Timespan", "departure"),
    "CreateDate": (None, "createDateTime"),
}

# The two spellings a date window arrives in. MiniHotel writes `From`/`To` on the booking
# filters and `from`/`to` on the occupancy one, in the same API.
WINDOW_BOUNDS = (("From", "To"), ("from", "to"))

# Request options that widen or narrow the CONTENT of each record rather than selecting
# records. The captures were taken with prices included, so honouring them is a no-op.
REQUEST_OPTIONS = {"IncludeRoomPrices", "IncludeHouseKeepingRemarks", "Cancellations",
                   "NotIncludeModifications", "Prices"}


class FrozenSource:
    """Replays captured responses. `calls` records every request, so a test can ASSERT the call
    count rather than assume it (R1) - the regression guard the whole design rests on."""

    def __init__(self, capture: str = "sandbox2026",
                 fixture_dir: pathlib.Path | str = FIXTURE_DIR):
        self.fixture_dir = pathlib.Path(fixture_dir)
        self.index = json.loads((self.fixture_dir / "index.json").read_text(encoding="utf-8"))
        if capture not in self.index["captures"]:
            raise ResponseUnavailable("no capture called %r" % (capture,))
        self.capture = capture
        self.calls: list[Request] = []

    @property
    def origin(self) -> str:
        meta = self.index["captures"][self.capture]
        return "%s (%s), captured %s, pseudonymised" % (
            self.capture, meta["label"], meta["captured_at"])

    @property
    def as_of(self) -> str:
        return self.index["captures"][self.capture]["as_of"]

    @property
    def observed_at(self) -> str:
        """The date these responses were OBTAINED, as the index recorded it.

        Different from `as_of`, and the difference is the whole of finding F7's freshness half:
        `as_of` is the date the evidence describes, `observed_at` is when the bytes were
        actually fetched. A control asking for evidence under an hour old is asking about the
        second one, and a replayed capture is honestly stale against it - which the run says
        rather than hides.
        """
        return self.index["captures"][self.capture]["captured_at"]

    @property
    def is_synthetic(self) -> bool:
        """Every fixture here is a real captured response. Nothing in this repository is
        invented, and a run over invented records that did not announce itself would be a lie
        by omission."""
        return False

    # ------------------------------------------------------------------ fetching
    def fetch(self, request: Request) -> str:
        self.calls.append(request)
        entry = self._entry_for(request)
        body = (self.fixture_dir / entry["file"]).read_text(encoding="utf-8")
        return self._replay(request, entry, body)

    def _entry_for(self, request: Request) -> dict[str, Any]:
        """Which captured response answers this call, within this capture."""
        candidates = [r for r in self.index["responses"]
                      if r["endpoint"] == request.endpoint
                      and self.capture in r.get("captures", [])]

        if request.endpoint in ("GetReservationBalance",):
            # Keyed per record: one call per reservation, no bulk journal endpoint (R1).
            wanted = request.params.get("ReservationNumber")
            for entry in candidates:
                if entry["request"].get("ReservationNumber") == wanted:
                    return entry
            # NOT an error in the ordinary sense. It is the evidence gap control 6 has to
            # survive: a reservation whose folio was never captured yields UNKNOWN for that
            # reservation and nothing else.
            raise ResponseUnavailable(
                "no captured folio for reservation %s in the %s capture - one call per "
                "reservation is the cost this control is built around (R1), and the sandbox "
                "belongs to someone else (R8), so only three were taken"
                % (wanted, self.capture))

        if not candidates:
            raise ResponseUnavailable(
                "the %s capture holds no %s response" % (self.capture, request.endpoint))
        # ISSUE #71. The response that answers is the one whose RECORDED question covers the
        # one asked - not the first of its endpoint. Taking the first, a run asking arrivals
        # met sandbox2026's departure window, found no arrival window on it to compare, and
        # replayed the arrival filter over the departure window's bookings: part of a
        # population, presented as the whole, behind three of criterion 1's PASSes.
        refusals = []
        for entry in candidates:
            refusal = _uncovered(request, entry)
            if refusal is None:
                return entry
            refusals.append(refusal)
        raise ResponseUnavailable(
            refusals[0] if len(refusals) == 1 else
            "none of the %d %s responses in this capture was asked that question: %s"
            % (len(refusals), request.endpoint, "; ".join(refusals)))

    # ------------------------------------------------------------------ filter replay
    def _replay(self, request: Request, entry: dict[str, Any], body: str) -> str:
        """Narrow a captured response the way the live server would have."""
        if request.endpoint != "GetReservationKey" or not request.params:
            return body

        root = parse_document(body)
        bookings = root.findall(".//Booking")
        parent_of = {id(child): parent for parent in root.iter() for child in parent}
        for booking in bookings:
            if not _booking_matches(booking, request.params):
                parent = parent_of.get(id(booking))
                if parent is not None:
                    parent.remove(booking)
        return ET.tostring(root, encoding="unicode")


def _booking_matches(booking: ET.Element, params: dict[str, Any]) -> bool:
    for name, wanted in params.items():
        if name in REQUEST_OPTIONS:
            continue

        if name in BOOKING_DATE_FILTERS:
            path, attribute = BOOKING_DATE_FILTERS[name]
            holder = booking if path is None else booking.find(path)
            raw = holder.get(attribute) if holder is not None else None
            # Responses carry dd/MM/yyyy while requests carry ISO. Compare in ISO, where a
            # string comparison is a date comparison.
            when = date_ddmmyyyy_to_iso(raw or "")
            if not when.is_known:
                return False
            if wanted.get("From") and when.payload < wanted["From"]:
                return False
            if wanted.get("To") and when.payload > wanted["To"]:
                return False

        elif name == "BookingSearch":
            for key, value in wanted.items():
                if key != "Status":
                    raise ResponseUnavailable(
                        "replay cannot honour BookingSearch filter %r" % (key,))
                if booking.get("Status") != value:
                    return False
        else:
            # Silently ignoring a filter hands the caller a WIDER population than it asked
            # for, which is the one failure a bounded query exists to prevent (R1).
            raise ResponseUnavailable("replay cannot honour request filter %r" % (name,))
    return True


def _uncovered(request: Request, entry: dict[str, Any]) -> str | None:
    """Why this captured response cannot answer this request - or None if it can.

    THREE WAYS A RECORDED QUESTION FAILS TO COVER AN ASKED ONE, each a population that would
    look complete and is not:

      * the run asks a window the recording never named (issue #71) - its records were
        selected by a different question, and replaying this one over them answers neither;
      * the run asks a window wider than the one recorded (finding F19c, issue #9);
      * the recording was narrowed by something the run does not ask (#71, the other
        direction) - its records are a part of what the run asks about.

    Windows are found by SHAPE, never by name: issue #9 is what a list of names leaves behind.
    """
    recorded = entry["request"]
    asked_params = request.params or {}
    for name, asked_raw in asked_params.items():
        asked = _window(asked_raw)
        if asked is None:
            # Not a date window: a status filter narrows WITHIN the recorded window, and
            # _booking_matches refuses any filter it cannot replay.
            continue
        captured = _window(recorded.get(name))
        if captured is None:
            return ("this capture cannot answer that question: the run asks for %s %s..%s, and "
                    "these records were selected by %s - a population replayed from them would "
                    "be the answer to a different question, and would look exactly as complete "
                    "as the right one" % (name, asked[0], asked[1], _described(recorded)))
        asked_from, asked_to = asked
        captured_from, captured_to = captured
        if (asked_from or "") < (captured_from or "") or \
                (asked_to or "9999") > (captured_to or "9999"):
            return ("this capture cannot answer that question: %s was captured for %s..%s and "
                    "the run asks for %s..%s. An empty population here would look exactly like "
                    "'no violations found', and a population from the WRONG window would look "
                    "like an answer, so it is refused instead"
                    % (name, captured_from, captured_to, asked_from, asked_to))
    for name in recorded:
        if name not in asked_params and name not in REQUEST_OPTIONS:
            return ("this capture cannot answer that question: these records were also "
                    "selected by %s, which the run does not ask, so they are a part of its "
                    "population presented as the whole" % name)
    return None


def _described(recorded: dict[str, Any]) -> str:
    """A recorded question as a refusal names it, e.g. a window and its two dates."""
    parts = []
    for name, value in recorded.items():
        if name in REQUEST_OPTIONS:
            continue
        window = _window(value)
        parts.append("%s %s..%s" % (name, window[0], window[1]) if window else name)
    return " and ".join(parts) or "no filter at all"


def _window(value: Any) -> tuple[str | None, str | None] | None:
    """The (start, end) a request filter names, or None if it is not a date window at all.

    Found by shape, because the name is exactly what the guard must not depend on (issue #9).
    A dict carrying either bound counts: a half-open window is still a window, and treating it
    as "not a window" would send it down the unguarded path this function exists to close.
    """
    if not isinstance(value, dict):
        return None
    for low, high in WINDOW_BOUNDS:
        if low in value or high in value:
            return value.get(low), value.get(high)
    return None
