# -*- coding: utf-8 -*-
"""
Value - the only thing the provider layer hands upwards.

    Value = known(payload, unit) | unknown(reason, risk)

Two states, no third. Everything the engine learns about a hotel arrives wrapped in one of
them, which is what makes UNKNOWN a first-class result rather than an exception somebody
forgot to catch.

The single most important test in this file is
`test_an_unknown_refuses_to_compare_rather_than_answering_false`. If `unknown == 0` returned
False, a caller writing the obvious `PASS if v == 0 else FAIL` would report FAIL for a
reservation whose balance was never established. That one line is the failure mode this
entire product exists to prevent.
"""
from decimal import Decimal

import pytest

from hotelcontrols.kernel import (NOT_APPLICABLE, CurrencyMismatch, Money, UnitRequired,
                                  UnknownValue, Value)


class TestKnown:
    def test_a_number_cannot_exist_without_a_unit(self):
        """R9. 23 of 28 sandbox rooms report capacity as a bare integer; a balance is an
        amount in a currency. Neither is evidence until it says what it is counting."""
        with pytest.raises(UnitRequired):
            Value.known(3)

    def test_a_number_with_a_unit_is_fine(self):
        adults = Value.known(3, unit="count")
        assert adults.payload == 3
        assert adults.unit == "count"

    def test_money_carries_its_own_unit_and_needs_no_second_one(self):
        balance = Value.known(Money.parse("3262.5", "ILS"))
        assert balance.unit == "ILS"

    def test_a_float_payload_is_refused_outright(self):
        """F10. There is no canonical field for which a float is the right representation:
        amounts are Money, counts are int, everything else is a string or a date."""
        with pytest.raises(TypeError):
            Value.known(3262.5, unit="ILS")

    def test_a_bare_decimal_still_needs_a_unit(self):
        with pytest.raises(UnitRequired):
            Value.known(Decimal("3262.5"))

    def test_a_boolean_needs_no_unit_because_a_flag_is_not_a_measurement(self):
        """bool is a subclass of int in Python, so this is a real edge the check must handle."""
        assert Value.known(True).payload is True

    def test_a_string_needs_no_unit(self):
        assert Value.known("checked_out").payload == "checked_out"

    def test_a_known_value_carries_where_it_came_from(self):
        """An auditor needs to know which system and which call produced a number."""
        v = Value.known("checked_out", source="pms:minihotel/GetReservationKey")
        assert v.source == "pms:minihotel/GetReservationKey"


class TestUnknown:
    def test_an_unknown_without_a_reason_cannot_be_constructed(self):
        """An UNKNOWN without a reason tells a hotel nothing about what to fix, so it is
        not auditable, so it is not allowed to exist."""
        with pytest.raises(ValueError):
            Value.unknown("")

    def test_an_unknown_whose_reason_is_only_whitespace_is_also_refused(self):
        with pytest.raises(ValueError):
            Value.unknown("   ")

    def test_an_unknown_carries_its_reason_and_risk_id(self):
        v = Value.unknown("0 means unconfigured in this PMS, not zero", risk="R12")
        assert v.is_known is False
        assert v.risk == "R12"
        assert "unconfigured" in v.reason

    def test_an_unknown_has_no_payload(self):
        """A second, shadow vocabulary for 'we sort of have a value' is how UNKNOWN gets
        quietly downgraded to a guess."""
        assert Value.unknown("balance not established").payload is None

    def test_an_unknown_cannot_be_handed_a_payload(self):
        with pytest.raises(ValueError):
            Value(is_known=False, payload="something", reason="a reason")


class TestComparisonRefusals:
    def test_an_unknown_refuses_to_compare_rather_than_answering_false(self):
        """THE test. See the module docstring.

        The comparison raises, which forces the caller to handle UNKNOWN explicitly instead
        of letting a missing balance silently become a violation.
        """
        never_fetched = Value.unknown("the folio call failed", risk="R1")
        with pytest.raises(UnknownValue):
            never_fetched.equals(0)

    def test_comparing_against_an_unknown_also_refuses(self):
        known = Value.known(Money.parse("0", "ILS"))
        with pytest.raises(UnknownValue):
            known.equals(Value.unknown("not established"))

    def test_two_amounts_in_different_currencies_refuse_to_compare(self):
        """R9, at the Value level - the guard has to hold wherever the amounts meet."""
        folio = Value.known(Money.parse("3262.5", "ILS"))
        reservation = Value.known(Money.parse("870", "USD"))
        with pytest.raises(CurrencyMismatch):
            folio.equals(reservation)

    def test_an_amount_compares_against_literal_zero_in_any_currency(self):
        """Control 6's assertion, and the reason it is currency-safe by construction."""
        assert Value.known(Money.parse("0", "ILS")).equals(0) is True
        assert Value.known(Money.parse("812.5", "ILS")).equals(0) is False

    def test_a_count_and_an_amount_do_not_compare(self):
        guests = Value.known(3, unit="count")
        balance = Value.known(Money.parse("3", "ILS"))
        with pytest.raises(CurrencyMismatch):
            guests.equals(balance)


class TestNotApplicable:
    def test_not_applicable_is_distinct_from_absent_empty_and_false(self):
        """R7. Seven of eleven sandbox bookings are direct and carry no portal id at all.
        'There is no channel confirmation because there was no channel' is a FACT, not a
        gap - and it must not be an empty string, or every direct booking looks like a
        duplicate of every other one."""
        assert NOT_APPLICABLE is not None
        assert NOT_APPLICABLE != ""
        assert NOT_APPLICABLE is not False
        assert NOT_APPLICABLE != 0

    def test_not_applicable_is_falsy_but_is_not_false(self):
        assert not NOT_APPLICABLE
        assert NOT_APPLICABLE is not False

    def test_a_not_applicable_value_is_known(self):
        """We know the answer: there isn't one. That is different from not knowing."""
        v = Value.known(NOT_APPLICABLE)
        assert v.is_known is True
        assert v.payload is NOT_APPLICABLE

    def test_repr_says_what_it_is(self):
        assert repr(NOT_APPLICABLE) == "NOT_APPLICABLE"


class TestStructuralEquality:
    def test_structural_equality_ignores_provenance(self):
        """`==` asks 'is this the same piece of evidence?'. The same record resolved through
        the frozen path and through a live transport must compare equal - that is the gate
        that proves the two paths agree."""
        frozen = Value.known("checked_out", source="pms:minihotel/frozen")
        live = Value.known("checked_out", source="pms:minihotel/live")
        assert frozen == live

    def test_structural_equality_never_raises_even_for_unknowns(self):
        """Distinct from `.equals()`, which enforces the domain rules and raises."""
        assert Value.unknown("a") == Value.unknown("a")
        assert Value.unknown("a") != Value.unknown("b")

    def test_a_value_is_immutable(self):
        v = Value.known("checked_out")
        with pytest.raises((AttributeError, TypeError)):
            v.payload = "confirmed"
