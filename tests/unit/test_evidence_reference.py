# -*- coding: utf-8 -*-
"""
Reference joins, and the ways they refuse.

The distinction this file exists to protect: A REFERENCE THAT COULD NOT BE FETCHED IS NOT AN
EMPTY REFERENCE. An empty set makes every membership test FAIL - "this room's type is not one of
the defined types" - and reports a wall of violations about a property whose data is fine. An
unavailable reference makes them UNKNOWN, which says what to connect. Same missing data, and the
difference between a false accusation and a product feature.
"""
import pytest

from hotelcontrols.evidence import CallBudget, ResponseCache, build_references
from hotelcontrols.evidence.reference import ReferenceIndex
from hotelcontrols.kernel import Value
from hotelcontrols.providers.base import ProviderError, Request
from hotelcontrols.spec import ControlIR


def ir_with(references):
    """A minimal IR carrying only what the reference builder reads."""
    return ControlIR({"control_id": "t", "entity": "stay", "references": references,
                      "assertion": {"mode": "all", "predicates": []},
                      "required_evidence": []})


class StubAdapter:
    name = "stub"

    def __init__(self, requests=None, records=None, values=None, fail=False):
        self._requests = requests if requests is not None else {"room": Request("rooms", {})}
        self._records = records or {}
        self._values = values or {}
        self._fail = fail

    def reference_request(self, entity):
        return self._requests.get(entity)

    def fetch(self, request):
        if self._fail:
            raise ProviderError("the response was never captured")
        return request.endpoint

    def records(self, response, entity):
        return list(self._records.get(entity, []))

    def resolve(self, name, record):
        return self._values.get((name, record), Value.unknown("no stub value for %s" % name))


def cache_for(adapter, limit=10):
    return ResponseCache(adapter.fetch, CallBudget(limit))


class TestUnavailableIsNotEmpty:
    def test_a_provider_with_no_way_to_fetch_the_entity_says_so(self):
        adapter = StubAdapter(requests={})
        index = build_references(
            ir_with([{"entity": "room", "kind": "set", "field": "room.number"}]),
            adapter, cache_for(adapter))["room"]
        assert not index.is_available
        assert "no way to retrieve" in index.unavailable

    def test_a_reference_that_fails_to_fetch_degrades_rather_than_stopping_the_run(self):
        """One broken reference must not abort a run: other evidence may still answer, and the
        control should report what it could not join rather than nothing at all."""
        adapter = StubAdapter(fail=True)
        index = build_references(
            ir_with([{"entity": "room", "kind": "lookup", "local_field": "stay.room_number",
                      "remote_field": "room.number"}]),
            adapter, cache_for(adapter))["room"]
        assert not index.is_available
        assert "never captured" in index.unavailable

    def test_a_tenant_supplied_reference_nobody_supplied_names_the_property_not_the_pms(self):
        """R13 / open question 1.6. Blaming the PMS for evidence the hotel owes us would send
        somebody to the wrong vendor."""
        adapter = StubAdapter()
        index = build_references(
            ir_with([{"entity": "rate_plan", "kind": "lookup", "source": "tenant",
                      "local_field": "stay.rate_code", "remote_field": "rate_plan.code"}]),
            adapter, cache_for(adapter))["rate_plan"]
        assert not index.is_available
        assert "property" in index.unavailable

    def test_an_unavailable_reference_is_never_asked_for_a_match(self):
        index = ReferenceIndex("room", "lookup", unavailable="not connected")
        matches, reason = index.match(Value.known("01"))
        assert matches == [] and reason == "not connected"


class TestMatching:
    def test_a_key_that_is_unknown_yields_no_match_and_says_why(self):
        index = ReferenceIndex("room", "lookup", by_key={"01": ["a record"]})
        matches, reason = index.match(Value.unknown("the stay has no assigned room"))
        assert matches == []
        assert "not established" in reason

    def test_a_key_that_matches_nothing_names_the_entity(self):
        """Never the first plausible record. Pairing the wrong ones would put wrong evidence
        behind a right-looking verdict, which is worse than answering nothing."""
        index = ReferenceIndex("room", "lookup", by_key={"01": ["a record"]})
        matches, reason = index.match(Value.known("9999"))
        assert matches == []
        assert "no room in this property matches 9999" in reason

    def test_a_matching_key_returns_its_records(self):
        index = ReferenceIndex("room", "lookup", by_key={"01": ["a record"]})
        matches, reason = index.match(Value.known("01"))
        assert matches == ["a record"] and reason is None

    def test_a_collection_returns_every_match_for_one_key(self):
        index = ReferenceIndex("occupancy", "collection", by_key={"303": ["first", "second"]})
        matches, _ = index.match(Value.known("303"))
        assert matches == ["first", "second"]


class TestBuilding:
    def test_a_set_reference_collects_only_the_values_it_could_resolve(self):
        """A code that could not be read must not appear in the set as None, or a membership
        test would start matching records whose type is missing."""
        adapter = StubAdapter(
            requests={"room_type": Request("types", {})},
            records={"room_type": ["a", "b", "c"]},
            values={("room_type.code", "a"): Value.known("dbl"),
                    ("room_type.code", "b"): Value.known("twin"),
                    ("room_type.code", "c"): Value.unknown("blank")})
        index = build_references(
            ir_with([{"entity": "room_type", "kind": "set", "field": "room_type.code"}]),
            adapter, cache_for(adapter))["room_type"]
        assert index.values == ("dbl", "twin")

    def test_a_lookup_indexes_by_the_remote_key_and_skips_unreadable_ones(self):
        adapter = StubAdapter(
            requests={"room": Request("rooms", {})},
            records={"room": ["r1", "r2"]},
            values={("room.number", "r1"): Value.known("01"),
                    ("room.number", "r2"): Value.unknown("no number")})
        index = build_references(
            ir_with([{"entity": "room", "kind": "lookup", "local_field": "stay.room_number",
                      "remote_field": "room.number"}]),
            adapter, cache_for(adapter))["room"]
        assert set(index.by_key) == {"01"}

    def test_a_budget_stop_ends_the_run_rather_than_disabling_the_reference(self):
        """A run that simply ran out of calls must not report 'the join was unavailable' for
        every record - that reads as a data problem when it is a cost problem."""
        from hotelcontrols.evidence import BudgetExceeded
        adapter = StubAdapter(requests={"room": Request("rooms", {})})
        budget = CallBudget(1)
        budget.spend(Request("population", {}))
        with pytest.raises(BudgetExceeded):
            build_references(
                ir_with([{"entity": "room", "kind": "lookup",
                          "local_field": "stay.room_number", "remote_field": "room.number"}]),
                adapter, ResponseCache(adapter.fetch, budget))
