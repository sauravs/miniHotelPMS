# -*- coding: utf-8 -*-
"""
Typed hotel parameters, and the difference between "decided: none" and "not decided".

Slice 21 (G6a, narrowed; docs/plan-v3.md §5). Until this slice a tenant setting was whatever
JSON the file held, and `[]` meant both "the hotel decided none" and "nobody has asked the
hotel" - `TenantConfig.setting`'s own docstring told you to write an empty value if the hotel
had not decided. In a SCOPE that is harmless: an empty list excludes every record. In an
EXCEPTION it exempts nobody, so every complimentary stay would FAIL - a confident accusation
manufactured from a missing answer (plan-v3 §5, slice 21, "why this is an accuracy slice").

So a parameter now has a declared type in `spec/parameters.json`, a tenant's values are checked
against it at load, and `null` is the one way to say "not decided". These tests are the type
system; `tests/integration/test_typed_parameters.py` is the slice's exit test end to end.

What each test protects is named: V8 (plan-v3 §7), R9 (money never without its currency), F11
(the property's clock is the only clock), and the "RACK" hazard fixed in #45.
"""
import datetime
import json
from decimal import Decimal

import pytest

from hotelcontrols.kernel import Money
from hotelcontrols.spec import SpecError, TenantConfig
from hotelcontrols.spec.parameters import ParameterSchema
from hotelcontrols.spec.registry import SPEC_DIR

# A schema covering every type, so each refusal is tested on the type it belongs to. The two
# shipped parameters are lists; money, times and choices arrive with slice 22's late-checkout
# template (D15), which may not change this package - so the types it needs are proven here,
# on parameters that exist only in this test.
EVERY_TYPE = {"parameters": {
    "codes": {"type": "text_list", "required": True},
    "room_types_by_rate": {"type": "text_list_map", "required": True},
    "fee_per_hour": {"type": "money", "required": True},
    "free_until": {"type": "time_of_day", "required": True},
    "hour_rounding": {"type": "choice", "options": ["started_hour", "whole_hour"],
                      "required": True},
    "optional_codes": {"type": "text_list", "required": False},
}}

DECIDED = {
    "codes": ["CORP", "RACK"],
    "room_types_by_rate": {"CORP": ["Executive", "Standard"]},
    "fee_per_hour": {"amount": "25.00", "currency": "USD"},
    "free_until": "14:00",
    "hour_rounding": "started_hour",
}


def tenant(settings, currencies=("ILS", "USD"), schema=EVERY_TYPE):
    """A tenant built from a dict and typed against `schema` - the same path `load` takes."""
    return TenantConfig.from_dict(
        {"tenant_id": "hotel_a", "provider": "minihotel", "timezone": "Asia/Jerusalem",
         "currencies": list(currencies), "settings": settings},
        parameters=ParameterSchema.from_dict(schema))


def refusal(settings, **kwargs) -> str:
    with pytest.raises(SpecError) as caught:
        tenant(settings, **kwargs)
    return str(caught.value)


# --------------------------------------------------------------------------- the shipped schema
class TestTheShippedSchema:
    def test_it_declares_every_setting_a_shipped_tenant_states(self):
        """Every value in spec/tenants/ has a declared type. A setting nobody typed is refused,
        so the schema and the tenant files cannot drift apart silently."""
        schema = ParameterSchema.load()
        for path in sorted((SPEC_DIR / "tenants").glob("*.json")):
            stated = json.loads(path.read_text(encoding="utf-8"))["settings"]
            assert set(stated) <= set(schema.parameters), path.name

    def test_the_two_settings_are_typed_as_what_the_engine_reads_them_as(self):
        """`nominated_rate_codes` is tested with `in` (control 15), so it is a list of text.
        `rate_plan_permitted_room_types` maps a rate code to the room types it may be sold in
        (R13, open question 1.6)."""
        schema = ParameterSchema.load()
        assert schema.parameters["nominated_rate_codes"].type == "text_list"
        assert schema.parameters["rate_plan_permitted_room_types"].type == "text_list_map"

    def test_no_shipped_parameter_has_a_default(self):
        """Plan-v3 §5: "required, no defaults". A default is the engine deciding for a hotel."""
        raw = json.loads((SPEC_DIR / "parameters.json").read_text(encoding="utf-8"))
        for name, definition in raw["parameters"].items():
            assert "default" not in definition, name


