# -*- coding: utf-8 -*-
"""
The demo fixtures are the same hotel - checked, not asserted in a comment.

`tests/e2e/test_two_providers.py` proves the two providers reach the same verdicts. That is
only worth something if they are answering about the same property, and "the same property" is
exactly the claim a second fixture set makes and cannot keep on its own. v1 shipped
`fixtures/synthetic/` and reached outcomes its captures could not; give a person a blank file
and the controls it is about to be judged by, and the data drifts towards the nicer answer.

So `fixtures/demopms/` is generated from the vendor captures, and this file checks three things:

  1. A REBUILD CHANGES NOTHING. If it did, every assertion about a demo fixture would be a
     statement about whatever was last written by hand.
  2. THE RECORDS ARE THE SAME RECORDS, canonically - same ids, same amounts, same statuses,
     same room numbers, read back through each provider's own adapter.
  3. THE GAPS ARE THE SAME GAPS. This is the one that matters most, and the one a hand-written
     fixture set would quietly close: the folios nobody captured are still missing, the
     statuses nobody can name are still unnameable, and the rooms with no configured capacity
     are still unconfigured.
"""
import json
import pathlib

import pytest

from hotelcontrols.providers.base import Request
from hotelcontrols.providers.demopms import DemoPmsAdapter, DemoSource
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import TenantConfig
from tools import transcode_demopms as transcode

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEMO = ROOT / "fixtures" / "demopms"

# The same body of evidence, named on each side. Both are the 2026 probe of one hotel.
PAIRS = (("sandbox2026", "demo2026"), ("sandbox2024", "demo2024"))


def adapters(source_capture, demo_capture):
    return (MiniHotelAdapter(TenantConfig.load("sandbox"), FrozenSource(source_capture)),
            DemoPmsAdapter(TenantConfig.load("demo"), DemoSource(demo_capture)))


def canonical(adapter, request, entity, fields):
    """Every record of an entity, as a sorted list of canonical values.

    Read through each adapter, so the comparison is between what the two PROVIDERS say rather
    than between two files - which is the only comparison the layers above care about.
    """
    records = adapter.records(adapter.fetch(request), entity)
    rows = []
    for record in records:
        row = []
        for name in fields:
            value = adapter.resolve(name, record)
            row.append(str(value.payload) if value.is_known else "unknown")
        rows.append(tuple(row))
    return sorted(rows)


class TestARebuildChangesNothing:
    """Determinism, checked against what is actually committed.

    If this fails, every re-run of the tool is a spurious diff and no assertion about a demo
    fixture can be trusted to stay put. It is the same guard `test_fixture_hygiene.py` puts on
    the scrubber, for the same reason.
    """

    def test_the_committed_fixtures_are_exactly_what_the_tool_produces(self):
        built = transcode.build()
        differences = []
        for name, content in sorted(built.items()):
            path = DEMO / name
            if not path.is_file():
                differences.append("%s is missing" % name)
            elif path.read_text(encoding="utf-8") != content:
                differences.append("%s differs from a rebuild" % name)
        assert not differences, (
            "run `python3 -m tools.transcode_demopms`; these fixtures are generated and must "
            "never be edited by hand: %s" % differences)

    def test_nothing_is_committed_that_the_tool_does_not_produce(self):
        """A leftover file is a fixture nobody generated, which is a fixture nobody checked."""
        built = set(transcode.build())
        assert {p.name for p in DEMO.glob("*.json")} == built

    def test_the_tool_reports_a_clean_check(self):
        assert transcode.main(["--check"]) == 0


class TestTheRecordsAreTheSameRecords:
    @pytest.mark.parametrize("source_capture,demo_capture", PAIRS)
    def test_the_same_reservations_with_the_same_statuses_and_totals(
            self, source_capture, demo_capture):
        source, demo = adapters(source_capture, demo_capture)
        fields = ("reservation.id", "reservation.status", "reservation.arrival_date",
                  "reservation.departure_date", "reservation.channel_confirmation_id",
                  "reservation.total_amount", "reservation.currency")
        assert canonical(source, Request("GetReservationKey", {}), "reservation", fields) == \
            canonical(demo, Request("bookings", {}), "reservation", fields)

    def test_the_same_rooms_with_the_same_types_and_capacities(self):
        source, demo = adapters("sandbox2026", "demo2026")
        fields = ("room.number", "room.type", "room.housekeeping_status",
                  "room.max_guests.adults", "room.max_guests.children",
                  "room.closed_from", "room.is_sellable_by_integration")
        assert canonical(source, Request("getRooms", {}), "room", fields) == \
            canonical(demo, Request("rooms", {}), "room", fields)

    def test_the_same_room_types(self):
        source, demo = adapters("sandbox2026", "demo2026")
        fields = ("room_type.code", "room_type.description")
        assert canonical(source, Request("getRoomTypes", {}), "room_type", fields) == \
            canonical(demo, Request("room-types", {}), "room_type", fields)

    def test_the_same_occupancy_segments(self):
        source, demo = adapters("sandbox2026", "demo2026")
        fields = ("occupancy.room_number", "occupancy.reservation_id", "occupancy.from",
                  "occupancy.to", "occupancy.status")
        assert canonical(source, Request("RoomStatusInquiry", {}), "occupancy", fields) == \
            canonical(demo, Request("occupancy", {}), "occupancy", fields)

    # Which capture holds which folio. Two were taken during the original 2024 probe and three
    # during the 2026 checkout probe; a folio costs one call per reservation on somebody else's
    # server (R1, R8), which is why there are five and not 138.
    FOLIOS = {"007003199": ("sandbox2024", "demo2024"),
              "007003204": ("sandbox2024", "demo2024"),
              "007004348": ("sandbox2026", "demo2026"),
              "007004351": ("sandbox2026", "demo2026"),
              "007004354": ("sandbox2026", "demo2026")}

    @pytest.mark.parametrize("booking_ref", sorted(FOLIOS))
    def test_the_same_folios_down_to_the_last_agora(self, booking_ref):
        """Every captured folio, amount by amount. The overpaid one is in this list, and it is
        the record decision D8 rests on - if the transcode rounded it, control 6 would stop
        being two controls."""
        source, demo = adapters(*self.FOLIOS[booking_ref])
        fields = ("folio.balance_due", "folio.currency", "folio.total_charged",
                  "folio.total_paid")
        source_folio = source.fetch(Request("GetReservationBalance",
                                            {"ReservationNumber": booking_ref}))
        demo_folio = demo.fetch(Request("ledger", {"booking_ref": booking_ref}))
        for name in fields:
            assert str(source.resolve(name, source_folio).payload) == \
                str(demo.resolve(name, demo_folio).payload), name


