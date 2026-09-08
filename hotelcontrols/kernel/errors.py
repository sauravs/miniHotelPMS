# -*- coding: utf-8 -*-
"""
The kernel's failure vocabulary.

Every one of these is raised rather than swallowed, and that is the design. A layer that
returns a plausible-looking default when it cannot answer is a layer that manufactures
confidence, and manufacturing confidence is the one thing this product exists not to do.

Callers above the kernel catch these deliberately and turn them into UNKNOWN *with the
reason attached* - which is why each carries a message written to be read by a hotel, not
by a developer.
"""


class KernelError(Exception):
    """Base for everything the kernel refuses to do."""


class UnknownValue(KernelError):
    """An unknown Value was compared.

    Raised rather than answering False, because `PASS if v.equals(0) else FAIL` is the
    obvious line a caller writes, and for a balance that was never established that line
    reports a violation. Forcing the caller to catch this is what keeps UNKNOWN alive all
    the way to the screen.
    """


class CurrencyMismatch(KernelError, ValueError):
    """Two amounts in different currencies were compared (R9).

    Found live: reservation 007003199 reports 870 USD while its own folio reports
    3262.5 ILS, and MiniHotel publishes no exchange rate anywhere in its API. There is no
    correct answer to give, so none is given.
    """


class UnitRequired(KernelError, ValueError):
    """A bare number was offered as evidence (R9).

    A capacity of 3 and a balance of 3 are different facts. Until a number says what it
    counts it is not evidence, and the constructor will not build it.
    """


class MoneyParseError(KernelError, ValueError):
    """A string that was supposed to be an amount is not one.

    Refused rather than coerced: a provider that starts returning "N/A" in an amount field
    must produce an UNKNOWN, never a zero.
    """


class NotAuditable(KernelError, ValueError):
    """A verdict was constructed without a reason or without evidence.

    Audit is the product. A FAIL with no evidence is an accusation without a receipt, and an
    UNKNOWN with no reason cannot tell a hotel what to fix - so neither is allowed to exist.
    """
