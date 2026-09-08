# -*- coding: utf-8 -*-
"""
The whole specification, checked together.

The unit tests prove each rule fires. This proves the eleven controls we actually ship are
clean against it - which is the difference between a validator that works and a specification
that is valid.

v1's equivalent ran 880 checks and had already caught two claims that were wrong about the
data. That is the bar: the validator is not ceremony, it is the thing that catches a field path
which does not exist before a hotel is told its data is fine.
"""
import ast
import json
import pathlib
import zoneinfo

import pytest

from hotelcontrols.spec import Registry, TenantConfig, available, load, load_schema, validate

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"

# Every real IANA zone, so the check below cannot be defeated by picking a different city and
# cannot fire on an unrelated string that merely contains a slash.
_IANA_ZONES = zoneinfo.available_timezones()

EXPECTED_CONTROLS = {
    "checkout_money_owed", "checkout_unrefunded_credit", "duplicate_channel_reservation",
    "inactive_room_future_stay", "ooo_room_protection", "rate_room_category_consistency",
    "required_reservation_fields", "resource_occupancy_consistency",
    "room_assignment_active_room", "room_assignment_type_validity", "room_capacity_compliance",
}


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def ir_schema():
    return load_schema()


@pytest.fixture(scope="module")
def tenant():
    return TenantConfig.load("sandbox")


class TestTheShippedControls:
    def test_eleven_controls_ship(self):
        """Ten from the dry run, with control 6 split in two (decision D8)."""
        assert set(available()) == EXPECTED_CONTROLS

    @pytest.mark.parametrize("control_id", sorted(EXPECTED_CONTROLS))
    def test_every_shipped_control_validates(self, control_id, registry, ir_schema, tenant):
        found = validate(load(control_id), registry, tenant=tenant, ir_schema=ir_schema)
        assert not found, "\n".join(str(p) for p in found)

    @pytest.mark.parametrize("control_id", sorted(EXPECTED_CONTROLS))
    def test_every_control_carries_the_sentence_it_came_from(self, control_id):
        """The chain 'rule as written -> answer -> evidence' has to be visible on screen, and
        that starts with the control knowing what it was asked to check."""
        ir = load(control_id)
        assert ir.natural_language.strip()
        assert ir.natural_language.strip().endswith("."), \
            "the natural-language rule should read as a sentence"

    @pytest.mark.parametrize("control_id", sorted(EXPECTED_CONTROLS))
    def test_every_control_says_how_it_can_fail_to_answer(self, control_id):
        """A control that cannot say when it is unable to answer is incompletely specified -
        and UNKNOWN is a first-class result here, not an error path."""
        assert load(control_id)["unknown_conditions"]

    def test_all_twenty_source_controls_are_accounted_for(self):
        """Each shipped IR names the row in Hotel Controls.docx it implements, so the
        feasibility workbook and the engine cannot drift apart."""
        rows = {load(c)["source_control"] for c in available()}
        assert rows == {"1a-1c", "1d", "2", "4", "6", "9", "13", "14", "15", "20"}


class TestControlSixIsNowTwoControls:
    """Decision D8. Reservation 007004348 checked out at -490.75 ILS - the guest overpaid and
    the hotel owes a refund - and v1 reported that as an outstanding balance. Correct as
    specified, and not what a finance team means by the phrase."""

    def test_money_owed_flags_only_positive_balances(self):
        predicate = load("checkout_money_owed")["assertion"]["predicates"][0]
        assert (predicate["field"], predicate["operator"], predicate["value"]) == \
            ("folio.balance_due", "lte", 0)

    def test_unrefunded_credit_flags_only_negative_balances(self):
        predicate = load("checkout_unrefunded_credit")["assertion"]["predicates"][0]
        assert (predicate["field"], predicate["operator"], predicate["value"]) == \
            ("folio.balance_due", "gte", 0)

    def test_both_compare_against_literal_zero_so_neither_can_trip_over_r9(self):
        """The folio is in ILS while the reservation is in USD and no exchange rate exists
        anywhere in the API. Comparing against zero sidesteps that by construction, because
        zero is the same amount in every currency."""
        for control_id in ("checkout_money_owed", "checkout_unrefunded_credit"):
            for predicate in load(control_id)["assertion"]["predicates"]:
                assert predicate.get("value") == 0
                assert "compare_to" not in predicate

    def test_they_carry_different_severities_because_they_are_different_events(self):
        """Money owed is a collections problem and a probable loss; an unrefunded credit is a
        liability with a different urgency and usually a different team. Folding them together
        makes the severity meaningless for both."""
        assert load("checkout_money_owed")["action"]["severity"] == "high"
        assert load("checkout_unrefunded_credit")["action"]["severity"] == "medium"


