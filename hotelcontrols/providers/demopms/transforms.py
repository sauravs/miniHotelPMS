# -*- coding: utf-8 -*-
"""
TRANSFORMS - every DemoPMS quirk, one named function each.

`spec/providers/demopms.json` names a transform per field; this module is the registry those
names resolve to. Each takes the raw JSON value exactly as it arrived and returns a `Value` -
never a bare Python object, so a transform can answer "I cannot tell" without inventing an
exception vocabulary on the way up.

    transform(raw, unit=None) -> Value

DemoPMS IS FICTIONAL, AND ITS QUIRKS WERE CHOSEN TO BE DIFFERENT
----------------------------------------------------------------
A second adapter that happened to share the first one's date format and the first one's way of
saying "nobody configured this" would prove nothing: it would be the same adapter twice, and
the canonical boundary above it would still be untested. So:

    quirk                     the real PMS                 this one
    ------------------------  ---------------------------  -----------------------------------
    dates                     three numeric formats in      one format, carrying a month NAME
                              one API (R2)
    "nobody configured this"  the number 0, overloaded      an out-of-band sentinel, so 0 is a
                              (R10, R12)                    real zero
    money                     amount and currency in        one self-describing object
                              different parts of the
                              response (R9)
    booleans                  "YES"/"NO", "true", "C"/"D"   real JSON booleans, and words
    occupancy                 sibling lists                 nested inside the room

WHAT IS NOT DIFFERENT is the contract: absence means what the registry says it means, money
carries its currency or it is not evidence, and an unmapped code is UNKNOWN rather than a
guess. That contract is asserted once for every provider in `tests/contract/`.

The raw value here is a JSON value rather than a string, which is the one signature difference
from MiniHotel's transforms. It is not incidental: `null`, `true` and `-1` are things this wire
format can say and the other one cannot, and flattening them to text first would throw away
exactly the distinctions the fields depend on.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ...kernel import Money, Value

# --------------------------------------------------------------------------- dates
# DemoPMS writes one date format and one only: `08 Jul 2026`. A month NAME, so it cannot be
# quietly misread as either of MiniHotel's numeric formats - which is the failure R2 describes
# and the reason the two adapters must not share a date parser.
#
# The month table is EXPLICIT rather than `strptime("%d %b %Y")`, and that is deliberate.
# `%b` reads the C library's month names, so the same fixture parses under one locale and
# fails under another - and it fails as an evidence gap, which is invisible. A verdict must not
# depend on the machine that produced it any more than it depends on the machine's clock (F11).
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def date_dmy_to_iso(raw: Any, unit: str | None = None) -> Value:
    """`08 Jul 2026` -> `2026-07-08`, or a refusal.

    The unit is "date", so no caller can come to believe it has an hour to work with. DemoPMS
    supplies no time component on any date field, exactly as MiniHotel does not (R3) - the two
    providers agree here by coincidence rather than by design, and the canonical vocabulary
    would be the same either way.
    """
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return Value.unknown("empty value where a `dd Mon yyyy` date was expected", risk="R2")

    parts = text.split()
    if len(parts) == 3 and parts[1][:3].lower() in _MONTHS and len(parts[1]) == 3:
        day, month, year = parts[0], _MONTHS[parts[1].lower()], parts[2]
        if day.isdigit() and year.isdigit() and len(year) == 4:
            number = int(day)
            # A day this month does not have is a defect in the response, not a date. February
            # is allowed 29 here because a leap check would be the only calendar arithmetic in
            # the module; `29 Feb 2027` reaching a control as a date is a smaller wrong than a
            # second date implementation to keep in step with the first.
            if 1 <= number <= _DAYS_IN_MONTH[month - 1]:
                return Value.known("%s-%02d-%02d" % (year, month, number), unit="date")

    return Value.unknown(
        "%r is not a `dd Mon yyyy` date - refusing to guess, because a misread date does not "
        "raise: it compares as a perfectly good date and passes the control (R2)" % (text,),
        risk="R2")


# --------------------------------------------------------------------------- numbers
def to_int(raw: Any, unit: str | None = "count") -> Value:
    """A tally. `bool` is excluded explicitly - Python says `True == 1` and a flag is not a
    count, so a boolean arriving where a number belongs is a shape change, not a one."""
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        return Value.unknown("%r is not an integer" % (raw,))
    try:
        return Value.known(int(str(raw).strip()), unit=unit or "count")
    except ValueError:
        return Value.unknown("%r is not an integer" % (raw,))


# The value DemoPMS spends to mean "nobody has configured this". It is out of band rather than
# overloaded, which is the deliberate contrast with MiniHotel's 0 (R10/R12): 23 of 28 rooms
# there report adult capacity 0 and every one of them means unconfigured, so that provider
# cannot express a room that genuinely sleeps nobody. This one can.
UNCONFIGURED = -1


def sentinel_is_unknown(raw: Any, unit: str | None = None) -> Value:
    """The unconfigured sentinel -> UNKNOWN; everything else, including 0, is a real number."""
    answer = to_int(raw, unit or "count")
    if answer.is_known and answer.payload == UNCONFIGURED:
        return Value.unknown(
            "this provider writes %d where a value was never configured, so it is a gap in "
            "the property's setup rather than a number (R12)" % UNCONFIGURED, risk="R12")
    return answer


def money_object(raw: Any, unit: str | None = None) -> Value:
    """A self-describing amount: `{"amount": "3262.50", "currency": "ILS"}`.

    R9, from the other side. MiniHotel keeps the currency in a different part of the response
    from the amount it denominates - reservation 007003199 reports 870 USD while its own folio
    reports 3262.5 ILS - so its adapter has to go and find it. Here it travels with the amount,
    and the failure mode is different in kind: not "the currency was somewhere else" but "the
    object arrived without one". Both end in UNKNOWN rather than a bare number.
    """
    if not isinstance(raw, dict):
        return Value.unknown("%r is not an amount - this provider writes money as an object "
                             "carrying its own currency (R9)" % (raw,), risk="R9")

    amount, currency = raw.get("amount"), raw.get("currency")
    if amount is None:
        # The second way this provider says "nobody configured this", for money. It does NOT
        # reuse the -1 sentinel, because -1 is a perfectly good amount and a hotel might owe it.
        return Value.unknown("this amount was never priced, so there is nothing to compare")
    if not isinstance(amount, str):
        # F10. `json.loads` turns 3262.5 into a float, and summing money in binary floating
        # point is how an audit engine produces a 0.01 discrepancy it cannot explain. The wire
        # format carries amounts as strings for that reason; one that does not is not evidence.
        return Value.unknown(
            "amount %r arrived as a JSON number rather than a string, and a JSON number is a "
            "float - money parsed through one has already lost the precision an audit trail "
            "exists to keep (F10)" % (amount,))
    if not (isinstance(currency, str) and currency.strip()):
        return Value.unknown(
            "amount %r has no currency, so it is not comparable to anything (R9)" % (amount,),
            risk="R9")
    try:
        return Value.known(Money.parse(amount, currency))
    except (InvalidOperation, ArithmeticError, ValueError):
        return Value.unknown("%r is not an amount" % (amount,))


# --------------------------------------------------------------------------- flags
def json_bool(raw: Any, unit: str | None = None) -> Value:
    """A real JSON boolean, and nothing else.

    Deliberately stricter than MiniHotel's, which must accept "YES", "true" and "1" because
    that is what its API sends. This one sends booleans, so a string here means the response
    changed shape - and reading it anyway would hide that from everybody.
    """
    if isinstance(raw, bool):
        return Value.known(raw)
    return Value.unknown("%r is not a boolean - this provider writes real JSON booleans, so "
                         "anything else means the response changed shape" % (raw,))


def presence_bool(raw: Any, unit: str | None = None) -> Value:
    """The card arrives as its last four digits. Presence is the only fact available - never
    validity, never the number itself. Returning either would be manufacturing evidence."""
    return Value.known(bool(str(raw).strip()) if raw is not None else False)


# --------------------------------------------------------------------------- code maps
def casefold(raw: Any, unit: str | None = None) -> Value:
    """Codes compare case-insensitively.

    R13's rule, applied by a provider that does not have R13's disease. MiniHotel returns
    EXECUTIVE from one endpoint and Executive from another; this one is consistent. Comparing
    case-insensitively is right either way, and doing it only where an API is known to be
    inconsistent is how the next inconsistency becomes a data defect that does not exist.
    """
    if not isinstance(raw, str):
        return Value.unknown("%r is not a code" % (raw,))
    return Value.known(raw.casefold(), unit=unit)


def clean_soiled(raw: Any, unit: str | None = None) -> Value:
    return {"CLEAN": Value.known("clean"), "SOILED": Value.known("dirty")}.get(
        raw.strip().upper() if isinstance(raw, str) else "",
        Value.unknown("%r is not a housekeeping status this provider defines" % (raw,)))


def charge_payment(raw: Any, unit: str | None = None) -> Value:
    return {"CHARGE": Value.known("charge"), "PAYMENT": Value.known("payment")}.get(
        raw.strip().upper() if isinstance(raw, str) else "",
        Value.unknown("%r is not a posting direction this provider defines" % (raw,)))


# --------------------------------------------------------------------------- tenant maps (A5)
# Deliberately duplicated from the other adapter rather than shared. The RULE - anything not in
# the map is UNKNOWN, never a guess - is a contract every provider owes, and it is asserted for
# every registered provider once, in tests/contract/. The VOCABULARY is per property and lives
# in `spec/tenants/*.json`.
#
# A shared helper here would make one adapter depend on another's module, which is precisely
# the coupling this slice exists to prove does not exist: the third PMS must be a new directory
# and a mapping file, not an edit to somebody else's.

def _map_code(raw: Any, mapping: dict[str, str] | None, what: str, consequence: str) -> Value:
    code = raw.strip() if isinstance(raw, str) else ""
    known = (mapping or {}).get(code)
    if known is not None:
        return Value.known(known)
    return Value.unknown(
        "%r is not in this property's %s map, and %s (A5)" % (code, what, consequence),
        risk="A5")


def tenant_status_map(raw: Any, unit: str | None = None,
                      mapping: dict[str, str] | None = None) -> Value:
    return _map_code(raw, mapping, "status",
                     "a status we cannot name must not decide whether a control applies")


def tenant_department_map(raw: Any, unit: str | None = None,
                          mapping: dict[str, str] | None = None) -> Value:
    return _map_code(raw, mapping, "department",
                     "posting categories are configured per property")


def text(raw: Any, unit: str | None = None) -> Value:
    """No transformation declared - the string is the value.

    A number where text was expected is UNKNOWN rather than stringified. A booking reference
    arriving as `1` and one arriving as `"01"` are not the same key, and a join keyed on the
    wrong spelling matches nothing while looking exactly like it tried.
    """
    if not isinstance(raw, str):
        return Value.unknown(
            "%r arrived where this field is declared as text; stringifying it would produce a "
            "key that silently matches nothing" % (raw,))
    return Value.known(raw, unit=unit)


# The name in `spec/providers/demopms.json` -> the function. A mapping naming a transform that
# is not here is a SPEC ERROR and the resolver raises rather than passing the raw value
# through: an unapplied transform is a wrong value that looks right.
TRANSFORMS = {
    None: text,
    "casefold": casefold,
    "charge_payment": charge_payment,
    "clean_soiled": clean_soiled,
    "date_dmy_to_iso": date_dmy_to_iso,
    "json_bool": json_bool,
    "money_object": money_object,
    "presence_bool": presence_bool,
    "sentinel_is_unknown": sentinel_is_unknown,
    "tenant_department_map": tenant_department_map,
    "tenant_status_map": tenant_status_map,
    "text": text,
    "to_int": to_int,
}

# The transforms that produce a `Money`. A money-typed canonical field mapped to anything else
# is a spec error the adapter refuses on: the registry's type is what the rules were written
# against, and an amount reaching a control without its currency is R9 happening again.
MONEY_TRANSFORMS = frozenset({"money_object"})
