# -*- coding: utf-8 -*-
"""
A guest inside a room's closed window - issues #87 and #109.

`ooo_room_protection` version 2 asserted `occupancy.reservation_id within room.closed_from ..
room.closed_to`: a reservation ID placed between two DATES. Compared as strings, "007004344" <
"2026-07-10" because '0' < '2', so every real id landed outside every window and the room
PASSed. Even a date in its place would have been read from the room's FIRST occupancy segment
only. #87's guard made such a room UNKNOWN. #109 (#87's option 2, design P1-P6 approved
2026-10-13) makes it answer: every segment is judged, the occupancy reference asks a bounded
window (today..today+7d), and a PASS needs the closure from today onward to lie inside it.

No room in this property has ever had a closed window (open question 2.4), so no capture can
show any of this. The source here is therefore a STAND-IN, like #86's: it answers each endpoint
with the refresh capture's recorded document - the only capture holding 2026 occupancy, exactly
2026-07-08..15, which is why a 7-day window is provable offline - and sets one room's closed
window in its own copy of the room master. No fixture is edited.

Room 303 is the real case that defeats both old defects at once: its first 2026 segment
(007004344, 08..09 Jul) is outside a window closed 10..20 Jul, and the next guest (007004367,
from 10 Jul) is inside it. Room 401 has no segment that week at all. Two segments of the week
(007004312/313, 08..13 Jul) have no readable room - either may be any room's guest.

Every run goes through `runner.run`, so the relative date in P4's scope clause is resolved by
the property clock exactly as it is in the product.
"""
import json
import pathlib
import re

import pytest

from hotelcontrols.evidence import CallBudget, gather
from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.base import ResponseUnavailable
from hotelcontrols.providers.registry import load as load_provider
from hotelcontrols.runner import run, with_dates_resolved
from hotelcontrols.spec import Registry, TenantConfig, load, validate

AS_OF = "2026-07-08T09:00"
CONTROL = "ooo_room_protection"
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}
REFRESH = {"minihotel": "sandbox2026refresh", "demopms": "demo2026refresh"}
OCCUPANCY = {"minihotel": "RoomStatusInquiry", "demopms": "occupancy"}
FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"


def close_minihotel(body, room, start, end):
    """rm_clsdt1 / rm_clsdt2 are yyyyMMdd on the wire; an empty one is self-closing."""
    def wire(iso, tag):
        return "<%s>%s</%s>" % (tag, iso.replace("-", ""), tag) if iso else "<%s />" % tag
    pattern = re.compile(r"(<rm_number>%s</rm_number>\s*<rm_type>[^<]*</rm_type>\s*)"
                         r"<rm_clsdt1 />\s*<rm_clsdt2 />" % room)
    closed, count = pattern.subn(
        lambda m: m.group(1) + wire(start, "rm_clsdt1") + wire(end, "rm_clsdt2"), body)
    assert count == 1, room
    return closed


def close_demopms(body, room, start, end):
    from datetime import date
    def wire(iso):
        return date.fromisoformat(iso).strftime("%d %b %Y") if iso else None
    document = json.loads(body)
    [found] = [r for r in document["rooms"] if r["room_no"] == room]
    window = {"from": wire(start)}
    if end:
        window["to"] = wire(end)
    found["out_of_service"] = window
    return json.dumps(document)


CLOSE = {"minihotel": ("getRooms", close_minihotel), "demopms": ("rooms", close_demopms)}


class RoomClosed:
    """Each endpoint answered with the refresh capture's recorded document, whatever window it
    is asked - a PMS answering, not a replay - with one room's closed window set in its copy.
    `refuse_occupancy` makes the occupancy call fail, as a PMS refusing it would."""

    def __init__(self, provider, room, start, end, refuse_occupancy=False):
        index = json.loads((FIXTURES / provider / "index.json").read_text("utf-8"))
        self.bodies = {r["endpoint"]: (FIXTURES / provider / r["file"]).read_text("utf-8")
                       for r in index["responses"] if REFRESH[provider] in r.get("captures", [])}
        endpoint, close = CLOSE[provider]
        self.bodies[endpoint] = close(self.bodies[endpoint], room, start, end)
        self.refused = OCCUPANCY[provider] if refuse_occupancy else None
        self.asked = []

    def fetch(self, request):
        self.asked.append(request)
        if request.endpoint == self.refused:
            raise ResponseUnavailable("the PMS refused the occupancy window")
        return self.bodies[request.endpoint]


def judged(provider, room, start, end, **kwargs):
    tenant = TenantConfig.load(PROPERTY[provider])
    source = RoomClosed(provider, room, start, end, **kwargs)
    adapter = load_provider(provider).adapter(tenant, source)
    clock = FixedClock.at(AS_OF, tenant.timezone)
    result = run(CONTROL, tenant, adapter, clock, budget=CallBudget(50))
    assert not result.is_blocked, result.blocked
    return {v.record_id: v for v in result.verdicts}, source


def verdict(provider, room, start, end, **kwargs):
    return judged(provider, room, start, end, **kwargs)[0][room]