class TestASchemaIsCheckedBeforeAnyTenantIs:
    def test_a_parameter_with_a_default_is_refused_by_name(self):
        """No defaults. A hotel decision nobody made must never be filled in by the engine -
        that is the anti-criterion "a missing hotel decision is read as none", by another door."""
        with pytest.raises(SpecError, match="fee_per_hour.*default"):
            ParameterSchema.from_dict({"parameters": {
                "fee_per_hour": {"type": "money", "required": True,
                                 "default": {"amount": "0", "currency": "USD"}}}})

    def test_an_unknown_type_is_refused_by_name(self):
        with pytest.raises(SpecError, match="vip_rate.*'percent'"):
            ParameterSchema.from_dict({"parameters": {
                "vip_rate": {"type": "percent", "required": True}}})

    def test_a_choice_must_say_what_it_chooses_between(self):
        with pytest.raises(SpecError, match="hour_rounding.*options"):
            ParameterSchema.from_dict({"parameters": {
                "hour_rounding": {"type": "choice", "required": True}}})

    def test_options_on_anything_but_a_choice_are_refused(self):
        with pytest.raises(SpecError, match="codes.*options"):
            ParameterSchema.from_dict({"parameters": {
                "codes": {"type": "text_list", "options": ["A"], "required": True}}})

    def test_required_is_stated_not_assumed(self):
        """`required` says whether a tenant file must STATE the parameter (decided or null).
        Leaving it out would make that a default of its own."""
        with pytest.raises(SpecError, match="codes.*required"):
            ParameterSchema.from_dict({"parameters": {"codes": {"type": "text_list"}}})

    def test_a_misspelt_key_is_refused_rather_than_ignored(self):
        """`requried: false` ignored would leave `required` unstated - or, in a laxer loader,
        silently true. Either way the schema would not say what its author wrote."""
        with pytest.raises(SpecError, match="codes.*requried"):
            ParameterSchema.from_dict({"parameters": {
                "codes": {"type": "text_list", "required": True, "requried": False}}})

    def test_a_definition_must_be_an_object(self):
        with pytest.raises(SpecError, match="codes.*object"):
            ParameterSchema.from_dict({"parameters": {"codes": "text_list"}})

    def test_a_schema_must_hold_a_parameters_object(self):
        with pytest.raises(SpecError, match="parameters"):
            ParameterSchema.from_dict({"nominated_rate_codes": {"type": "text_list"}})

    def test_a_spec_with_no_schema_cannot_type_a_tenant(self, tmp_path):
        """Refused, not treated as an empty schema: no schema means nothing is typed, which
        is the state this slice removes."""
        with pytest.raises(SpecError, match="parameters.json"):
            ParameterSchema.load(tmp_path)


# --------------------------------------------------------------------------- decided values
class TestDecidedValuesAreTyped:
    def test_every_type_reads_into_what_the_engine_uses(self):
        """Money parameters are `Money` with their currency (plan-v3 §5); a time of day is a
        time; a list is immutable, so a running engine cannot be taught a new code mid-run."""
        settings = tenant(DECIDED).settings
        assert settings["codes"] == ("CORP", "RACK")
        assert settings["room_types_by_rate"] == {"CORP": ("Executive", "Standard")}
        assert settings["fee_per_hour"] == Money(Decimal("25.00"), "USD")
        assert settings["free_until"] == datetime.time(14, 0)
        assert settings["hour_rounding"] == "started_hour"

    def test_an_empty_list_is_a_decision_and_stays_one(self):
        """`[]` still means "the hotel decided none". It is legal and it is DECIDED - the
        evaluator sees it, and a scope over it excludes every record honestly."""
        hotel = tenant(dict(DECIDED, codes=[]))
        assert hotel.settings["codes"] == ()
        assert hotel.is_decided("codes")

    def test_an_optional_parameter_may_be_left_out_entirely(self):
        hotel = tenant(DECIDED)
        assert not hotel.has_setting("optional_codes")


