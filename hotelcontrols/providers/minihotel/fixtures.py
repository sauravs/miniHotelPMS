# -*- coding: utf-8 -*-
"""
FROZEN SOURCE - captured responses, replayed as if the server had answered.

No network, ever. `fixtures/minihotel/` holds fourteen real responses, pseudonymised, and they
are the test evidence and the ground truth. MiniHotel asks integrators not to query wide date
ranges without agreement (R8), and a suite that needs someone else's server to be up is not a
suite.

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

# Where each booking-level date filter reads from, on one <Booking> element.
BOOKING_DATE_FILTERS = {
    "ArrivalDate": ("ResGlobalInfo/Timespan", "arrival"),
    "DepartureDate": ("ResGlobalInfo/Timespan", "departure"),
    "CreateDate": (None, "createDateTime"),
}

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
        entry = candidates[0]
        self._check_window_covered(request, entry)
        return entry

    def _check_window_covered(self, request: Request, entry: dict[str, Any]) -> None:
        """Refuse a question this capture cannot answer (finding F19c).

        If a control asks for departures in a window the capture never covered, replaying the
        filter would return zero bookings - and zero bookings renders identically to "we looked
        and everything was fine". Saying so is the whole point.
        """
        for name in BOOKING_DATE_FILTERS:
            asked, captured = request.params.get(name), entry["request"].get(name)
            if not asked or not captured:
                continue
            if asked.get("From", "") < captured.get("From", "") or \
                    asked.get("To", "9999") > captured.get("To", "9999"):
                raise ResponseUnavailable(
                    "this capture cannot answer that question: %s was captured for %s..%s and "
                    "the run asks for %s..%s. An empty population here would look exactly like "
                    "'no violations found', so it is refused instead"
                    % (name, captured.get("From"), captured.get("To"),
                       asked.get("From"), asked.get("To")))

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