@pytest.mark.parametrize("provider", sorted(PROPERTY))
class TestP6:

    def test_the_constructed_case_is_the_one_described(self, provider):
        """Room 303 is in scope and its segments are as the docstring says - so the verdicts
        below are about a real guest inside the window, behind a first segment outside it."""
        tenant = TenantConfig.load(PROPERTY[provider])
        adapter = load_provider(provider).adapter(
            tenant, RoomClosed(provider, "303", "2026-07-10", "2026-07-20"))
        clock = FixedClock.at(AS_OF, tenant.timezone)
        evidence = gather(with_dates_resolved(load(CONTROL), clock), adapter, tenant, clock,
                          CallBudget(50))
        room = next(b for b in evidence.bundles if b.record_id == "303")
        assert room.fields["room.closed_from"].payload == "2026-07-10"
        segments = [(s["occupancy.reservation_id"].payload, s["occupancy.from"].payload)
                    for s in room.related["occupancy"]]
        assert segments[0] == ("007004344", "2026-07-08")
        assert ("007004367", "2026-07-10") in segments
        assert room.windows["occupancy"].start == "2026-07-08"
        assert room.windows["occupancy"].end == "2026-07-15"

    def test_the_reference_asks_the_bounded_window(self, provider):
        _verdicts, source = judged(provider, "303", "2026-07-10", "2026-07-13")
        [asked] = [r for r in source.asked if r.endpoint == OCCUPANCY[provider]]
        assert {"from": "2026-07-08", "to": "2026-07-15"} in list(asked.params.values())

    def test_a_guest_inside_the_closed_window_is_a_fail_naming_the_segment(self, provider):
        """303 closed 10..13 Jul, guest 007004367 from the 10th. Version 2 said PASS."""
        found = verdict(provider, "303", "2026-07-10", "2026-07-13")
        assert found.outcome is Outcome.FAIL, found
        assert "007004367" in found.reason, found.reason

    def test_a_closed_room_with_no_segment_in_its_window_is_a_pass(self, provider):
        """401 closed 14..15 Jul: inside the fetched 08..15, nobody in it, and neither
        segment with no readable room reaches the 14th."""
        found = verdict(provider, "401", "2026-07-14", "2026-07-15")
        assert found.outcome is Outcome.PASS, found

    def test_an_overlap_inside_the_horizon_fails_a_longer_closure(self, provider):
        """303 closed 10..20 Jul: the 16th..20th were never fetched, and do not need to be."""
        found = verdict(provider, "303", "2026-07-10", "2026-07-20")
        assert found.outcome is Outcome.FAIL, found
        assert "007004367" in found.reason, found.reason

    def test_a_closure_beyond_the_horizon_is_unknown_naming_the_dates(self, provider):
        found = verdict(provider, "401", "2026-07-16", "2026-07-20")
        assert found.outcome is Outcome.UNKNOWN, found
        assert "2026-07-16..2026-07-20" in found.reason, found.reason

    def test_an_open_ended_closure_with_no_overlap_is_unknown(self, provider):
        found = verdict(provider, "401", "2026-07-14", None)
        assert found.outcome is Outcome.UNKNOWN, found
        assert "no end" in found.reason, found.reason

    def test_a_refused_reference_is_unknown_never_a_pass(self, provider):
        """No segments came back because NONE were fetched - not because there are none."""
        found = verdict(provider, "401", "2026-07-14", "2026-07-15", refuse_occupancy=True)
        assert found.outcome is Outcome.UNKNOWN, found
        assert "refused" in found.reason, found.reason

    def test_a_closure_that_ended_before_today_is_excluded(self, provider):
        """P4. Not PASS - nothing was checked - and not UNKNOWN - nothing is unknown."""
        found = verdict(provider, "303", "2026-07-01", "2026-07-05")
        assert found.outcome is Outcome.EXCLUDED, found
        assert "room.closed_to" in found.reason, found.reason

    def test_a_segment_whose_room_is_unknown_keeps_an_empty_room_unknown(self, provider):
        """401 closed 10..12 Jul: no segment of its own, but 007004312/313 (08..13, no
        readable room) may be its guests."""
        found = verdict(provider, "401", "2026-07-10", "2026-07-12")
        assert found.outcome is Outcome.UNKNOWN, found
        assert "007004312" in found.reason, found.reason

    def test_every_other_room_is_still_excluded(self, provider):
        verdicts, _source = judged(provider, "303", "2026-07-10", "2026-07-13")
        assert {v.outcome for r, v in verdicts.items() if r != "303"} == {Outcome.EXCLUDED}


class TestTheRuleItself:

    def test_the_rule_is_version_4_and_valid(self):
        """Editing a rule makes a new version; validate_spec refuses an edit without a bump."""
        ir = load(CONTROL)
        assert ir.version == 4
        assert validate(ir, Registry.load()) == []

    def test_its_interval_operands_are_dates(self):
        registry = Registry.load()
        for _clause, predicate in load(CONTROL).predicates():
            if predicate["operator"] in ("within", "not_within"):
                fields = [predicate["field"], *predicate["interval"].values()]
                assert {registry.field(f).type for f in fields} <= {"date", "datetime"}, fields