class TestWrongValuesAreRefusedByName:
    """Plan-v3 §5, slice 21 exit test: "A string where a list is required, a bare number where
    Money is required, and a currency the property does not use are each refused by name.\""""

    def test_a_string_where_a_list_is_required(self):
        """The "RACK" hazard (#45): `"RACK" in tuple("RACK")` is False, so a one-code hotel
        writing "RACK" for ["RACK"] would have excluded every record. Refused at load now, where
        the reason can name the setting, rather than only when a control happens to use it."""
        message = refusal(dict(DECIDED, codes="RACK"))
        assert "codes" in message and "list" in message and "'RACK'" in message

    def test_a_bare_number_where_money_is_required(self):
        """R9. A number with no currency cannot be compared with anything this engine holds."""
        message = refusal(dict(DECIDED, fee_per_hour=25))
        assert "fee_per_hour" in message and "currency" in message and "25" in message

    def test_a_currency_the_property_does_not_use(self):
        message = refusal(dict(DECIDED, fee_per_hour={"amount": "25.00", "currency": "GBP"}))
        assert "fee_per_hour" in message and "GBP" in message
        assert "ILS, USD" in message                     # and it says what the property uses

    def test_money_for_a_property_that_states_no_currencies_cannot_be_checked(self):
        """Refused rather than waved through: "a currency the property does not use" cannot be
        established when the property has not said which it uses."""
        message = refusal(DECIDED, currencies=())
        assert "fee_per_hour" in message and "currencies" in message

    def test_an_amount_written_as_a_json_number_is_refused(self):
        """Money is Decimal (CLAUDE.md). JSON numbers arrive as binary floats, and 0.1 + 0.2 is
        not 0.3 in one of them, so the amount is written as text and read exactly."""
        message = refusal(dict(DECIDED, fee_per_hour={"amount": 25.5, "currency": "USD"}))
        assert "fee_per_hour" in message and "string" in message

    @pytest.mark.parametrize("amount", ["", "twenty", "NaN", "Infinity"])
    def test_an_amount_that_is_not_an_amount(self, amount):
        message = refusal(dict(DECIDED, fee_per_hour={"amount": amount, "currency": "USD"}))
        assert "fee_per_hour" in message

    def test_money_with_anything_but_an_amount_and_a_currency(self):
        message = refusal(dict(DECIDED, fee_per_hour={"amount": "25", "currency": "USD",
                                                      "per": "hour"}))
        assert "fee_per_hour" in message

    @pytest.mark.parametrize("written", ["3 PM", "15", "24:00", "15:00:00", "9:00", 1500])
    def test_a_time_that_is_not_hh_mm(self, written):
        message = refusal(dict(DECIDED, free_until=written))
        assert "free_until" in message and "HH:MM" in message

    @pytest.mark.parametrize("written", ["15:00+03:00", "15:00Z", "15:00 UTC"])
    def test_a_time_on_another_clock_is_refused_not_converted(self, written):
        """F11, and the "unit" in "wrong type, unit or currency". A hotel's times are on its
        own clock; an offset would be a second clock, and converting it would be the engine
        guessing which day the hotel meant."""
        message = refusal(dict(DECIDED, free_until=written))
        assert "free_until" in message and "clock" in message

    def test_a_choice_outside_its_options(self):
        message = refusal(dict(DECIDED, hour_rounding="nearest_hour"))
        assert "hour_rounding" in message and "started_hour" in message

    def test_a_list_holding_something_other_than_text(self):
        message = refusal(dict(DECIDED, codes=["RACK", 7]))
        assert "codes" in message

    def test_a_blank_code_in_a_list(self):
        """A blank code matches nothing a PMS sends, so it would quietly do nothing."""
        message = refusal(dict(DECIDED, codes=["RACK", "  "]))
        assert "codes" in message

    def test_a_map_whose_values_are_not_lists(self):
        message = refusal(dict(DECIDED, room_types_by_rate={"CORP": "Executive"}))
        assert "room_types_by_rate" in message and "'CORP'" in message

    def test_a_list_where_a_map_is_required(self):
        message = refusal(dict(DECIDED, room_types_by_rate=["CORP"]))
        assert "room_types_by_rate" in message and "list" in message

    def test_a_map_with_a_blank_key(self):
        message = refusal(dict(DECIDED, room_types_by_rate={" ": ["Executive"]}))
        assert "room_types_by_rate" in message and "blank" in message

    @pytest.mark.parametrize("currency", ["", "  ", None])
    def test_money_with_no_currency(self, currency):
        """R9: "an amount without a currency is not evidence" - nor is it a setting."""
        message = refusal(dict(DECIDED, fee_per_hour={"amount": "25.00", "currency": currency}))
        assert "fee_per_hour" in message and "currency" in message

    def test_settings_that_are_not_an_object(self):
        with pytest.raises(SpecError, match="settings must be an object"):
            ParameterSchema.from_dict(EVERY_TYPE).typed(["codes"], tenant_id="hotel_a",
                                                        currencies=("USD",))

    def test_a_setting_the_schema_does_not_declare(self):
        """An untyped value cannot be checked, so it is refused rather than passed through."""
        message = refusal(dict(DECIDED, nominated_unicorns=["X"]))
        assert "nominated_unicorns" in message

    def test_a_required_parameter_left_out_entirely(self):
        """A required parameter must be STATED - `null` if undecided - so that "nobody wrote
        this down" is visible in the file rather than inferred from an absence."""
        settings = dict(DECIDED)
        del settings["codes"]
        message = refusal(settings)
        assert "codes" in message and "null" in message

    def test_every_problem_is_reported_not_only_the_first(self):
        message = refusal(dict(DECIDED, codes="RACK", fee_per_hour=25))
        assert "codes" in message and "fee_per_hour" in message


