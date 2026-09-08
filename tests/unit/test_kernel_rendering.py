# -*- coding: utf-8 -*-
"""
How evidence reads on screen, and the guards that were not exercised elsewhere.

Rendering is not cosmetic here. Success criterion 3 is that every verdict traces to the
fields that produced it - name, value, UNIT, and provenance - so `str(Value)` is the criterion
itself, not a debugging convenience. A balance rendered as `812.5` rather than `812.5 ILS` is
a criterion-3 failure however correct the arithmetic behind it was.

The requirements doc (§20) is explicit about the shape: a table of field and value next to the
verdict, so a human can see why. These tests pin the cell contents.
"""
from datetime import datetime
from decimal import Decimal

import pytest

from hotelcontrols.kernel import (NOT_APPLICABLE, CurrencyMismatch, EvidenceLine, FixedClock,
                                  Money, Outcome, PropertyClock, Value, Verdict)


class TestValueReadsAsEvidence:
    def test_an_amount_renders_with_its_currency(self):
        """Never a bare number. R9 is invisible to a reader unless the unit is on screen."""
        assert str(Value.known(Money.parse("-490.75", "ILS"))) == "-490.75 ILS"

    def test_a_count_renders_with_its_unit(self):
        assert str(Value.known(3, unit="count")) == "3 count"

    def test_a_date_renders_bare_because_the_unit_would_be_noise(self):
        """"2026-07-08 date" reads worse than "2026-07-08" and tells a reader nothing extra."""
        assert str(Value.known("2026-07-08", unit="date")) == "2026-07-08"

    def test_an_unknown_renders_its_reason_not_a_blank(self):
        """This string is the whole product value of an UNKNOWN: what to go and fix."""
        rendered = str(Value.unknown("the folio call failed", risk="R1"))
        assert rendered == "unknown (the folio call failed)"

    def test_not_applicable_renders_as_itself_and_not_as_empty(self):
        """R7. "not applicable" and "" must never look the same to a reader, or a direct
        booking with no channel id reads as a booking whose channel id went missing."""
        assert str(Value.known(NOT_APPLICABLE)) == "not applicable"

    def test_a_plain_string_renders_plainly(self):
        assert str(Value.known("checked_out")) == "checked_out"

    def test_repr_distinguishes_known_from_unknown_at_a_glance(self):
        assert repr(Value.known(Money.parse("0", "ILS"))) == "known(0 ILS)"
        assert repr(Value.unknown("no folio", risk="R1")) == "unknown(no folio [R1])"
        assert repr(Value.unknown("no folio")) == "unknown(no folio)"


class TestEvidenceLine:
    def test_a_line_inherits_provenance_from_its_value(self):
        """A line cannot claim a different origin from the evidence it contains."""
        value = Value.known("checked_out", source="pms:minihotel/GetReservationKey")
        assert EvidenceLine("reservation.status", value).source == \
            "pms:minihotel/GetReservationKey"

    def test_an_explicit_source_is_kept(self):
        value = Value.known("checked_out")
        assert EvidenceLine("reservation.status", value, source="pms:demopms/bookings").source \
            == "pms:demopms/bookings"

    def test_a_line_renders_as_field_equals_value(self):
        line = EvidenceLine("folio.balance_due", Value.known(Money.parse("812.5", "ILS")))
        assert str(line) == "folio.balance_due = 812.5 ILS"


class TestVerdictRendering:
    def test_a_verdict_renders_as_a_sentence_a_person_can_act_on(self):
        verdict = Verdict(
            Outcome.FAIL, "folio.balance_due is 812.5 ILS, which does not satisfy `lte 0`",
            evidence=[EvidenceLine("folio.balance_due",
                                   Value.known(Money.parse("812.5", "ILS")))],
            record_id="007003199")
        assert str(verdict).startswith("FAIL 007003199:")
        assert "812.5 ILS" in str(verdict)

    def test_a_verdict_reports_whether_it_concluded_anything(self):
        """Finding F5. Coverage is built on this, one verdict at a time."""
        evidence = [EvidenceLine("x", Value.known("y"))]
        assert Verdict(Outcome.PASS, "r", evidence).is_answer
        assert not Verdict(Outcome.EXCLUDED, "r", evidence).is_answer