class TestVocabularyCoverage:
    def test_every_canonical_field_is_mapped_or_declared_unresolvable(self, registry):
        """A field that is neither is a gap nobody has decided about: a control referencing it
        would return UNKNOWN at runtime for a reason no document explains."""
        provider = json.loads((SPEC / "providers" / "minihotel.json").read_text())
        mapped = {m["canonical"] for m in provider["mappings"]}
        unresolvable = {f.field for f in registry.unresolvable()}
        orphans = sorted(set(registry.field_names) - mapped - unresolvable)
        assert not orphans, (
            "these fields are neither mapped by a provider nor marked unresolvable: %s"
            % orphans)

    def test_the_unresolvable_fields_are_exactly_the_rate_plan_ones(self, registry):
        """R13, and it is a fact about the vocabulary rather than a bug in an adapter: a
        reservation's rate code and the Bulk ARI price-list code are different key spaces, so
        no MiniHotel endpoint can join them. Control 9 answers UNKNOWN with that reason, which
        is the 'connect this to enable the control' path working as designed."""
        assert {f.field for f in registry.unresolvable()} == \
            {"rate_plan.code", "rate_plan.permitted_room_types"}

    def test_every_provider_mapping_names_a_declared_canonical_field(self, registry):
        provider = json.loads((SPEC / "providers" / "minihotel.json").read_text())
        undeclared = sorted(m["canonical"] for m in provider["mappings"]
                            if not registry.has(m["canonical"]))
        assert not undeclared, undeclared

    def test_no_canonical_field_is_mapped_twice(self):
        """Two mappings for one field means two possible sources and a coin toss."""
        provider = json.loads((SPEC / "providers" / "minihotel.json").read_text())
        seen, duplicates = set(), []
        for mapping in provider["mappings"]:
            if mapping["canonical"] in seen:
                duplicates.append(mapping["canonical"])
            seen.add(mapping["canonical"])
        assert not duplicates, duplicates


class TestReferencesUnlockTheBlockedControls:
    """Finding F1. In v1, three controls returned 111 UNKNOWN out of 111 records because a
    record could never be joined to property-wide data. The joins are now declared."""

    @pytest.mark.parametrize("control_id", [
        "room_assignment_type_validity", "room_assignment_active_room",
        "room_capacity_compliance", "inactive_room_future_stay"])
    def test_the_room_joining_controls_declare_their_join(self, control_id):
        room = [r for r in load(control_id).references if r["entity"] == "room"]
        assert room, "%s needs the room master and must say how it joins to it" % control_id
        assert room[0]["local_field"] == "stay.room_number"
        assert room[0]["remote_field"] == "room.number"

    def test_the_aggregate_controls_declare_what_they_group_by(self):
        assert load("duplicate_channel_reservation")["assertion"]["group_by"] == \
            "reservation.channel_confirmation_id"
        assert load("resource_occupancy_consistency")["assertion"]["group_by"] == \
            "occupancy.room_number"

    def test_duplicate_detection_excludes_cancellations_before_grouping(self):
        """R7. An OTA modification is a cancel plus a recreate reusing the same portal id, and
        7 of 11 sandbox bookings are direct with no portal id at all. Without both guards every
        direct booking is a duplicate of every other one."""
        ir = load("duplicate_channel_reservation")
        assert {"field": "reservation.status", "operator": "not_equals",
                "value": "cancelled"} in ir["scope"]
        assert any(p["field"] == "reservation.channel_confirmation_id"
                   and p["operator"] == "not_exists" for p in ir["exceptions"])


class TestTenantConfigurationIsNotInTheCode:
    """Slice 1 gate, and the fix for finding F12 / v1's open question 1.4."""

    def test_no_provider_status_or_department_map_remains_in_python(self):
        """F12 / v1's open question 1.4. A property's status vocabulary is configuration.

        Checked for an actual DICT LITERAL mapping provider codes to canonical statuses -
        which is the thing being banned - rather than for the words appearing anywhere. The
        adapter's docstring necessarily says "a control speaks checked_out; only this layer
        knows a hotel writes OUT", and a grep that cannot tell an explanation from an
        implementation pushes us to delete the explanation.
        """
        engine = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"
        codes = {"OUT", "CL", "IN", "OK", "OK4", "WL", "LWP"}
        canonical = {"checked_out", "checked_in", "cancelled", "confirmed"}
        offenders = []
        for path in engine.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Dict):
                    continue
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                values = {v.value for v in node.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str)}
                if keys & codes and values & canonical:
                    offenders.append("%s line %d maps %s -> %s"
                                     % (path.name, node.lineno, sorted(keys & codes),
                                        sorted(values & canonical)))
        assert not offenders, (
            "a property's status vocabulary belongs in spec/tenants/, not in the engine: %s"
            % offenders)

    def test_no_timezone_is_hard_coded_in_the_engine(self):
        """F11. A property's timezone decides which records a control even looks at, so it is
        the hotel's configuration and must arrive as data.

        Checked over string constants the code actually EVALUATES, with docstrings excluded:
        `clock.py` explains the Jerusalem-versus-UTC example at length in prose, and prose that
        documents why a value must not be hard-coded is not the value being hard-coded. A
        cruder grep flags that comment, which would push us to delete the best explanation in
        the file to make a test pass.
        """
        engine = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"
        offenders = []
        for path in engine.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and id(node) not in docstrings and "/" in node.value
                        and node.value in _IANA_ZONES):
                    offenders.append("%s line %d: %r" % (path.name, node.lineno, node.value))
        assert not offenders, (
            "a property's timezone belongs in spec/tenants/, not in the engine: %s" % offenders)
