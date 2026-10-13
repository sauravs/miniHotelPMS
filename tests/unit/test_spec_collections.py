# -*- coding: utf-8 -*-
"""
What the validator refuses about collections, absences and windows - issue #109.

Four checks, each a rule that would otherwise run and answer wrongly:

  8. A field of a `collection` reference is read only in an assertion of mode `none` (P1). In
     scope, in an exception, or under `all` / `any` / `aggregate` it would be read from ONE
     record and reported as speaking for all of them - #87's defect - so it is refused BY NAME.
  9. `absent` says what a clause answers when its field is a declared absence (the owner's
     choice for P4, 2026-10-13). It belongs on an ordering, and only on a field whose absence
     the registry declares a fact; on a field whose absence is UNKNOWN it could never apply.
 10. `population.reference_windows` bounds a reference's request with canonical relative dates
     (P2). It must name a declared PMS reference, and its dates must be ones the property clock
     can resolve - an unrecognised token sent to somebody else's parser is a silently wrong
     window.
 11. A relative date (`today`, `today+7d`) as a predicate's value names a day, so its field is a
     date: the runner resolves it through the property clock (P4), and against a string field
     it would compare "2026-07-08" with a status.

Each test mutates the shipped rule in ONE way, so it proves the check fires on one defect.
"""
import copy

import pytest

from hotelcontrols.spec import Registry, load, load_schema, validate


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def ir_schema():
    return load_schema()


@pytest.fixture
def ooo():
    return copy.deepcopy(load("ooo_room_protection").raw)


def problems(raw, registry, ir_schema):
    return [str(p) for p in validate(raw, registry, ir_schema=ir_schema)]


OVERLAP = {"field": "occupancy.from", "operator": "within",
           "interval": {"start": "room.closed_from", "end": "room.closed_to"}}


class TestTheShippedRule:

    def test_it_validates(self, ooo, registry, ir_schema):
        assert problems(ooo, registry, ir_schema) == []

    def test_it_is_version_4_with_the_window_and_the_scope_clause(self, ooo):
        """P5. The two overlap predicates of version 3, P4's clause, P2's window."""
        assert ooo["version"] == 4
        assert ooo["population"]["reference_windows"] == {
            "occupancy": {"from": "today", "to": "today+7d"}}
        assert {"field": "room.closed_to", "operator": "gte", "value": "today",
                "absent": True} in [{k: v for k, v in p.items() if k != "note"}
                                    for p in ooo["scope"]]
        assert [(p["field"], p["interval"]) for p in ooo["assertion"]["predicates"]] == [
            ("occupancy.from", {"start": "room.closed_from", "end": "room.closed_to"}),
            ("room.closed_from", {"start": "occupancy.from", "end": "occupancy.to"})]


class TestCheck8ACollectionIsReadOnlyUnderNone:

    @pytest.mark.parametrize("clause", ["scope", "exceptions"])
    def test_a_collection_field_in_scope_or_exceptions_is_refused_by_name(
            self, ooo, registry, ir_schema, clause):
        ooo[clause].append(copy.deepcopy(OVERLAP))
        found = problems(ooo, registry, ir_schema)
        assert any("occupancy.from" in p and "collection" in p and clause in p
                   for p in found), found

    @pytest.mark.parametrize("mode", ["all", "any"])
    def test_a_collection_field_under_all_or_any_is_refused_by_name(
            self, ooo, registry, ir_schema, mode):
        ooo["assertion"]["mode"] = mode
        found = problems(ooo, registry, ir_schema)
        assert any("occupancy.from" in p and "collection" in p and repr(mode) in p
                   for p in found), found

    def test_a_collection_field_as_an_interval_bound_is_found_too(
            self, ooo, registry, ir_schema):
        ooo["assertion"]["mode"] = "all"
        found = problems(ooo, registry, ir_schema)
        assert any("occupancy.to" in p for p in found), found

    def test_a_collection_field_compared_to_is_found_too(self, ooo, registry, ir_schema):
        ooo["scope"].append({"field": "room.closed_from", "operator": "equals",
                             "compare_to": "occupancy.from"})
        found = problems(ooo, registry, ir_schema)
        assert any("occupancy.from" in p and "scope" in p for p in found), found

    def test_a_lookup_field_is_not_a_collection(self, registry, ir_schema):
        """A stay's assigned room is ONE record, read in scope by four shipped controls."""
        raw = copy.deepcopy(load("room_capacity_compliance").raw)
        assert problems(raw, registry, ir_schema) == []


