# -*- coding: utf-8 -*-
"""
INTERVALS - does a date fall inside a window?

Control 1d asks whether an arrival falls inside a room's out-of-service window, and control 2
asks the same question from the room's side. v1 declared `within` in its schema, used it in two
controls, and implemented none of it - so every record came back UNKNOWN (review finding F2).

Dates are compared as ISO strings, which is safe because every date reaching this layer has
already been PARSED and reformatted by the provider adapter. A string comparison on `yyyy-MM-dd`
is a date comparison; on `dd/MM/yyyy` it is nonsense, which is exactly why the adapter refuses
to pass a date through unparsed (R2).

TWO RULES THAT DECIDE VERDICTS
------------------------------
BOUNDARIES ARE INCLUSIVE. A room closed *from* the 1st is closed ON the 1st. Excluding the
boundary would let an arrival on the first day of an out-of-service window pass.

A MISSING END IS AN OPEN WINDOW, NOT AN ABSENT ONE. A room closed from a date with no end is
closed indefinitely. Reading the missing end as "no window" would silently pass every future
arrival - and all 28 sandbox rooms return these fields empty, so this is the path that runs
first on real data (open question 2.4).
"""
from __future__ import annotations

from ..kernel import Value

# `absent_means: false` on the closed-date fields means an unset window arrives as known(False)
# rather than as an unknown. That is the registry's decision and this layer honours it.
_UNSET = (False, None, "")


def within(value: Value, start: Value, end: Value) -> bool | None:
    """True, False, or None when any of the three cannot be established."""
    if not value.is_known:
        return None
    if not start.is_known or not end.is_known:
        # A window whose bound we could not READ is not a window we know to be absent.
        return None

    lower = None if start.payload in _UNSET else str(start.payload)
    upper = None if end.payload in _UNSET else str(end.payload)

    if lower is None and upper is None:
        # No window at all - a definite answer, not a gap. Most rooms are in this state.
        return False

    moment = str(value.payload)
    if lower is not None and moment < lower:
        return False
    if upper is not None and moment > upper:
        return False
    return True


def overlaps(one_start: str, one_end: str, two_start: str, two_end: str) -> bool:
    """Whether two closed date ranges share any day.

    Half-open at the end: a stay departing on the 11th and one arriving on the 11th do not
    overlap, because the room is vacated and re-let the same day. That is how a hotel counts
    nights, and counting it the other way would report a violation on every back-to-back
    booking in the property.
    """
    return one_start < two_end and two_start < one_end
