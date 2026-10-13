# -*- coding: utf-8 -*-
"""
A guest inside a room's closed window - issue #87.

`ooo_room_protection` version 2 asserted `occupancy.reservation_id within room.closed_from ..
room.closed_to`: a reservation ID placed between two DATES. Compared as strings, "007004344" <
"2026-07-10" because '0' < '2', so every real id landed outside every window and the room
PASSed. Even a date in its place would have been read from the room's FIRST occupancy segment
only, because a `collection` reference fills each of its fields with the first match.

No room in this property has ever had a closed window (open question 2.4), so no capture can
show it, and since #71 replay refuses this control's occupancy question (it names no window, and
the capture recorded one week) - so on frozen evidence the defect is hidden, not prevented. A
live PMS that answered would expose it. The source here is therefore a STAND-IN, like #86's: it
answers each endpoint with the refresh capture's recorded document, and sets room 303's closed
window in its own copy of the room master. No fixture is edited. Room 303 is the real case that
defeats both defects at once: its first 2026 segment (007004344, 08..09 Jul) is outside a window
closed 10..20 Jul, and the next guest (007004367, from 10 Jul) is inside it.

Fixed by the guard (#87's option 1): the rule's interval now places dates, and the evaluator
refuses to judge a collection by its first record. So the room is UNKNOWN, with the reason, until
the evaluator can judge every segment (option 2). It must never be PASS.
"""
import json
import pathlib
import re

import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import gather
from hotelcontrols.evidence.budget import CallBudget
from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.registry import load as load_provider
from hotelcontrols.spec import Registry, TenantConfig, load, validate

AS_OF = "2026-07-08T09:00"
CONTROL = "ooo_room_protection"
ROOM = "303"
PROPERTY = {"minihotel": "sandbox", "demopms": "demo"}
REFRESH = {"minihotel": "sandbox2026refresh", "demopms": "demo2026refresh"}


def close_minihotel(body):
    """rm_clsdt1 / rm_clsdt2 are yyyyMMdd on the wire."""
    room = re.compile(r"(<rm_number>%s</rm_number>\s*<rm_type>[^<]*</rm_type>\s*)"
                      r"<rm_clsdt1 />\s*<rm_clsdt2 />" % ROOM)
    closed, count = room.subn(
        r"\1<rm_clsdt1>20260710</rm_clsdt1><rm_clsdt2>20260720</rm_clsdt2>", body)
    assert count == 1
    return closed


def close_demopms(body):
    document = json.loads(body)
    [room] = [r for r in document["rooms"] if r["room_no"] == ROOM]
    room["out_of_service"] = {"from": "10 Jul 2026", "to": "20 Jul 2026"}
    return json.dumps(document)


CLOSE = {"minihotel": ("getRooms", close_minihotel), "demopms": ("rooms", close_demopms)}


FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"


class RoomClosed:
    """Each endpoint answered with the refresh capture's recorded document, whatever window it
    is asked - a PMS answering, not a replay - with room 303's closed window set in its copy."""

    def __init__(self, provider):
        index = json.loads((FIXTURES / provider / "index.json").read_text("utf-8"))
        self.bodies = {r["endpoint"]: (FIXTURES / provider / r["file"]).read_text("utf-8")
                       for r in index["responses"] if REFRESH[provider] in r.get("captures", [])}
        endpoint, close = CLOSE[provider]
        self.bodies[endpoint] = close(self.bodies[endpoint])

    def fetch(self, request):
        return self.bodies[request.endpoint]


def judged(provider):
    tenant = TenantConfig.load(PROPERTY[provider])
    adapter = load_provider(provider).adapter(tenant, RoomClosed(provider))
    ir = load(CONTROL)
    evidence = gather(ir, adapter, tenant, FixedClock.at(AS_OF, tenant.timezone),
                      CallBudget(50))
    verdicts = evaluate_population(ir, evidence.bundles, tenant.settings)
    bundles = {b.record_id: b for b in evidence.bundles}
    return {v.record_id: v for v in verdicts}, bundles


@pytest.mark.parametrize("provider", sorted(PROPERTY))
class TestAGuestInsideAClosedWindowIsNeverAPass:

    def test_the_constructed_case_is_the_one_described(self, provider):
        """The room is in scope, and its segments are as the docstring says - so the verdict
        below is about a real guest inside the window, behind a first segment outside it."""
        _verdicts, bundles = judged(provider)
        room = bundles[ROOM]
        assert room.fields["room.closed_from"].payload == "2026-07-10"
        segments = [(s["occupancy.reservation_id"].payload, s["occupancy.from"].payload)
                    for s in room.related["occupancy"]]
        assert segments[0] == ("007004344", "2026-07-08")
        assert ("007004367", "2026-07-10") in segments

    def test_the_room_is_not_pass(self, provider):
        """CLAUDE.md, never widen a verdict. Version 2 said PASS here."""
        verdicts, _bundles = judged(provider)
        assert verdicts[ROOM].outcome is Outcome.UNKNOWN, verdicts[ROOM]
        assert "occupancy" in verdicts[ROOM].reason, verdicts[ROOM].reason

    def test_every_other_room_is_still_excluded(self, provider):
        """Nothing else moved: no other room has a closed window."""
        verdicts, _bundles = judged(provider)
        others = {v.outcome for r, v in verdicts.items() if r != ROOM}
        assert others == {Outcome.EXCLUDED}


class TestTheRuleItself:

    def test_the_rule_is_version_3_and_valid(self):
        """Editing a rule makes a new version; validate_spec refuses an edit without a bump."""
        ir = load(CONTROL)
        assert ir.version == 3
        assert validate(ir, Registry.load()) == []

    def test_its_interval_operands_are_dates(self):
        registry = Registry.load()
        for _clause, predicate in load(CONTROL).predicates():
            if predicate["operator"] in ("within", "not_within"):
                fields = [predicate["field"], *predicate["interval"].values()]
                assert {registry.field(f).type for f in fields} <= {"date", "datetime"}, fields
