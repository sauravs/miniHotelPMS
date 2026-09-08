# -*- coding: utf-8 -*-
"""
VALUE - the only thing the provider layer hands upwards.

    Value = known(payload, unit) | unknown(reason, risk)

Two states, no third. Everything the engine learns about a hotel arrives wrapped in one of
them, which is what makes UNKNOWN a first-class result rather than an exception somebody
forgot to catch.

FOUR PROPERTIES ARE ENFORCED HERE RATHER THAN LEFT TO CALLERS
------------------------------------------------------------
because "the caller will remember" is how each of these gets broken.

1. A NUMBER CANNOT EXIST WITHOUT ITS UNIT (R9). A capacity of 3 and a balance of 3 are
   different facts, and a reservation reporting 870 USD must never meet its own folio's
   3262.5 ILS in an expression.

2. NO FLOAT, EVER (F10). Amounts are `Money`, which is `Decimal`; counts are `int`. There is
   no canonical field for which binary floating point is the right representation.

3. AN UNKNOWN REFUSES TO COMPARE AT ALL. If `unknown.equals(0)` returned False, a caller
   writing the obvious `PASS if v.equals(0) else FAIL` would report FAIL for a reservation
   whose balance was never established. That single line is the failure mode this entire
   product exists to prevent, so the comparison raises and forces the caller to decide.

4. AN UNKNOWN CANNOT EXIST WITHOUT A REASON. An UNKNOWN whose reason is blank tells a hotel
   nothing about what to fix, and "connect your housekeeping system to enable this control"
   is the product path that depends on it.

NOT_APPLICABLE is a third kind of answer, and it is a KNOWN one: R7 found that 7 of 11
sandbox bookings are direct and carry no portal id at all. "There is no channel confirmation
because there was no channel" is a fact, not a gap - and it must not be an empty string, or
every direct booking looks like a duplicate of every other one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .errors import CurrencyMismatch, UnitRequired, UnknownValue
from .money import Money


class _NotApplicable:
    """Sentinel for a field whose absence is meaningful rather than missing.

    A dedicated singleton rather than `None`, so that `None` never becomes a second failure
    vocabulary - the one callers forget to check.
    """

    __slots__ = ()
    _instance: "_NotApplicable | None" = None

    def __new__(cls) -> "_NotApplicable":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_APPLICABLE"

    def __bool__(self) -> bool:
        return False


NOT_APPLICABLE = _NotApplicable()


def _is_bare_number(payload: Any) -> bool:
    """A measurement that needs a unit. `bool` is a subclass of `int` in Python and a flag is
    not a measurement, so it is excluded explicitly."""
    return isinstance(payload, (int, Decimal)) and not isinstance(payload, bool)


@dataclass(frozen=True, slots=True)
class Value:
    """One canonical field's worth of evidence, or a reasoned admission that we have none."""

    is_known: bool
    payload: Any = None
    unit: str | None = None
    reason: str | None = None
    risk: str | None = None
    # Where this came from, as it should read in an audit trail:
    # "pms:minihotel/GetReservationBalance". This is the ONE thing carrying a provider name
    # that crosses the canonical boundary, and it crosses as data: no PMS FIELD PATH is in
    # it, and no layer above ever parses it. An auditor has to know which system and which
    # call produced a number.
    source: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.is_known:
            self._validate_known()
        else:
            self._validate_unknown()

    def _validate_known(self) -> None:
        payload = self.payload
        if isinstance(payload, float):
            raise TypeError(
                "evidence may not be a float - amounts are Money (Decimal), counts are int "
                "(F10): %r" % (payload,))
        if isinstance(payload, Money):
            # Money already carries its currency; asking the caller to repeat it is an
            # opportunity to disagree with itself.
            if self.unit not in (None, payload.currency):
                raise ValueError("unit %r contradicts the amount's own currency %r"
                                 % (self.unit, payload.currency))
            object.__setattr__(self, "unit", payload.currency)
        elif _is_bare_number(payload) and not (self.unit or "").strip():
            raise UnitRequired(
                "a number without a unit is not evidence (R9): %r. Use Money for an amount, "
                "or pass unit='count' for a tally" % (payload,))

    def _validate_unknown(self) -> None:
        if not (self.reason or "").strip():
            raise ValueError("an unknown without a reason is not auditable")
        if self.payload is not None:
            # A "sort of known" state is how UNKNOWN gets quietly downgraded to a guess.
            raise ValueError("an unknown value cannot also carry a payload: %r" % (self.payload,))

    # ------------------------------------------------------------------ constructors
    @classmethod
    def known(cls, payload: Any, unit: str | None = None, source: str | None = None) -> Value:
        """A fact.

        `unit` is mandatory for bare numbers - "count" for a tally, "date" for a calendar date
        whose granularity matters (R3). An amount should be a `Money`, which carries its own.
        """
        return cls(True, payload=payload, unit=unit, source=source)

    @classmethod
    def unknown(cls, reason: str, risk: str | None = None, source: str | None = None) -> Value:
        """An admission, with the reason that will end up on screen next to the verdict."""
        return cls(False, reason=reason, risk=risk, source=source)

    # ------------------------------------------------------------------ comparison
    def equals(self, other: Any) -> bool:
        """Evidence-level equality: raises rather than guessing. See the module docstring.

        `other` may be another Value or a literal out of an IR predicate ("checked_out", 0).
        """
        left, right = self.comparable_pair(other)
        return bool(left == right)

    def comparable_pair(self, other: Any) -> tuple[Any, Any]:
        """The two raw payloads, ready to compare - or a refusal with the reason.

        The evaluator's ordering predicates use this so that `lt`, `lte`, `gt` and `gte` get
        exactly the same unknown and currency guards that `equals` gets. One gate, not five.
        """
        if not self.is_known:
            raise UnknownValue("cannot compare an unknown value: %s" % self.reason)

        if isinstance(other, Value):
            if not other.is_known:
                raise UnknownValue("cannot compare against an unknown value: %s" % other.reason)
            right, right_unit = other.payload, other.unit
        else:
            # A literal from an IR predicate. It carries no unit - see the zero rule below.
            right, right_unit = other, None

        # Money enforces R9 itself, and it is the only type that knows the zero rule, so the
        # question is delegated rather than re-implemented here.
        #
        # Both sides come back as bare Decimals. That normalisation is the whole job: once
        # the currency question has been settled, the caller compares two plain numbers with
        # ordinary Python operators and cannot get it wrong. Returning the Money objects
        # unchanged would leave `Money(0,'ILS') == 0` to Python's default equality, which
        # answers False - a settled folio would read as "not zero" and control 6 would report
        # a violation on a reservation that owes nothing.
        if isinstance(self.payload, Money):
            return self.payload.amount, self.payload.comparable_with(right)
        if isinstance(right, Money):
            # Only the right-hand side is money. Mirror the same question rather than
            # inventing a second, subtly different rule for the reflected case - and keep the
            # operands in their original order, because `lt` and `gt` depend on it.
            return right.comparable_with(self.payload), right.amount

        if _is_bare_number(self.payload) or _is_bare_number(right):
            if (self.unit or None) != (right_unit or None):
                # Zero means the same thing under any unit; everything else does not.
                if not (right_unit is None and right == 0) and not (
                        self.unit is None and self.payload == 0):
                    raise CurrencyMismatch(
                        "refusing to compare %r %s against %r %s - they are not measured in "
                        "the same thing (R9)"
                        % (self.payload, self.unit or "(no unit)", right,
                           right_unit or "(no unit)"))
        return self.payload, right

    # ------------------------------------------------------------------ plumbing
    def __str__(self) -> str:
        """How a value should read next to a verdict, on screen and in a stored run."""
        if not self.is_known:
            return "unknown (%s)" % self.reason
        if self.payload is NOT_APPLICABLE:
            return "not applicable"
        if isinstance(self.payload, Money):
            return str(self.payload)
        if self.unit and self.unit not in ("date", "datetime"):
            return "%s %s" % (self.payload, self.unit)
        return str(self.payload)

    def __repr__(self) -> str:
        if self.is_known:
            return "known(%s)" % self
        return "unknown(%s%s)" % (self.reason, " [%s]" % self.risk if self.risk else "")
