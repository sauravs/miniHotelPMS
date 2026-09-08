# -*- coding: utf-8 -*-
"""
MONEY - an amount, and the currency it is denominated in. Never one without the other.

R9 IS WHY THIS TYPE EXISTS
--------------------------
Reservation 007003199 reports a total of `870 USD`. Its OWN folio, in the same property, on
the same reservation, reports a balance of `3262.5 ILS`. MiniHotel publishes no exchange rate
anywhere in its API. A bare float would let those two amounts meet in an expression and
produce a confident, wrong answer that a finance team would then act on.

So: two amounts in different currencies REFUSE to compare. Not compare-and-warn. Refuse.

The single exception is comparison against a bare zero, because zero is the same amount in
every currency. That is exactly why control 6 asserts `folio.balance_due lte 0` rather than
comparing the balance to the reservation total - it sidesteps R9 by construction rather than
by remembering not to.

DECIMAL, NOT FLOAT
------------------
v1 used `float` (finding F10). Control 19 - financial posting integrity - reconciles Debit,
Credit and TotalDebit against per-transaction amounts, and summing money in binary floating
point is how an audit engine produces a 0.01 discrepancy it cannot explain to anybody. The
raw string goes straight to `Decimal`; no float is ever constructed anywhere in the path,
which the constructor enforces rather than a comment requesting.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Union

from .errors import CurrencyMismatch, MoneyParseError

# What may sit on the right-hand side of a comparison: another amount, or a bare zero.
Comparable = Union["Money", int, Decimal]


@dataclass(frozen=True, slots=True)
class Money:
    """An amount of a named currency. Immutable, hashable, and refuses bad arithmetic."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        # float is refused at the door rather than converted. Converting would hide exactly
        # the precision loss this type exists to prevent, and `Money(0.1 + 0.2, "ILS")`
        # would then be silently wrong instead of loudly impossible.
        if isinstance(self.amount, float):
            raise TypeError(
                "money must be Decimal, not float - parse from the raw string with "
                "Money.parse() so no precision is lost (F10)")
        if not isinstance(self.amount, Decimal):
            raise TypeError("money amount must be a Decimal, got %r" % type(self.amount).__name__)
        if not (self.currency or "").strip():
            raise ValueError("an amount without a currency is not evidence (R9)")
        object.__setattr__(self, "currency", self.currency.strip())

    # ------------------------------------------------------------------ construction
    @classmethod
    def parse(cls, raw: str, currency: str) -> Money:
        """Build an amount from the raw string exactly as the provider wrote it.

        The provider's own text is the input on purpose: any intermediate float, however
        briefly it exists, is a rounding decision nobody asked for.
        """
        if not (currency or "").strip():
            raise ValueError("an amount without a currency is not evidence (R9): %r" % (raw,))
        try:
            return cls(Decimal(str(raw).strip()), currency)
        except (InvalidOperation, ArithmeticError, ValueError):
            raise MoneyParseError("%r is not an amount - refusing to guess" % (raw,)) from None

    # ------------------------------------------------------------------ properties
    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        """A checked-out folio CAN be negative: reservation 007004348 departed at
        -490.75 ILS because the guest overpaid and the hotel owes a refund. That is a real
        captured record, and the reason control 6 is two controls in v2 (decision D8)."""
        return self.amount < 0

    # ------------------------------------------------------------------ comparison
    def compare(self, other: Comparable) -> int:
        """-1, 0 or 1 - or raise, because there is no honest answer (R9)."""
        return _sign(self.amount - self.comparable_with(other))

    def plus(self, other: Money) -> Money:
        """Addition, in the same currency only. Summing across currencies without a rate is
        the arithmetic form of the same mistake as comparing across them."""
        return Money(self.amount + self.comparable_with(other), self.currency)

    def minus(self, other: Money) -> Money:
        return Money(self.amount - self.comparable_with(other), self.currency)

    def comparable_with(self, other: Comparable) -> Decimal:
        """The other side as a bare Decimal IN THIS CURRENCY, or a refusal (R9).

        Public because `Value` delegates to it: the currency rule is defined once, here, and
        every layer that compares amounts asks this type rather than re-deriving it. The
        return is a plain Decimal so the caller can then use ordinary Python operators - by
        that point the only question that could have been wrong has already been settled.
        """
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(
                    "refusing to compare %s against %s - no exchange rate exists in this "
                    "provider, and inventing one would be worse than answering nothing (R9)"
                    % (self, other))
            return other.amount
        # A bare number out of an IR predicate. Zero is the one amount that means the same
        # thing in every currency; anything else is missing the half that makes it a fact.
        if isinstance(other, bool):
            raise CurrencyMismatch("cannot compare %s against a boolean" % self)
        if isinstance(other, (int, Decimal)) and other == 0:
            return Decimal(0)
        raise CurrencyMismatch(
            "refusing to compare %s against the bare number %r - an amount is only comparable "
            "to another amount in the same currency, or to zero (R9)" % (self, other))

    # Ordering raises on a mismatch for the same reason `compare` does. Python's own Decimal
    # raises for incompatible operands too, so this is the idiomatic shape.
    def __lt__(self, other: Comparable) -> bool:
        return self.compare(other) < 0

    def __le__(self, other: Comparable) -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: Comparable) -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: Comparable) -> bool:
        return self.compare(other) >= 0

    # ------------------------------------------------------------------ identity
    def __eq__(self, other: object) -> bool:
        """Structural equality, which NEVER raises.

        Deliberately not the same question as `.compare()`. This one asks "is this the same
        piece of evidence?" and is used by tests, sets and dict keys - all of which break if
        equality can raise. `.compare()` asks "do these two amounts agree?" and is the one
        that enforces R9. Different currencies are simply not equal here; they are not an
        error, because `Money(5,'USD') == Money(5,'ILS')` has an obvious correct answer.
        """
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount and self.currency == other.currency

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __str__(self) -> str:
        """This string ends up in an audit trail next to an accusation, so it is the plain
        form a person would write: `-490.75 ILS`."""
        return "%s %s" % (self.amount, self.currency)

    __repr__ = __str__


def _sign(delta: Decimal) -> int:
    return (delta > 0) - (delta < 0)
