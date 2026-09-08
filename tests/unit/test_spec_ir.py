# -*- coding: utf-8 -*-
"""
IR validation - the gate that stops a broken rule before it runs.

`control_rule_architecture.docx` section 17 asks for exactly this and says why:

    Don't go: LLM -> executable JSON directly. That's risky.
    Use: Natural Language -> Control IR -> Validation -> ... -> Executable Rule

This file is the Validation stage under test. It is what makes adding a compiler in slice 9
safe: whatever writes an IR - a person or a model - passes through these checks, and a rule
naming vocabulary nobody defined is rejected NAMING the missing fields rather than running and
quietly answering about nothing.

The last test in TestTheGateSection17Asksfor is the one to read first. It feeds the
requirements document's own example sentence to the pipeline and asserts the pipeline says no.
"""
import copy

import pytest

from hotelcontrols.spec import Registry, SpecError, TenantConfig, load, load_schema, validate


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def ir_schema():
    return load_schema()


@pytest.fixture(scope="module")
def tenant():
    return TenantConfig.from_dict({
        "tenant_id": "test", "provider": "minihotel", "timezone": "Asia/Jerusalem",
        "settings": {"nominated_rate_codes": [], "rate_plan_permitted_room_types": {}}})


@pytest.fixture
def valid_ir():
    """A real shipped control, used as the base every mutation below starts from.

    Mutating a working rule is deliberate: it proves each check fires on ONE defect rather than
    on a document that was malformed in six ways at once.
    """
    return copy.deepcopy(load("checkout_money_owed").raw)


def problems(raw, registry, ir_schema, tenant=None):
    return [str(p) for p in validate(raw, registry, tenant=tenant, ir_schema=ir_schema)]