# --------------------------------------------------------------------------- not decided
class TestNullMeansNotDecided:
    """V8 at the configuration layer: null is "not decided", which is neither "none" nor an
    error. It is accepted for every type and kept apart from every decided value."""

    @pytest.mark.parametrize("name", sorted(EVERY_TYPE["parameters"]))
    def test_null_is_accepted_for_every_type(self, name):
        hotel = tenant(dict(DECIDED, **{name: None}))
        assert hotel.has_setting(name)
        assert not hotel.is_decided(name)
        assert name in hotel.undecided

    @pytest.mark.parametrize("name", sorted(DECIDED))
    def test_an_undecided_parameter_is_not_among_the_values_the_evaluator_sees(self, name):
        """The mechanism, and why no evaluator change is needed. `tenant.settings` is what the
        runner hands the evaluator, and the evaluator's existing branch answers UNKNOWN - "this
        property has not supplied X" - for a name that is not in it."""
        hotel = tenant(dict(DECIDED, **{name: None}))
        assert name not in hotel.settings
        assert None not in hotel.settings.values()

    def test_reading_an_undecided_parameter_raises_naming_it(self):
        """No caller can receive None and treat it as empty: that is the bug this slice fixes,
        so the accessor refuses rather than returns."""
        hotel = tenant(dict(DECIDED, codes=None))
        with pytest.raises(SpecError, match="codes.*not decided"):
            hotel.setting("codes")

    def test_null_is_not_decided_even_without_a_schema(self):
        """A tenant built in a test, with no schema to check against, still never shows the
        evaluator a None."""
        hotel = TenantConfig(tenant_id="t", provider="minihotel", timezone="Asia/Jerusalem",
                             settings={"nominated_rate_codes": None, "other": []})
        assert hotel.undecided == ("nominated_rate_codes",)
        assert hotel.settings == {"other": []}

    def test_a_name_cannot_be_both_decided_and_undecided(self):
        with pytest.raises(SpecError, match="codes"):
            TenantConfig(tenant_id="t", provider="minihotel", timezone="Asia/Jerusalem",
                         settings={"codes": []}, undecided=("codes",))


# --------------------------------------------------------------------------- currencies
class TestTheCurrenciesAPropertyUses:
    def test_they_are_iso_style_codes(self):
        """Checked BEFORE any money is read against them, so a misspelt `usd` is reported as
        itself rather than as the fee being "in a currency the property does not use"."""
        with pytest.raises(SpecError, match="currency 'usd' is not a three-letter code"):
            tenant(DECIDED, currencies=("ILS", "usd"))

    def test_a_single_code_is_still_written_as_a_list(self):
        """The "RACK" hazard again: `"USD"` iterated is "U", "S", "D"."""
        with pytest.raises(SpecError, match="currencies must be a list"):
            TenantConfig.from_dict(
                {"tenant_id": "hotel_a", "provider": "minihotel", "timezone": "Asia/Jerusalem",
                 "currencies": "USD", "settings": DECIDED},
                parameters=ParameterSchema.from_dict(EVERY_TYPE))

    def test_the_shipped_tenants_state_the_currencies_their_captures_show(self):
        """R9: reservations in USD (and EUR in 2024), folios in ILS. Observed, not decided -
        the tenant files cite the captures. Both providers carry the same hotel, so the same
        three."""
        for tenant_id in ("sandbox", "demo"):
            assert TenantConfig.load(tenant_id).currencies == ("EUR", "ILS", "USD")
