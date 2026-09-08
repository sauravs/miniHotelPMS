# -*- coding: utf-8 -*-
"""
FROZEN SOURCE - DemoPMS responses, replayed as if a server had answered.

No network, ever. There is no DemoPMS server to reach: the provider is fictional, and every
response in `fixtures/demopms/` was TRANSCODED from a real MiniHotel capture by
`tools/transcode_demopms.py`.

THAT IS THE POINT, AND IT IS WHY THIS SOURCE ANNOUNCES ITSELF AS SYNTHETIC
--------------------------------------------------------------------------
Success criterion 7 asks that the same IR, over the same logical hotel, through two providers,
yields the same verdicts. "The same hotel" has to mean something, or the claim is decoration.
So these fixtures are not invented: they are the same 138 reservations, the same 28 rooms, the
same five folios and the same two occupancy segments, re-encoded field by field into a wire
format with DIFFERENT quirks. A rebuild is asserted to be byte-identical, so nothing here can
drift towards a nicer answer than the captures support.

What that buys is a real test of the boundary. What it does not buy is new evidence about a
hotel, and a run over transcoded records that did not say so would be a lie by omission - so
`is_synthetic` is True and the runner carries it onto the screen.

THE TWO THINGS THIS DOES THAT ANY REPLAY MUST
----------------------------------------------
1. IT KNOWS WHAT EACH FIXTURE WAS ASKED, and refuses a question the capture cannot answer
   (finding F19c, and issue #9 for the half that was missed). The fingerprints are the
   MiniHotel ones, translated - so a window refused there is refused here, and the two
   providers stay comparable in what they can and cannot say.

2. IT REPLAYS FILTERS THE WAY A SERVER WOULD. Knowing that `departure {from,to}` narrows on
   `departure.date` is DemoPMS knowledge and belongs here. Above this layer the filters are
   opaque data carried in the IR.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from ..base import Request, ResponseUnavailable
from .paths import find_all, parse_document
from .transforms import date_dmy_to_iso

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[3] / "fixtures" / "demopms"

# Where each booking-level date filter reads from, on one booking object. As with the other
# provider, this table is about REPLAYING a filter and is deliberately not the list of filters
# the window guard checks - issue #9 is what happens when those two are the same list.
BOOKING_DATE_FILTERS = {
    "arrival": "arrival.date",
    "departure": "departure.date",
    "created": "created_on",
}

# Request options that widen or narrow the CONTENT of each record rather than selecting
# records. The captures they were transcoded from were taken with prices included.
REQUEST_OPTIONS = {"include_prices"}

# DemoPMS spells a window one way, in lower case, everywhere. MiniHotel spells it `From`/`To`
# on the booking filters and `from`/`to` on the occupancy one, in the same API - the sort of
# inconsistency a fictional provider has no excuse for.
WINDOW_BOUNDS = ("from", "to")


class DemoSource:
    """Replays transcoded responses. `calls` records every request, so a test can ASSERT the
    call count rather than assume it (R1)."""

    def __init__(self, capture: str = "demo2026",
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
        return "%s (%s), transcoded from %s" % (
            self.capture, meta["label"], meta["transcoded_from"])

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
        """True, and it stays true. These records describe a real hotel and were produced by
        this repository rather than by a vendor's system, and a reader has to be able to tell
        the difference without reading the fixture directory."""
        return True

    # ------------------------------------------------------------------ fetching
    def fetch(self, request: Request) -> str:
        self.calls.append(request)
        entry = self._entry_for(request)
        body = (self.fixture_dir / entry["file"]).read_text(encoding="utf-8")
        return self._replay(request, body)

    def _entry_for(self, request: Request) -> dict[str, Any]:
        """Which response answers this call, within this capture."""
        candidates = [r for r in self.index["responses"]
                      if r["endpoint"] == request.endpoint
                      and self.capture in r.get("captures", [])]

        if request.endpoint in KEYED_ENDPOINTS:
            # Keyed per record: one call per booking, no bulk journal endpoint (R1).
            wanted = request.params.get(KEYED_ENDPOINTS[request.endpoint])
            for entry in candidates:
                if entry["request"].get(KEYED_ENDPOINTS[request.endpoint]) == wanted:
                    return entry
            # NOT an error in the ordinary sense. It is the evidence gap the checkout controls
            # have to survive: the source capture holds five folios and no more, so the
            # reservations without one yield UNKNOWN and nothing else.
            raise ResponseUnavailable(
                "no ledger for booking %s in the %s capture - one call per booking is the cost "
                "these controls are built around (R1), and only the folios the source capture "
                "holds could be transcoded" % (wanted, self.capture))

        if not candidates:
            raise ResponseUnavailable(
                "the %s capture holds no %s response" % (self.capture, request.endpoint))
        entry = candidates[0]
        self._check_window_covered(request, entry)
        return entry

    def _check_window_covered(self, request: Request, entry: dict[str, Any]) -> None:
        """Refuse a question this capture cannot answer (F19c, issue #9).

        Every window in the request is checked against the fingerprint, found by SHAPE rather
        than by name - for the reason the other provider's guard learned the hard way: a guard
        that knows three filter names leaves the fourth unguarded from the day it is added.

        An empty population renders identically to "we looked and everything was fine", and a
        population from the WRONG window is worse still, because it looks like an answer.
        """
        for name, asked_raw in request.params.items():
            asked, captured = _window(asked_raw), _window(entry["request"].get(name))
            if asked is None or captured is None:
                continue
            if (asked[0] or "") < (captured[0] or "") or \
                    (asked[1] or "9999") > (captured[1] or "9999"):
                raise ResponseUnavailable(
                    "this capture cannot answer that question: %s was captured for %s..%s and "
                    "the run asks for %s..%s. An empty population here would look exactly like "
                    "'no violations found', and a population from the WRONG window would look "
                    "like an answer, so it is refused instead"
                    % (name, captured[0], captured[1], asked[0], asked[1]))

    # ------------------------------------------------------------------ filter replay
    def _replay(self, request: Request, body: str) -> str:
        """Narrow a captured response the way a live server would have."""
        if request.endpoint != "bookings" or not request.params:
            return body
        document = parse_document(body)
        document["bookings"] = [b for b in document.get("bookings", [])
                                if _booking_matches(b, request.params)]
        return json.dumps(document, indent=2, ensure_ascii=False)


# Endpoints that answer about ONE record, and the parameter carrying its key.
KEYED_ENDPOINTS = {"ledger": "booking_ref"}


def _booking_matches(booking: dict[str, Any], params: dict[str, Any]) -> bool:
    for name, wanted in params.items():
        if name in REQUEST_OPTIONS:
            continue

        if name in BOOKING_DATE_FILTERS:
            found = find_all(booking, BOOKING_DATE_FILTERS[name])
            # Responses carry `08 Jul 2026` while requests carry ISO. Compare in ISO, where a
            # string comparison is a date comparison.
            when = date_dmy_to_iso(found[0] if found else None)
            if not when.is_known:
                return False
            if wanted.get("from") and when.payload < wanted["from"]:
                return False
            if wanted.get("to") and when.payload > wanted["to"]:
                return False

        elif name == "state":
            if booking.get("state") != wanted:
                return False
        else:
            # Silently ignoring a filter hands the caller a WIDER population than it asked
            # for, which is the one failure a bounded query exists to prevent (R1).
            raise ResponseUnavailable("replay cannot honour request filter %r" % (name,))
    return True


def _window(value: Any) -> tuple[str | None, str | None] | None:
    """The (start, end) a request filter names, or None if it is not a date window at all."""
    if not isinstance(value, dict):
        return None
    low, high = WINDOW_BOUNDS
    if low in value or high in value:
        return value.get(low), value.get(high)
    return None