class TestTheGateSection17AsksFor:
    def test_a_shipped_control_validates_cleanly(self, valid_ir, registry, ir_schema, tenant):
        assert problems(valid_ir, registry, ir_schema, tenant) == []

    def test_a_rule_naming_a_field_nobody_declared_is_rejected_by_name(
            self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["predicates"][0]["field"] = "folio.outstanding_amount"
        found = problems(valid_ir, registry, ir_schema)
        assert any("folio.outstanding_amount" in p and "undeclared" in p for p in found), found

    def test_the_requirements_docs_own_vip_example_is_rejected_naming_both_gaps(
            self, registry, ir_schema):
        """THE test in this file.

        control_rule_architecture.docx section 17 offers "All VIP arrivals should have an
        assigned room that is clean by 2 PM" as the sentence a compiler would handle. Neither
        field it needs exists: MiniHotel has no VIP flag at all - the only VIP information in
        the entire 2026 capture is Hebrew prose inside a free-text remarks field - and there is
        no housekeeping-status-at-a-time-of-day field either.

        The right answer is to refuse and say which two words are missing. A rule that ran
        would report PASS or FAIL about a question nobody can currently answer.
        """
        vip = {
            "control_id": "vip_arrival_clean_room", "version": 2, "source_control": "example",
            "name": "VIP Arrival Clean Room",
            "natural_language": "All VIP arrivals should have an assigned room that is clean "
                                "by 2 PM.",
            "entity": "reservation",
            "population": {"description": "arrivals today",
                           "provider_query": {"minihotel": {"endpoint": "x"}}},
            "references": [],
            "scope": [{"field": "reservation.vip", "operator": "equals", "value": True}],
            "exceptions": [],
            "assertion": {"mode": "all", "predicates": [
                {"field": "room.housekeeping_status_at", "operator": "equals",
                 "value": "clean"}]},
            "required_evidence": [
                {"field": "reservation.vip", "source": "pms"},
                {"field": "room.housekeeping_status_at", "source": "housekeeping"}],
            "execution": {"mode": "daily"},
            "freshness_requirement": {"maximum_age": "1h"},
            "unknown_conditions": [{"when": "no VIP flag exists", "reason": "not exposed"}],
            "action": {"type": "notify", "severity": "medium"},
        }
        found = problems(vip, registry, ir_schema)
        assert any("reservation.vip" in p for p in found), found
        assert any("room.housekeeping_status_at" in p for p in found), found

    def test_a_rule_may_not_read_evidence_it_never_declared(
            self, valid_ir, registry, ir_schema):
        """Otherwise a rule depends on a field the evidence layer was never asked to fetch,
        and the failure surfaces at runtime as an UNKNOWN that looks like the hotel's gap."""
        valid_ir["required_evidence"] = [
            e for e in valid_ir["required_evidence"] if e["field"] != "folio.balance_due"]
        found = problems(valid_ir, registry, ir_schema)
        assert any("folio.balance_due" in p and "required_evidence" in p for p in found), found


class TestSchemaEnforcement:
    def test_an_unknown_operator_is_rejected(self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["predicates"][0]["operator"] = "approximately_equals"
        assert problems(valid_ir, registry, ir_schema)

    def test_an_unknown_assertion_mode_is_rejected(self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["mode"] = "mostly"
        assert problems(valid_ir, registry, ir_schema)

    def test_a_missing_required_section_is_rejected(self, valid_ir, registry, ir_schema):
        del valid_ir["unknown_conditions"]
        found = problems(valid_ir, registry, ir_schema)
        assert any("unknown_conditions" in p for p in found), found

    def test_a_mistyped_property_name_is_rejected_rather_than_ignored(
            self, valid_ir, registry, ir_schema):
        """`additionalProperties: false` throughout. A clause spelled `assertions` must not
        validate while the real `assertion` quietly keeps whatever it had."""
        valid_ir["assertions"] = valid_ir["assertion"]
        found = problems(valid_ir, registry, ir_schema)
        assert any("assertions" in p for p in found), found

    def test_an_empty_natural_language_sentence_is_rejected(
            self, valid_ir, registry, ir_schema):
        """The sentence travels with the control and appears next to the verdict. A control
        that cannot say what it is checking is not auditable."""
        valid_ir["natural_language"] = ""
        assert problems(valid_ir, registry, ir_schema)


class TestPredicateShape:
    def test_a_predicate_with_two_right_hand_sides_is_ambiguous_and_refused(
            self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["predicates"][0]["compare_to"] = "reservation.total_amount"
        found = problems(valid_ir, registry, ir_schema)
        assert any("exactly one of" in p for p in found), found

    def test_a_predicate_with_no_right_hand_side_is_refused(
            self, valid_ir, registry, ir_schema):
        del valid_ir["assertion"]["predicates"][0]["value"]
        found = problems(valid_ir, registry, ir_schema)
        assert any("exactly one of" in p for p in found), found

    def test_exists_takes_no_value(self, valid_ir, registry, ir_schema):
        valid_ir["scope"].append(
            {"field": "reservation.id", "operator": "exists", "value": True})
        found = problems(valid_ir, registry, ir_schema)
        assert any("takes no value" in p for p in found), found

    def test_an_interval_operator_without_an_interval_is_refused(
            self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["predicates"] = [
            {"field": "reservation.departure_date", "operator": "within"}]
        found = problems(valid_ir, registry, ir_schema)
        assert any("needs an interval" in p for p in found), found

    def test_an_interval_on_an_operator_that_does_not_use_one_is_refused(
            self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["predicates"][0]["interval"] = {
            "start": "reservation.arrival_date", "end": "reservation.departure_date"}
        found = problems(valid_ir, registry, ir_schema)
        assert any("does not use an interval" in p for p in found), found


class TestAggregateShape:
    """v1 shipped two aggregate assertions with no grouping key at all, which is why duplicate
    detection could never be evaluated: the rule never said what a duplicate was OF (F2)."""

    def test_an_aggregate_assertion_must_declare_what_it_groups_by(
            self, registry, ir_schema):
        raw = copy.deepcopy(load("duplicate_channel_reservation").raw)
        del raw["assertion"]["group_by"]
        found = problems(raw, registry, ir_schema)
        assert any("group_by" in p for p in found), found

    def test_group_by_is_meaningless_outside_an_aggregate(
            self, valid_ir, registry, ir_schema):
        valid_ir["assertion"]["group_by"] = "reservation.id"
        found = problems(valid_ir, registry, ir_schema)
        assert any("only meaningful for an aggregate" in p for p in found), found

    def test_an_aggregate_operator_cannot_appear_in_scope(
            self, valid_ir, registry, ir_schema):
        """`count_lte` asks a question about a group. Scope decides whether the control
        applies to ONE record, and cannot see the group at all."""
        valid_ir["scope"].append(
            {"field": "reservation.id", "operator": "count_lte", "value": 1})
        found = problems(valid_ir, registry, ir_schema)
        assert any("cannot appear in scope" in p for p in found), found

    def test_a_record_level_operator_cannot_be_an_aggregates_assertion(
            self, registry, ir_schema):
        raw = copy.deepcopy(load("duplicate_channel_reservation").raw)
        raw["assertion"]["predicates"] = [
            {"field": "reservation.id", "operator": "exists"}]
        found = problems(raw, registry, ir_schema)
        assert any("must be aggregate operators" in p for p in found), found


class TestReferenceShape:
    """The joins v1 could not express, and therefore never executed (F1)."""

    def test_a_lookup_without_both_sides_of_its_join_is_refused(
            self, registry, ir_schema):
        """A half-declared join silently matches nothing, and every record comes back UNKNOWN
        for a reason that blames the hotel's data rather than the rule."""
        raw = copy.deepcopy(load("room_capacity_compliance").raw)
        del raw["references"][0]["remote_field"]
        found = problems(raw, registry, ir_schema)
        assert any("remote_field" in p for p in found), found

    def test_a_set_reference_needs_the_field_that_forms_the_set(
            self, registry, ir_schema):
        raw = copy.deepcopy(load("room_assignment_type_validity").raw)
        reference = next(r for r in raw["references"] if r["kind"] == "set")
        del reference["field"]
        found = problems(raw, registry, ir_schema)
        assert any("needs `field`" in p for p in found), found

    def test_a_remote_field_must_belong_to_the_entity_it_joins(
            self, registry, ir_schema):
        raw = copy.deepcopy(load("room_capacity_compliance").raw)
        raw["references"][0]["remote_field"] = "reservation.id"
        found = problems(raw, registry, ir_schema)
        assert any("does not belong to entity" in p for p in found), found

    def test_one_entity_cannot_be_referenced_twice(self, registry, ir_schema):
        """Two references to the same entity would give a field of that entity two possible
        sources, and whichever won would be an accident."""
        raw = copy.deepcopy(load("room_capacity_compliance").raw)
        raw["references"].append(copy.deepcopy(raw["references"][0]))
        found = problems(raw, registry, ir_schema)
        assert any("referenced twice" in p for p in found), found


class TestTenantSettings:
    def test_a_rule_naming_an_undeclared_tenant_setting_is_refused(
            self, registry, ir_schema, tenant):
        """Otherwise the setting resolves to an empty default, scope matches nothing, and the
        control reports a clean run over zero records - finding F5 by another route."""
        raw = copy.deepcopy(load("required_reservation_fields").raw)
        predicate = next(p for p in raw["scope"] if "tenant_setting" in p)
        predicate["tenant_setting"] = "codes_nobody_declared"
        found = problems(raw, registry, ir_schema, tenant)
        assert any("codes_nobody_declared" in p for p in found), found

    def test_control_15_reads_its_rate_codes_from_the_hotel_not_from_a_placeholder(self):
        """v1's IR carried the literal ["<hotel-nominated rate codes>"] inside a rule it then
        tried to execute. Which rate categories carry the requirement is the hotel's policy."""
        raw = load("required_reservation_fields").raw
        predicate = next(p for p in raw["scope"] if p["field"] == "stay.rate_code")
        assert predicate["tenant_setting"] == "nominated_rate_codes"
        assert "value" not in predicate


class TestLoading:
    def test_the_control_index_is_the_directory_listing(self):
        """Success criterion 6: a twelfth control is a file, not a branch."""
        from hotelcontrols.spec import available
        assert "checkout_money_owed" in available()

    def test_a_control_id_from_a_url_cannot_escape_the_spec_directory(self):
        with pytest.raises(SpecError):
            load("../../../etc/passwd")

    def test_an_unknown_control_is_a_spec_error_not_a_file_not_found(self):
        with pytest.raises(SpecError):
            load("no_such_control")