class TestTheGapsAreTheSameGaps:
    """The half a hand-written fixture set would quietly close."""

    def test_the_folios_nobody_captured_are_still_missing(self):
        """The source capture holds five folios because a folio costs one call per reservation
        on somebody else's server (R1, R8). The demo hotel has five too - not 138."""
        index = json.loads((DEMO / "index.json").read_text(encoding="utf-8"))
        ledgers = [r for r in index["responses"] if r["endpoint"] == "ledger"]
        assert len(ledgers) == 5

    def test_the_statuses_nobody_can_name_are_still_unnameable(self):
        """A5. 21 reservations in this window carry a code documented nowhere, on both. Mapping
        them here would be inventing knowledge about a hotel."""
        source, demo = adapters("sandbox2026", "demo2026")
        counts = []
        for adapter, request in ((source, Request("GetReservationKey", {})),
                                 (demo, Request("bookings", {}))):
            records = adapter.records(adapter.fetch(request), "reservation")
            counts.append(sum(1 for r in records
                              if not adapter.resolve("reservation.status", r).is_known))
        assert counts[0] == counts[1] == 21

    def test_the_rooms_with_no_configured_capacity_are_still_unconfigured(self):
        """R12, and the sharpest test of the transcode. The source says 0 and means
        "unconfigured"; the demo file says -1 and means the same thing. Writing a plausible
        capacity instead would let `room_capacity_compliance` answer for records the real hotel
        cannot answer for - which is the whole failure this project exists to prevent."""
        source, demo = adapters("sandbox2026", "demo2026")
        counts = []
        for adapter, request in ((source, Request("getRooms", {})),
                                 (demo, Request("rooms", {}))):
            records = adapter.records(adapter.fetch(request), "room")
            counts.append(sum(1 for r in records
                              if not adapter.resolve("room.max_guests.adults", r).is_known))
        assert counts[0] == counts[1] == 23

    def test_no_room_has_a_closed_date_window_on_either_provider(self):
        """Open question 2.4. The out-of-service mechanism has never been observed working on
        this property, and the demo hotel does not get to have observed it."""
        source, demo = adapters("sandbox2026", "demo2026")
        for adapter, request in ((source, Request("getRooms", {})),
                                 (demo, Request("rooms", {}))):
            records = adapter.records(adapter.fetch(request), "room")
            assert all(adapter.resolve("room.closed_from", r).payload is False
                       for r in records)


class TestTheToolRefusesToInvent:
    def test_a_status_code_it_has_not_been_told_about_stops_the_build(self):
        """The rule that keeps the tool honest. A capture that starts carrying a new code must
        be a decision somebody makes, not a silent widening of what the demo hotel knows."""
        with pytest.raises(transcode.Unencodable) as caught:
            transcode._translate(transcode.STATUS, "SOMETHING_NEW", "status")
        assert "has not been told" in str(caught.value)

    def test_every_status_the_captures_carry_has_a_translation(self):
        """The other direction: a code in the evidence with no entry here would stop the build,
        so this asserts the table is complete for the fixtures we actually hold."""
        import re
        source = ROOT / "fixtures" / "minihotel"
        seen = set()
        for path in source.glob("*.xml"):
            seen.update(re.findall(r'<Booking [^>]*Status="([^"]*)"',
                                   path.read_text(encoding="utf-8")))
        assert seen and seen <= set(transcode.STATUS), sorted(seen - set(transcode.STATUS))

    def test_the_fingerprints_are_translated_rather_than_invented(self):
        """A window one provider refuses must be refused by the other, or the two stop being
        comparable in what they can answer (F19c, issue #9)."""
        source = json.loads(
            (ROOT / "fixtures" / "minihotel" / "index.json").read_text(encoding="utf-8"))
        demo = json.loads((DEMO / "index.json").read_text(encoding="utf-8"))
        by_file = {r["transcoded_from"]: r for r in demo["responses"]}

        for entry in source["responses"]:
            if entry["file"] not in by_file:
                continue
            translated = by_file[entry["file"]]["request"]
            for name, value in entry["request"].items():
                if not isinstance(value, dict) or "Status" in value:
                    continue
                bounds = translated[transcode.FILTERS[name]]
                assert bounds["from"] == value.get("From", value.get("from"))
                assert bounds["to"] == value.get("To", value.get("to"))
