# -*- coding: utf-8 -*-
"""
v3 slice 23: the evidence refresh, measured.

Four read-only calls to the live sandbox on 2026-10-10, each approved by the project owner at
the time it was made (D3, D16): `getRooms`, `getRoomTypes`, a 7-day `RoomStatusInquiry`
(open question 1.2), and the 2026 reservation window asked again WITH room prices (#49). They
are a NEW capture, `sandbox2026refresh`, and DemoPMS's `demo2026refresh` is its transcode. No
earlier capture was edited.

The demo does not offer this capture: the engine's capture lists are a must-not for slice 23
(the owner's choice A), so everything here builds the source directly, which any capture in the
index allows.

What this file pins, so a change to any of it is noticed:
  * the capture is what it says it is - four responses, all observed on 2026-10-10;
  * question 1.2's findings, each with a dated verdict;
  * the rate codes #49 was waiting for arrive, and still move no number on their own;
  * criterion 1 per capture, beside the old figure and never instead of it;
  * criterion 7 on the new capture: both providers, the same answers.
"""
import json
import pathlib
from collections import Counter

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import Request
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig, available

ROOT = pathlib.Path(__file__).resolve().parents[2]
AS_OF = "2026-07-08T09:00"
REFRESH = {"sandbox": "sandbox2026refresh", "demo": "demo2026refresh"}
BEFORE = {"sandbox": "sandbox2026", "demo": "demo2026"}
ENDPOINT = {  # each provider's name for the same question
    "sandbox": {"rooms": "getRooms", "types": "getRoomTypes", "bookings": "GetReservationKey"},
    "demo": {"rooms": "rooms", "types": "room-types", "bookings": "bookings"},
}


def built(property_id, capture):
    tenant = TenantConfig.load(property_id)
    package = next(p for p in all_providers() if p.name == tenant.provider)
    adapter, _source = package.build(tenant, capture)
    return tenant, adapter


def a_run(control_id, property_id="sandbox", capture=None):
    capture = capture or REFRESH[property_id]
    tenant, adapter = built(property_id, capture)
    return run(control_id, tenant, adapter, FixedClock.at(AS_OF, tenant.timezone),
               evidence_label=capture)


def records(property_id, capture, which, entity):
    _tenant, adapter = built(property_id, capture)
    response = adapter.fetch(Request(ENDPOINT[property_id][which], {}))
    return adapter, adapter.records(response, entity)


def index(provider_dir):
    return json.loads((ROOT / "fixtures" / provider_dir / "index.json").read_text("utf-8"))


# --------------------------------------------------------------------------- the capture
class TestTheCaptureIsWhatItSays:

    def test_four_calls_all_observed_on_the_day_they_were_made(self):
        """D16's exit test: the index entry records the date and the call count, and every
        response in the capture was obtained that day (F7) - none borrowed from an older one,
        which would make the capture look fresher than its evidence."""
        minihotel = index("minihotel")
        meta = minihotel["captures"]["sandbox2026refresh"]
        assert (meta["captured_at"], meta["as_of"], meta["calls"]) == (
            "2026-10-10", "2026-07-08", 4)
        mine = [r for r in minihotel["responses"] if "sandbox2026refresh" in r["captures"]]
        assert len(mine) == meta["calls"]
        assert {r["captured_at"] for r in mine} == {"2026-10-10"}
        assert {r["endpoint"] for r in mine} == {
            "getRooms", "getRoomTypes", "RoomStatusInquiry", "GetReservationKey"}
        assert all(r["captures"] == ["sandbox2026refresh"] for r in mine), \
            "a refreshed response belongs to the refresh capture and nothing else"

    def test_the_reservation_call_asked_the_old_question_plus_room_prices(self):
        """#49, and what makes the two captures comparable: the same window as sandbox2026,
        verbatim, with one option added - so a difference is the hotel's, not the question's."""
        by_file = {r["file"]: r for r in index("minihotel")["responses"]}
        old = by_file["9_departures_2026-07.xml"]["request"]
        new = by_file["14_departures_2026-07_prices.xml"]["request"]
        assert new == dict(old, IncludeRoomPrices=True)

    def test_the_demo_capture_is_its_transcode_and_keeps_its_date(self):
        meta = index("demopms")["captures"]["demo2026refresh"]
        assert meta["captured_at"] == "2026-10-10" and meta["as_of"] == "2026-07-08"
        assert "sandbox2026refresh" in meta["transcoded_from"]


