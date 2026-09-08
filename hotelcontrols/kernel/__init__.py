# -*- coding: utf-8 -*-
"""
KERNEL - the vocabulary every other layer speaks.

Depends on nothing but the standard library, and nothing here knows that a PMS, a control or
an HTTP request exists. Everything above imports its nouns from this one place, so that
"a number without a unit" is impossible everywhere rather than prevented in most places.

    Value    known(payload, unit) | unknown(reason, risk)   - evidence, or a reasoned gap
    Money    Decimal + currency                             - never one without the other (R9)
    Outcome  PASS | FAIL | UNKNOWN | EXCLUDED               - four, and EXCLUDED is not PASS
    Verdict  outcome + reason + evidence                    - cannot exist without its working
    Clock    today() / now(), in the PROPERTY's timezone    - injected, never global (F11)

The five guarantees this layer enforces structurally, so no caller has to remember them:

  1. A number cannot exist without its unit; an amount cannot exist without its currency (R9).
  2. No float ever represents money (F10).
  3. Two amounts in different currencies refuse to compare - they raise (R9).
  4. An unknown refuses to compare at all, rather than answering False.
  5. A verdict cannot be constructed without a reason and at least one piece of evidence.
"""
from .clock import Clock, FixedClock, PropertyClock
from .errors import (CurrencyMismatch, KernelError, MoneyParseError, NotAuditable, UnitRequired,
                     UnknownValue)
from .money import Money
from .outcome import Outcome
from .value import NOT_APPLICABLE, Value
from .verdict import EvidenceLine, Verdict

__all__ = [
    "NOT_APPLICABLE",
    "Clock",
    "CurrencyMismatch",
    "EvidenceLine",
    "FixedClock",
    "KernelError",
    "Money",
    "MoneyParseError",
    "NotAuditable",
    "Outcome",
    "PropertyClock",
    "UnitRequired",
    "UnknownValue",
    "Value",
    "Verdict",
]