class TestRemainingGuards:
    def test_a_unit_contradicting_an_amounts_own_currency_is_refused(self):
        """Two sources of truth for one currency is one too many."""
        with pytest.raises(ValueError):
            Value.known(Money.parse("5", "USD"), unit="ILS")

    def test_money_refuses_a_non_decimal_amount(self):
        with pytest.raises(TypeError):
            Money("5", "USD")

    def test_money_refuses_a_blank_currency_both_ways_in(self):
        with pytest.raises(ValueError):
            Money(Decimal("5"), "  ")
        with pytest.raises(ValueError):
            Money.parse("5", "")

    def test_a_currency_code_is_stripped_so_padding_never_splits_a_currency(self):
        """MiniHotel pads several attributes with spaces. "ILS" and "ILS " comparing unequal
        would refuse a comparison between an amount and itself."""
        assert Money(Decimal("5"), " ILS ").currency == "ILS"
        assert Money.parse(" 5 ", "ILS").amount == Decimal("5")

    def test_subtraction_holds_the_same_currency_rule_as_addition(self):
        assert Money.parse("10", "ILS").minus(Money.parse("4", "ILS")) == Money.parse("6", "ILS")
        with pytest.raises(CurrencyMismatch):
            Money.parse("10", "ILS").minus(Money.parse("4", "USD"))

    def test_an_amount_never_compares_against_a_boolean(self):
        """`bool` is a subclass of `int`, so `Money > True` would otherwise quietly mean
        `Money > 1` - a unit-free comparison wearing a disguise."""
        with pytest.raises(CurrencyMismatch):
            Money.parse("5", "ILS").compare(True)

    def test_the_remaining_ordering_operators_hold_the_currency_rule(self):
        assert Money.parse("5", "ILS") <= Money.parse("5", "ILS")
        assert Money.parse("5", "ILS") >= Money.parse("5", "ILS")
        with pytest.raises(CurrencyMismatch):
            _ = Money.parse("5", "ILS") <= Money.parse("5", "USD")
        with pytest.raises(CurrencyMismatch):
            _ = Money.parse("5", "ILS") >= Money.parse("5", "USD")

    def test_a_clock_refuses_a_naive_instant(self):
        """A naive datetime is ambiguous by definition, and treating it as UTC is a guess
        that moves the date - which moves the population."""
        naive = datetime(2026, 7, 8, 14, 30)
        with pytest.raises(ValueError):
            FixedClock(naive)
        with pytest.raises(ValueError):
            PropertyClock("Asia/Jerusalem", instant=naive).now()


class TestBareNumberUnits:
    """The path control 4 runs through.

    "Guests assigned to a room may not exceed the configured occupancy capacity" compares
    `reservation.guest_count.adults` against `room.max_guests.adults` - two bare integers,
    both counting people. The guard has to let those through and stop anything else, and it
    is a different code path from the Money guard because neither side is an amount.
    """

    def test_two_counts_compare_normally(self):
        assert Value.known(2, unit="count").equals(Value.known(2, unit="count")) is True
        assert Value.known(3, unit="count").equals(Value.known(2, unit="count")) is False

    def test_a_count_refuses_to_compare_against_a_differently_united_number(self):
        """Three guests is not three nights. Without the unit the two are the same integer,
        and a control comparing them would look entirely reasonable."""
        with pytest.raises(CurrencyMismatch):
            Value.known(3, unit="count").equals(Value.known(3, unit="nights"))

    def test_a_count_compares_against_a_bare_zero(self):
        """Zero is unit-free everywhere, which is what lets `exists`-shaped assertions work
        without every IR predicate having to declare a unit."""
        assert Value.known(0, unit="count").equals(0) is True
        assert Value.known(3, unit="count").equals(0) is False

    def test_a_count_refuses_a_bare_non_zero_literal(self):
        """`guest_count lte 4` in an IR is missing the half that makes 4 a fact. Refused
        here so the evaluator reports UNKNOWN rather than answering a different question."""
        with pytest.raises(CurrencyMismatch):
            Value.known(3, unit="count").equals(4)


class TestMoneyPredicates:
    def test_is_zero_names_the_settled_folio(self):
        """The condition control 6a passes on: reservation 007004351 departed at 0 ILS."""
        assert Money.parse("0", "ILS").is_zero
        assert not Money.parse("-490.75", "ILS").is_zero

    def test_greater_than_holds_the_currency_rule(self):
        assert Money.parse("812.5", "ILS") > Money.parse("0", "ILS")
        with pytest.raises(CurrencyMismatch):
            _ = Money.parse("812.5", "ILS") > Money.parse("0", "USD")
