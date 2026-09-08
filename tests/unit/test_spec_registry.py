# -*- coding: utf-8 -*-
"""
The canonical field registry - the vocabulary a rule is allowed to use.

This is the layer that makes "the rule never names a PMS" enforceable rather than aspirational.
A control may reference `folio.balance_due`; it may not reference `TotalDebit`, and it may not
reference `reservation.vip` either, because nobody has defined what that would mean or where it
would come from.

`absent_means` is the interesting column and it is per field, not global:

    unknown          the field should be there and is not - an evidence gap
    false            its absence IS the signal (control 15 tests exactly that)
    not_applicable   a direct booking genuinely has no channel confirmation (R7)

Getting that wrong in either direction is a wrong verdict: treating an absent portal id as an
evidence gap makes every direct booking UNKNOWN, and treating it as an empty string makes every
direct booking a duplicate of every other.
"""
import pytest

from hotelcontrols.spec import FieldSpec, Registry, SpecError


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


class TestVocabulary:
    def test_the_registry_defines_the_entities_the_controls_speak_about(self):
        assert Registry.load().entities >= {
            "reservation", "stay", "room", "room_type", "folio", "occupancy", "rate_plan"}

    def test_a_field_carries_its_type_and_what_its_absence_means(self, registry):
        status = registry.field("reservation.status")
        assert isinstance(status, FieldSpec)
        assert status.type == "enum"
        assert status.absent_means == "unknown"

    def test_a_channel_confirmation_id_is_not_applicable_when_absent(self, registry):
        """R7. 7 of 11 sandbox bookings are direct. 'There was no channel' is a fact."""
        assert registry.field("reservation.channel_confirmation_id").absent_means == \
            "not_applicable"

    def test_money_fields_are_typed_money_so_they_can_never_be_bare_numbers(self, registry):
        """R9 begins here: the registry types the field, and the provider layer may not
        override it with a looser one."""
        assert registry.field("folio.balance_due").type == "money"
        assert registry.field("reservation.total_amount").type == "money"

    def test_a_field_nobody_declared_is_a_spec_error_not_a_silent_none(self, registry):
        with pytest.raises(SpecError) as caught:
            registry.field("reservation.vip")
        assert "reservation.vip" in str(caught.value)

    def test_capacity_fields_carry_the_risk_that_explains_their_zeroes(self, registry):
        """R12 - 23 of 28 sandbox rooms report adult capacity 0, meaning unconfigured. The
        risk id travels with the field so it reaches the screen next to the UNKNOWN."""
        assert registry.field("room.max_guests.adults").risk == "R12"

    def test_the_unresolvable_field_is_marked_as_such_with_its_reason(self, registry):
        """R13. A reservation's rate code and the ARI price-list code are different key
        spaces, so control 9's evidence cannot be obtained from this provider at all. That is
        a property of the VOCABULARY, not a bug to be fixed in an adapter."""
        permitted = registry.field("rate_plan.permitted_room_types")
        assert permitted.resolvable is False
        assert permitted.risk == "R13"


class TestRegistryIntegrity:
    def test_every_field_name_is_entity_qualified(self, registry):
        """`balance_due` alone is ambiguous the moment a second entity has one."""
        bad = [f for f in registry.field_names if "." not in f]
        assert not bad, bad

    def test_every_fields_entity_prefix_is_a_declared_entity(self, registry):
        bad = [f for f in registry.field_names if f.split(".")[0] not in registry.entities]
        assert not bad, bad

    def test_absent_means_is_one_of_exactly_three_things(self, registry):
        allowed = {"unknown", "false", "not_applicable"}
        bad = [f for f in registry.field_names
               if registry.field(f).absent_means not in allowed]
        assert not bad, bad

    def test_the_registry_is_immutable_once_loaded(self, registry):
        with pytest.raises((AttributeError, TypeError)):
            registry.field("reservation.status").type = "string"
