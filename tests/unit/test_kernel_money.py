# -*- coding: utf-8 -*-
"""
Money - an amount is not evidence until it carries the currency it is denominated in.

Protects R9, the finding that shapes this whole codebase: reservation 007003199 reports
870 USD while its OWN folio reports 3262.5 ILS, in the same property, on the same
reservation - and MiniHotel publishes no exchange rate anywhere. A bare float would let
those two meet and produce a confident, wrong answer.

Also protects finding F10 from the v1 review: v1 used `float` for money. Control 19
(financial posting integrity) reconciles Debit, Credit and TotalDebit against per-transaction
amounts, and summing money in binary floating point is how an audit engine produces a 0.01
discrepancy it cannot explain.
"""
from decimal import Decimal

import pytest

from hotelcontrols.kernel import CurrencyMismatch, Money, MoneyParseError


class TestConstruction:
    def test_money_is_decimal_parsed_from_the_raw_string(self):
        """The raw string goes straight to Decimal. No float ever exists in the path (F10)."""
        amount = Money.parse("3262.5", "ILS")
        assert amount.amount == Decimal("3262.5")
        assert isinstance(amount.amount, Decimal)
        assert amount.currency == "ILS"

    def test_a_float_can_never_enter_a_money(self):
        """Blocked at the constructor, not merely discouraged in a comment."""
        with pytest.raises(TypeError):
            Money(3262.5, "ILS")

    def test_parsing_via_float_would_lose_precision_and_we_do_not_do_it(self):
        """The exact reason Decimal is not a style preference.

        float("0.1") + float("0.2") != 0.3. A folio reconciliation built on that reports a
        discrepancy that does not exist, and there is no way to explain it to a hotel.
        """
        total = Money.parse("0.1", "ILS").plus(Money.parse("0.2", "ILS"))
        assert total.amount == Decimal("0.3")
        assert float(Decimal("0.1") + Decimal("0.2")) != 0.1 + 0.2

    def test_an_unparseable_amount_is_refused_rather_than_guessed(self):
        with pytest.raises(MoneyParseError):
            Money.parse("not a number", "ILS")

    def test_an_amount_without_a_currency_cannot_exist(self):
        """R9. There is no such thing as '3262.5' in this system."""
        with pytest.raises(ValueError):
            Money.parse("3262.5", "")

    def test_a_negative_amount_is_legitimate(self):
        """Reservation 007004348 checked out at -490.75 ILS: the guest overpaid and the
        hotel owes a refund. A real captured record, and the reason control 6 is two
        controls in v2 (decision D8)."""
        overpaid = Money.parse("-490.75", "ILS")
        assert overpaid.amount == Decimal("-490.75")
        assert overpaid.is_negative


class TestCurrencyGuard:
    def test_two_amounts_in_different_currencies_refuse_to_compare(self):
        """R9. Not 'compare and warn' - refuse. There is no exchange rate to be had."""
        reservation_total = Money.parse("870", "USD")
        folio_balance = Money.parse("3262.5", "ILS")
        with pytest.raises(CurrencyMismatch):
            folio_balance.compare(reservation_total)

    def test_ordering_across_currencies_also_refuses(self):
        with pytest.raises(CurrencyMismatch):
            _ = Money.parse("870", "USD") < Money.parse("3262.5", "ILS")

    def test_arithmetic_across_currencies_refuses(self):
        with pytest.raises(CurrencyMismatch):
            Money.parse("870", "USD").plus(Money.parse("3262.5", "ILS"))

    def test_the_same_currency_compares_normally(self):
        assert Money.parse("812.5", "ILS").compare(Money.parse("0", "ILS")) == 1
        assert Money.parse("0", "ILS").compare(Money.parse("0", "ILS")) == 0
        assert Money.parse("-490.75", "ILS") < Money.parse("0", "ILS")

    def test_comparison_against_a_bare_zero_is_allowed_in_any_currency(self):
        """Zero is the one amount that means the same thing everywhere.

        This is exactly why control 6 asserts `folio.balance_due lte 0` rather than comparing
        the balance to the reservation total: it sidesteps R9 entirely.
        """
        assert Money.parse("0", "ILS").compare(0) == 0
        assert Money.parse("812.5", "JPY").compare(0) == 1
        assert Money.parse("-490.75", "ILS").compare(0) == -1

    def test_comparison_against_a_bare_non_zero_number_is_refused(self):
        """`balance > 100` is meaningless without saying 100 of what. Only zero is exempt."""
        with pytest.raises(CurrencyMismatch):
            Money.parse("812.5", "ILS").compare(100)


class TestStructuralEquality:
    def test_equality_never_raises_and_includes_the_currency(self):
        """`==` asks 'is this the same piece of evidence?' and is used by tests, sets and
        dict keys, so it must not raise. `.compare()` asks 'do these two amounts agree?'
        and is the one that enforces R9. Keeping them distinct is deliberate."""
        assert Money.parse("5", "USD") == Money.parse("5", "USD")
        assert Money.parse("5", "USD") != Money.parse("5", "ILS")
        assert Money.parse("5", "USD") != "5 USD"

    def test_money_is_hashable_so_it_can_key_a_group(self):
        assert len({Money.parse("5", "USD"), Money.parse("5", "USD")}) == 1

    def test_money_is_immutable(self):
        amount = Money.parse("5", "USD")
        with pytest.raises((AttributeError, TypeError)):
            amount.amount = Decimal("6")

    def test_repr_reads_as_evidence(self):
        """This string ends up in an audit trail next to an accusation."""
        assert repr(Money.parse("-490.75", "ILS")) == "-490.75 ILS"
