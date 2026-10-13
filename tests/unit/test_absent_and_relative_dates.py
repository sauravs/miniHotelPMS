# -*- coding: utf-8 -*-
"""
P4 of issue #109: a closure that ended before today is EXCLUDED, and an absent end stays in
scope. Two engine pieces make that sayable, and this file pins both.

`absent` (the owner's choice, 2026-10-13). Scope clauses AND together and the grammar has no
OR, so "closed_to is absent OR on/after today" had no honest expression - and `gte` on an
absent end was not an answer at all but a TypeError (`False >= "2026-07-08"`). Now a clause
may state what it answers for a DECLARED absence (a known False or not-applicable, which the
registry says is a fact), and never for an unknown, which stays UNKNOWN. Without the key, an
ordering on an absence is UNKNOWN rather than a crash.

Relative dates. The runner resolves `today` / `today+Nd` in a predicate's value through the
PROPERTY clock before evaluating, so the evaluator stays pure. An unresolved one reaching the
evaluator is UNKNOWN: compared as a string, "2026-07-05" >= "today" is False because '2' < 't',
and every closed room would have been EXCLUDED.
"""
import pytest

from hotelcontrols.evaluator.predicates import evaluate_predicate
from hotelcontrols.evidence import Bundle
from hotelcontrols.kernel import NOT_APPLICABLE, FixedClock, Value
from hotelcontrols.runner import with_dates_resolved
from hotelcontrols.spec import load


def closed_to(value):
    return Bundle("room", "303", {"room.closed_to": value})


def gte_today(absent=None, value="2026-07-08"):
    predicate = {"field": "room.closed_to", "operator": "gte", "value": value}
    if absent is not None:
        predicate["absent"] = absent
    return predicate


class TestAbsent:

    def test_a_date_is_compared_as_before(self):
        assert evaluate_predicate(gte_today(True), closed_to(
            Value.known("2026-07-20", unit="date"))).holds is True
        assert evaluate_predicate(gte_today(True), closed_to(
            Value.known("2026-07-05", unit="date"))).holds is False

    @pytest.mark.parametrize("absence", [False, NOT_APPLICABLE])
    @pytest.mark.parametrize("absent", [True, False])
    def test_a_declared_absence_answers_what_the_clause_says(self, absence, absent):
        result = evaluate_predicate(gte_today(absent), closed_to(Value.known(absence)))
        assert result.holds is absent, result
        assert "absent" in result.reason, result.reason

    def test_an_unknown_is_never_read_as_an_absence(self):
        """`absent` is about a FACT the registry declares. An unreadable end is a gap."""
        result = evaluate_predicate(gte_today(True), closed_to(Value.unknown("unreadable")))
        assert result.holds is None
        assert "unreadable" in result.reason

    def test_without_the_key_an_ordering_on_an_absence_is_unknown_not_a_crash(self):
        result = evaluate_predicate(gte_today(), closed_to(Value.known(False)))
        assert result.holds is None, result
        assert "room.closed_to" in result.reason


class TestAnUnresolvedRelativeDate:

    @pytest.mark.parametrize("token", ["today", "today+7d", "today-1d"])
    def test_it_is_unknown_rather_than_compared_as_text(self, token):
        result = evaluate_predicate(gte_today(True, value=token), closed_to(
            Value.known("2026-07-05", unit="date")))
        assert result.holds is None, result
        assert token in result.reason and "clock" in result.reason, result.reason


class TestTheRunnerResolvesThroughThePropertyClock:

    def clock(self, instant="2026-07-08T09:00"):
        return FixedClock.at(instant, "Asia/Jerusalem")

    def test_today_becomes_the_propertys_date(self):
        resolved = with_dates_resolved(load("ooo_room_protection"), self.clock())
        assert {"field": "room.closed_to", "operator": "gte", "value": "2026-07-08",
                "absent": True} in [{k: v for k, v in p.items() if k != "note"}
                                    for p in resolved["scope"]]

    def test_the_property_clock_and_not_the_machines(self):
        """22:30 UTC on the 7th is already the 8th in Jerusalem (F11)."""
        clock = FixedClock.at("2026-07-08T01:30", "Asia/Jerusalem")
        resolved = with_dates_resolved(load("ooo_room_protection"), clock)
        assert "2026-07-08" in [p.get("value") for p in resolved["scope"]]

    def test_an_offset_is_applied(self):
        ir = load("ooo_room_protection")
        ir.raw["scope"].append({"field": "room.closed_from", "operator": "lt",
                                "value": "today+7d"})
        resolved = with_dates_resolved(ir, self.clock())
        assert "2026-07-15" in [p.get("value") for p in resolved["scope"]]

    def test_the_rule_on_disk_and_its_digest_are_unchanged(self):
        ir = load("ooo_room_protection")
        digest = ir.digest
        with_dates_resolved(ir, self.clock())
        assert ir.digest == digest
        assert "today" in [p.get("value") for p in ir["scope"]]

    def test_other_values_are_left_alone(self):
        ir = load("checkout_money_owed")
        assert with_dates_resolved(ir, self.clock()).raw == ir.raw