class TestTheProviderMapWasReverified:

    def test_every_mapping_of_a_reprobed_endpoint_finds_its_field_in_the_refresh(self):
        """What `verified_against` in spec/providers/minihotel.json claims for 2026-10-10: the
        same check validate_spec runs against each mapping's original probe file, run again
        against the response the refresh took from that endpoint."""
        import re
        provider_map = json.loads(
            (ROOT / "spec" / "providers" / "minihotel.json").read_text("utf-8"))
        refreshed = {r["endpoint"]: r["file"] for r in index("minihotel")["responses"]
                     if "sandbox2026refresh" in r["captures"]}
        checked, missing = 0, []
        for mapping in provider_map["mappings"]:
            if mapping["endpoint"] not in refreshed:
                continue
            body = (ROOT / "fixtures" / "minihotel" / refreshed[mapping["endpoint"]]
                    ).read_text("utf-8")
            checked += 1
            if not re.search(mapping["test"], body, re.S):
                missing.append(mapping["canonical"])
        assert (checked, missing) == (43, [])
        assert "re-verified 2026-10-10" in provider_map["verified_against"]


# --------------------------------------------------------------------------- question 1.2
@pytest.mark.parametrize("property_id", ["sandbox", "demo"])
class TestQuestion12RestatedOn20261010:
    """Each of 1.2's findings, with the verdict the refresh gives it. `docs/open-questions.md`
    1.2 says the same in prose; this is the part that fails if a later capture disagrees."""

    def test_r12_still_true_23_of_28_rooms_have_no_configured_adult_capacity(
            self, property_id):
        adapter, rooms = records(property_id, REFRESH[property_id], "rooms", "room")
        unknown = [r for r in rooms
                   if not adapter.resolve("room.max_guests.adults", r).is_known]
        assert (len(unknown), len(rooms)) == (23, 28)

    def test_r11_still_true_rooms_9900_to_9902_carry_a_type_nobody_defines(self, property_id):
        adapter, rooms = records(property_id, REFRESH[property_id], "rooms", "room")
        types_adapter, room_types = records(property_id, REFRESH[property_id], "types",
                                            "room_type")
        defined = {str(types_adapter.resolve("room_type.code", t).payload).casefold()
                   for t in room_types}                                        # R13
        undefined = sorted(adapter.resolve("room.number", r).payload for r in rooms
                           if str(adapter.resolve("room.type", r).payload).casefold()
                           not in defined)
        assert undefined == ["9900", "9901", "9902"]
        assert len(room_types) == 9

    def test_still_no_closed_date_window_on_any_room(self, property_id):
        """Open question 2.4: the out-of-service mechanism has still never been seen working,
        so both controls that read it still apply to no record - correctly."""
        assert a_run("ooo_room_protection", property_id).counts["EXCLUDED"] == 28
        active = a_run("room_assignment_active_room", property_id).counts
        assert active["EXCLUDED"] == active["total"] > 0


