# -*- coding: utf-8 -*-
"""
TRANSFORMS - every MiniHotel quirk, one named function each.

`spec/providers/minihotel.json` names a transform per field; this module is the registry those
names resolve to. Each takes the RAW string exactly as it appeared in the response and returns
a `Value` - never a bare Python object, so a transform can answer "I cannot tell" without
inventing an exception vocabulary on the way up.

    transform(raw, unit=None) -> Value

`unit` is supplied by the resolver, which is the only layer that knows a field's canonical type:
a currency code for money, "count" for a tally, None for everything else.

EVERY RULE BELOW WAS FOUND BY CALLING THE API, NOT BY READING ITS DOCUMENTATION. Documentation
review got 4 of 12 risks wrong on this project. Where a rule rests on a specific record, the
record is named, because that is the difference between a convention and a finding.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from ...kernel import Money, Value


# --------------------------------------------------------------------------- dates
# R2 - MiniHotel mixes THREE date formats inside one API:
#
#     GetReservationKey      arrival="28/08/2024"      dd/MM/yyyy
#     GetReservationBalance  <Date>20240828</Date>     yyyyMMdd
#     RoomStatusInquiry      from="2024-08-14"         yyyy-MM-dd
#
# The formats are deliberately NOT mutually forgiving. A parser that shrugs and tries the other
# format when the first fails will one day read 01/02/2024 as the 2nd of January - and a
# misread date does not raise. It compares as a perfectly valid date and passes the control,
# which is the quietest way this system could be wrong.

def _parse(raw: str, fmt: str, label: str) -> Value:
    text = (raw or "").strip()
    if not text:
        return Value.unknown("empty value where a %s date was expected" % label, risk="R2")
    try:
        return Value.known(datetime.strptime(text, fmt).strftime("%Y-%m-%d"), unit="date")
    except ValueError:
        return Value.unknown("%r is not a %s date - refusing to guess" % (text, label),
                             risk="R2")


def date_ddmmyyyy_to_iso(raw: str, unit: str | None = None) -> Value:
    """dd/MM/yyyy -> yyyy-MM-dd.

    Also the format of `createDateTime`, which is DATE ONLY (R3): there is no time component
    at all, so same-day precision is impossible. The returned unit is "date", so no caller can
    come to believe it has an hour to work with - control 12 ("reservations created after the
    scheduled arrival time") has to say that rather than imply it.
    """
    return _parse(raw, "%d/%m/%Y", "dd/MM/yyyy")


def date_yyyymmdd_to_iso(raw: str, unit: str | None = None) -> Value:
    """yyyyMMdd -> yyyy-MM-dd."""
    return _parse(raw, "%Y%m%d", "yyyyMMdd")


def date_iso_to_iso(raw: str, unit: str | None = None) -> Value:
    """yyyy-MM-dd -> yyyy-MM-dd. Still PARSED, not passed through: 2024-13-01 is not a date."""
    return _parse(raw, "%Y-%m-%d", "yyyy-MM-dd")


# --------------------------------------------------------------------------- numbers
def to_int(raw: str, unit: str | None = "count") -> Value:
    try:
        return Value.known(int(str(raw).strip()), unit=unit or "count")
    except ValueError:
        return Value.unknown("%r is not an integer" % (raw,))


def to_money(raw: str, unit: str | None = None) -> Value:
    """An amount, which is only evidence once it carries the currency it is denominated in (R9).

    The currency arrives as `unit` from the resolver, which found it elsewhere in the response -
    reservation 007003199 reports 870 USD while its own folio reports 3262.5 ILS, so it is not
    a constant and cannot be assumed.
    """
    if not unit:
        return Value.unknown(
            "amount %r has no currency, so it is not comparable to anything (R9)" % (raw,),
            risk="R9")
    try:
        return Value.known(Money.parse(raw, unit))
    except (InvalidOperation, ArithmeticError, ValueError):
        return Value.unknown("%r is not an amount" % (raw,))


def zero_is_unknown(raw: str, unit: str | None = None) -> Value:
    """R10 / R12 - `0` in MiniHotel usually means "nobody configured this", not zero.

    23 of 28 sandbox rooms report adult capacity 0, and per-room prices come back 0 on bookings
    that were demonstrably paid for. Reading those as real zeroes converts a configuration gap
    into a wall of FAILs - which is the "never widen a verdict" rule, inverted.
    """
    try:
        number = Decimal(str(raw).strip())
    except (InvalidOperation, ArithmeticError, ValueError):
        return Value.unknown("%r is not a number" % (raw,))
    if number == 0:
        return Value.unknown(
            "0 means unconfigured in this provider, not zero (R10/R12)", risk="R12")
    if unit == "count":
        # Capacities are counts, not measurements; keep them integral.
        return Value.known(int(number), unit="count")
    if not unit:
        return Value.unknown(
            "amount %r has no currency, so it is not comparable to anything (R9)" % (raw,),
            risk="R9")
    return Value.known(Money(number, unit))


# --------------------------------------------------------------------------- flags
def to_bool(raw: str, unit: str | None = None) -> Value:
    text = (raw or "").strip().lower()
    if text in ("true", "1"):
        return Value.known(True)
    if text in ("false", "0"):
        return Value.known(False)
    return Value.unknown("%r is neither true nor false" % (raw,))


def yesno_to_bool(raw: str, unit: str | None = None) -> Value:
    text = (raw or "").strip().upper()
    if text in ("YES", "Y"):
        return Value.known(True)
    if text in ("NO", "N"):
        return Value.known(False)
    return Value.unknown("%r is neither YES nor NO" % (raw,))


def masked_to_presence_bool(raw: str, unit: str | None = None) -> Value:
    """The card number arrives masked ("****"). Presence is the only fact available - never
    validity, never the number itself. Returning either would be manufacturing evidence."""
    return Value.known(bool((raw or "").strip()))


# --------------------------------------------------------------------------- code maps
def casefold(raw: str, unit: str | None = None) -> Value:
    """R13 - room type codes differ in case between endpoints: Bulk ARI says EXECUTIVE, the
    room-type master says Executive, and they are the same type. Comparing them raw reports a
    data defect that does not exist."""
    return Value.known((raw or "").casefold(), unit=unit)


def cd_to_clean_dirty(raw: str, unit: str | None = None) -> Value:
    return {"C": Value.known("clean"), "D": Value.known("dirty")}.get(
        (raw or "").strip().upper(),
        Value.unknown("%r is not a housekeeping status this provider defines" % (raw,)))


def one_two_to_charge_payment(raw: str, unit: str | None = None) -> Value:
    return {"1": Value.known("charge"), "2": Value.known("payment")}.get(
        (raw or "").strip(),
        Value.unknown("%r is not a debit/credit marker this provider defines" % (raw,)))


# --------------------------------------------------------------------------- tenant maps (A5)
# Status codes and folio departments are customisable PER PROPERTY, so the maps arrive from
# `spec/tenants/*.json` rather than living here. A control speaks canonical statuses
# ("checked_out"); only this layer is allowed to know that a hotel writes "OUT".
#
# ANYTHING NOT IN THE MAP IS UNKNOWN, NEVER A GUESS. Silently mapping a code nobody told us
# about would include or exclude reservations from a control's scope invisibly - and 44 of the
# 217 distinct reservations we have ever seen carry exactly such a code.

def _map_code(raw: str, mapping: dict[str, str] | None, what: str, consequence: str) -> Value:
    code = (raw or "").strip()
    known = (mapping or {}).get(code)
    if known is not None:
        return Value.known(known)
    return Value.unknown(
        "%r is not in this property's %s map, and %s (A5)" % (code, what, consequence),
        risk="A5")


def tenant_status_map(raw: str, unit: str | None = None,
                      mapping: dict[str, str] | None = None) -> Value:
    return _map_code(raw, mapping, "status",
                     "a status we cannot name must not decide whether a control applies")


def tenant_department_map(raw: str, unit: str | None = None,
                          mapping: dict[str, str] | None = None) -> Value:
    return _map_code(raw, mapping, "department",
                     "posting categories are configured per property")


def identity(raw: str, unit: str | None = None) -> Value:
    """No transformation declared in the provider map - the raw string is the value."""
    return Value.known(raw, unit=unit)


# The name in `spec/providers/minihotel.json` -> the function. A mapping naming a transform
# that is not here is a SPEC ERROR and the resolver raises rather than passing the raw string
# through: an unapplied transform is a wrong value that looks right.
TRANSFORMS = {
    None: identity,
    "casefold": casefold,
    "cd_to_clean_dirty": cd_to_clean_dirty,
    "date_ddmmyyyy_to_iso": date_ddmmyyyy_to_iso,
    "date_iso_to_iso": date_iso_to_iso,
    "date_yyyymmdd_to_iso": date_yyyymmdd_to_iso,
    "identity": identity,
    "masked_to_presence_bool": masked_to_presence_bool,
    "one_two_to_charge_payment": one_two_to_charge_payment,
    "tenant_department_map": tenant_department_map,
    "tenant_status_map": tenant_status_map,
    "to_bool": to_bool,
    "to_int": to_int,
    "to_money": to_money,
    "yesno_to_bool": yesno_to_bool,
    "zero_is_unknown": zero_is_unknown,
}
