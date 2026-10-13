# -*- coding: utf-8 -*-
"""
RELATIVE DATES - `today`, `today-1d`, `today+7d`, and nothing else.

A rule names days relative to the PROPERTY'S today, never the machine's (F11): a population
window, a reference's window (issue #109, P2) and a predicate's value (P4) all say `today+7d`
and mean the same thing. Three layers read the token - the validator refuses a malformed one,
the evidence layer resolves windows, the runner resolves values - so its grammar lives here,
once, rather than as three regular expressions that could disagree.

This module reads no clock. It is handed the property's date by whoever holds the clock, which
is what keeps `kernel/clock.py` the only module that can ask what time it is.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

RELATIVE_DATE = re.compile(r"^today(?:([+-])(\d+)d)?$")


def is_relative_date(value: Any) -> bool:
    """Whether `value` is a well-formed relative date token."""
    return isinstance(value, str) and RELATIVE_DATE.match(value) is not None


def offset_days(token: str) -> int:
    """How many days from today a token names. Raises ValueError for anything else.

    An unrecognised token RAISES rather than passing through: sent on to a provider's parser,
    or compared as text, it would make an answer silently wrong rather than obviously refused.
    """
    match = RELATIVE_DATE.match(token) if isinstance(token, str) else None
    if match is None:
        raise ValueError("%r is not a relative date - write today, today+Nd or today-Nd"
                         % (token,))
    sign, days = match.groups()
    return int(days or 0) * (-1 if sign == "-" else 1)


def resolve_relative_date(token: str, today: date) -> str:
    """The ISO date a token names, counted from the property's `today`."""
    return (today + timedelta(days=offset_days(token))).isoformat()