# --------------------------------------------------------------------------- #49
@pytest.mark.parametrize("property_id", ["sandbox", "demo"])
class TestRateCodesArrive:

    def test_rate_codes_are_present_on_the_refresh_and_on_no_earlier_capture(
            self, property_id):
        """#49: `stay.rate_code` was absent from every reservation captured, because none was
        taken with room prices. Ten stays carry an EMPTY code, which stays UNKNOWN."""
        def codes(capture):
            adapter, stays = records(property_id, capture, "bookings", "stay")
            return Counter(adapter.resolve("stay.rate_code", s).payload
                           if adapter.resolve("stay.rate_code", s).is_known else "UNKNOWN"
                           for s in stays)
        assert codes(BEFORE[property_id]) == Counter({"UNKNOWN": 135})
        assert codes(REFRESH[property_id]) == Counter(
            {"Tourist-BB": 122, "Tourist-RO": 4, "UNKNOWN": 10})

    def test_and_on_their_own_they_move_no_number(self, property_id):
        """The other half of #49. Control 15 needs the hotel's nominated rate codes too, and
        the sandbox's are NOT DECIDED (slice 21) - the vendor's test hotel has no policy anybody
        could honestly state. Inventing one to move criterion 1 is an anti-criterion of v3."""
        result = a_run("required_reservation_fields", property_id)
        assert not result.coverage.concluded
        assert any("nominated_rate_codes" in (v.reason or "") for v in result.verdicts)


# --------------------------------------------------------------------------- criterion 1
class TestCriterionOnePerCapture:
    """prd.md criterion 1 asks 8 of 11. Reported PER CAPTURE: the refresh is a second
    measurement beside sandbox2026's, never a replacement for it, and never rounded."""

    CONCLUDING = {
        "sandbox2026": {
            "checkout_money_owed", "checkout_unrefunded_credit",
            "duplicate_channel_reservation", "inactive_room_future_stay",
            "room_assignment_type_validity"},
        "sandbox2026refresh": {
            "duplicate_channel_reservation", "inactive_room_future_stay",
            "resource_occupancy_consistency", "room_assignment_type_validity"},
    }

    @pytest.mark.parametrize("capture", sorted(CONCLUDING))
    def test_the_controls_that_conclude_on_each_capture(self, capture):
        concluding = {c for c in available()
                      if a_run(c, capture=capture).coverage.concluded}
        assert concluding == self.CONCLUDING[capture], (
            "update CONCLUDING and the per-capture figure in docs/plan.md together")
        assert len(concluding) < 8, "criterion 1 is recorded as NOT MET on every capture"

    def test_what_the_refresh_gains_is_occupancy_and_what_it_loses_is_folios(self):
        """The difference, each half with its reason. Occupancy concludes because 2026 occupancy
        exists for the first time (issue #9 blocked it everywhere). The checkout controls find
        their two departures and stop, because no folio was re-taken: one call per reservation
        was not part of the approved probe (R1), and borrowing September's folios would date
        them October. So they say UNKNOWN, naming the gap."""
        assert a_run("resource_occupancy_consistency",
                     capture="sandbox2026").is_blocked
        occupancy = a_run("resource_occupancy_consistency").counts
        assert (occupancy["PASS"], occupancy["FAIL"], occupancy["UNKNOWN"]) == (31, 0, 4)
        for control_id in ("checkout_money_owed", "checkout_unrefunded_credit"):
            result = a_run(control_id)
            assert result.counts["UNKNOWN"] == result.counts["total"] == 2
            assert all("folio" in (v.reason or "") for v in result.verdicts)

    def test_the_two_unassigned_segments_are_unknown_not_an_overlap(self):
        """Issue #75, the defect this capture found: 007004312 and 007004313 are checked in
        with no room. Before the fix they FAILed against each other in a room called False."""
        result = a_run("resource_occupancy_consistency")
        outcomes = {v.record_id: v.outcome.value for v in result.verdicts}
        assert outcomes["007004312"] == outcomes["007004313"] == "UNKNOWN"


# --------------------------------------------------------------------------- criterion 7
@pytest.mark.parametrize("control_id", sorted(available()))
def test_both_providers_give_the_same_answers_on_the_refresh(control_id):
    """Criterion 7 on the new capture: the same records, the same outcomes, the same cost, the
    same verdict on whether anything was concluded."""
    def reduced(property_id):
        result = a_run(control_id, property_id)
        if result.is_blocked:
            return "blocked", result.calls
        return (Counter((v.record_id, v.outcome.value) for v in result.verdicts),
                result.calls, result.coverage.concluded)
    assert reduced("sandbox") == reduced("demo")
