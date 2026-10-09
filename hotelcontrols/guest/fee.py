# -*- coding: utf-8 -*-
"""
FEE - how much a late checkout costs, as Money, with no multiplication anywhere.

    charged_hours(charge_from, requested, rounding) -> int
    fee_for(fee_per_hour, hours)                   -> Money | None

D15 makes the fee Money: an amount with its currency, from `fee_per_hour`, which slice 21 already
refuses as a bare number or in a currency the property does not use (R9). `Money` has no
multiplication, and the kernel is a must-not for this slice - nor does it need one. A fee is the
hourly rate added to itself once per charged hour, which is exactly what "25.00 USD per started
hour" says, and which cannot round, overflow a float or change the currency on the way.

ROUNDING IS THE HOTEL'S, NEVER OURS. `hour_rounding` has no default (D15): `started_hour` charges
every hour begun after `charge_from` (14:01 is one hour), `completed_hour` only hours fully
elapsed (14:59 is none). An unknown rounding raises rather than falling back to either, because
choosing one is deciding a price for the hotel.
"""
from __future__ import annotations

from datetime import time

from ..kernel import Money

ROUNDINGS = ("started_hour", "completed_hour")


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def charged_hours(charge_from: time, requested: time, rounding: str) -> int:
    """Whole hours from `charge_from` to `requested`, rounded as the hotel states. Never
    negative: a time at or before `charge_from` is no charged hours."""
    if rounding not in ROUNDINGS:
        raise ValueError("hour_rounding %r is not one of %s; no rounding is assumed for a hotel "
                         "(D15)" % (rounding, ", ".join(ROUNDINGS)))
    minutes = _minutes(requested) - _minutes(charge_from)
    if minutes <= 0:
        return 0
    if rounding == "started_hour":
        return -(-minutes // 60)                         # ceiling, in integers
    return minutes // 60


def fee_for(fee_per_hour: Money, hours: int) -> Money | None:
    """`fee_per_hour`, `hours` times, by repeated `Money.plus` - or None for no hours.

    None rather than a zero amount: "a fee of 0.00" is not a fee, and a decision that names one
    would read as a charge somebody should post.
    """
    if hours <= 0:
        return None
    fee = fee_per_hour
    for _ in range(hours - 1):
        fee = fee.plus(fee_per_hour)
    return fee