class TestCheck9Absent:

    def test_absent_on_an_ordering_of_a_declared_absence_is_accepted(
            self, ooo, registry, ir_schema):
        assert any(p.get("absent") is True for p in ooo["scope"])
        assert problems(ooo, registry, ir_schema) == []

    def test_absent_must_be_a_boolean(self, ooo, registry, ir_schema):
        [clause] = [p for p in ooo["scope"] if "absent" in p]
        clause["absent"] = "yes"
        assert problems(ooo, registry, ir_schema), "the schema types it"

    def test_absent_on_a_non_ordering_operator_is_refused(self, ooo, registry, ir_schema):
        ooo["scope"].append({"field": "room.closed_to", "operator": "exists",
                             "absent": True})
        found = problems(ooo, registry, ir_schema)
        assert any("absent" in p and "'exists'" in p for p in found), found

    def test_absent_on_a_field_whose_absence_is_unknown_is_refused(self, registry, ir_schema):
        """folio.balance_due's absence is an evidence gap, never a fact - `absent` could
        never apply, and reading it as if it did would be a rule that lies about itself."""
        raw = copy.deepcopy(load("checkout_money_owed").raw)
        [predicate] = raw["assertion"]["predicates"]
        predicate["absent"] = False
        found = problems(raw, registry, ir_schema)
        assert any("absent" in p and "folio.balance_due" in p for p in found), found


class TestCheck10ReferenceWindows:

    def test_a_window_on_an_undeclared_reference_is_refused(self, ooo, registry, ir_schema):
        ooo["population"]["reference_windows"]["room"] = {"from": "today", "to": "today+7d"}
        found = problems(ooo, registry, ir_schema)
        assert any("reference_windows" in p and "'room'" in p for p in found), found

    @pytest.mark.parametrize("token", ["tomorrow", "today+7", "2026-07-08", "today+7w"])
    def test_a_date_the_clock_cannot_resolve_is_refused(self, ooo, registry, ir_schema, token):
        ooo["population"]["reference_windows"]["occupancy"]["to"] = token
        found = problems(ooo, registry, ir_schema)
        assert any("reference_windows" in p and token in p for p in found), found

    def test_a_window_needs_both_ends(self, ooo, registry, ir_schema):
        del ooo["population"]["reference_windows"]["occupancy"]["to"]
        assert problems(ooo, registry, ir_schema)

    def test_a_window_carries_nothing_else(self, ooo, registry, ir_schema):
        ooo["population"]["reference_windows"]["occupancy"]["DateRange"] = {}
        assert problems(ooo, registry, ir_schema), "no provider's filter name above the boundary"

    def test_a_window_ending_before_it_starts_is_refused(self, ooo, registry, ir_schema):
        ooo["population"]["reference_windows"]["occupancy"] = {"from": "today+7d",
                                                               "to": "today"}
        found = problems(ooo, registry, ir_schema)
        assert any("reference_windows" in p for p in found), found


class TestCheck11ARelativeDateValueIsADate:

    def test_on_a_date_field_it_is_accepted(self, ooo, registry, ir_schema):
        assert problems(ooo, registry, ir_schema) == []

    def test_on_a_string_field_it_is_refused(self, registry, ir_schema):
        raw = copy.deepcopy(load("checkout_money_owed").raw)
        raw["scope"].append({"field": "reservation.status", "operator": "equals",
                             "value": "today"})
        found = problems(raw, registry, ir_schema)
        assert any("today" in p and "reservation.status" in p for p in found), found

    def test_a_malformed_relative_date_is_refused(self, ooo, registry, ir_schema):
        [clause] = [p for p in ooo["scope"] if p.get("value") == "today"]
        clause["value"] = "today+1week"
        found = problems(ooo, registry, ir_schema)
        assert any("today+1week" in p for p in found), found
