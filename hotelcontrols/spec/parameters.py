# -*- coding: utf-8 -*-
"""
PARAMETERS - what a hotel decides, typed, and the difference between "none" and "not decided".

    ParameterSchema.load(spec_dir)                         spec/parameters.json
    schema.typed(settings, tenant_id=..., currencies=...)  -> every value read into its type

WHY THIS EXISTS (slice 21, G6a narrowed - docs/plan-v3.md §5)
-------------------------------------------------------------
Until slice 21 a tenant setting was whatever JSON its file held, and `[]` meant two different
things: "the hotel decided none" and "nobody has asked the hotel". `TenantConfig.setting`'s own
docstring told you to write an empty value if the hotel had not decided. In a SCOPE that is
harmless - an empty list excludes every record. In an EXCEPTION it exempts nobody, so every
complimentary stay would FAIL: a confident accusation manufactured from a missing answer.

So, three rules:

  1. `null` IS "NOT DECIDED", and it is the only spelling of it. It is accepted for every type,
     and it never becomes a value: `TenantConfig` keeps an undecided parameter declared but
     out of `tenant.settings`, which is the dict the runner hands the evaluator. A predicate
     reading it answers through the evaluator's existing branch - "this property has not
     supplied X, which this control needs" - so UNKNOWN names the parameter and no evaluator
     code changed to make it so.
  2. NO DEFAULTS. A schema entry carrying one is refused. A default is the engine deciding for
     a hotel, which is the anti-criterion "a missing hotel decision is read as none" arriving
     by another door.
  3. EVERY VALUE HAS A DECLARED TYPE, checked at load, refused BY NAME. A tenant setting the
     schema does not declare is refused rather than passed through untyped.

THE TYPES
---------
Five, and the last three exist before anything in `spec/ir/` uses them: slice 22's late-checkout
template (D15 - `free_until`, `charge_from`, `maximum_time`, `approval_required_after` as times,
`fee_per_hour` as Money, `hour_rounding` with no default) declares its parameters in this same
vocabulary from `spec/guest/`, and may not change this package. The types are proven here; the
parameters are that slice's, approved by the owner with its decision table.

    text_list       ["RACK", "CORP"]                     -> tuple of str
    text_list_map   {"CORP": ["Executive"]}              -> dict of str -> tuple of str
    money           {"amount": "25.00", "currency": "USD"} -> kernel Money
    time_of_day     "14:00"                              -> datetime.time
    choice          one of the parameter's `options`     -> str

"Unit or currency" (plan-v3 §5) is carried by the type. A Money value must be in a currency the
property states it uses - refused otherwise, never converted (R9: there is no exchange rate
anywhere in the API). A time of day is on the property's own clock (F11), so a time written with
an offset or a zone names a second clock and is refused rather than converted.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..kernel import Money
from .errors import SpecError
from .registry import SPEC_DIR

# Each type, and how it is written - the second half of every refusal, so the person editing a
# tenant file is told what to write rather than only that they were wrong.
TYPES = {
    "text_list": 'a list of text, e.g. ["RACK"]',
    "text_list_map": 'an object mapping text to a list of text, e.g. {"CORP": ["Executive"]}',
    "money": 'an amount with its currency, e.g. {"amount": "25.00", "currency": "USD"}',
    "time_of_day": 'a time on the property\'s own clock, written HH:MM (24-hour), e.g. "14:00"',
    "choice": "one of the parameter's options",
}

# What a schema entry may say. Anything else is refused, so a misspelt `requried` cannot leave a
# parameter silently optional - and `default` has a refusal of its own, because it is the one
# key somebody will reach for on purpose.
_KEYS = frozenset({"type", "required", "options", "description", "note"})

_TIME = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
# Something that READ as a time and then named a clock: an offset, a Z, a zone abbreviation.
_ANOTHER_CLOCK = re.compile(r"\d{1,2}:\d{2}(:\d{2})?\s*(Z|[+-]\d{1,2}(:?\d{2})?|[A-Za-z][\w/+-]*)")


@dataclass(frozen=True, slots=True)
class Parameter:
    """One thing a hotel decides: its name, its type, and whether a tenant must state it."""

    name: str
    type: str
    required: bool
    options: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True, slots=True)
class ParameterSchema:
    """Every parameter a tenant file may state, by name."""

    parameters: dict[str, Parameter] = field(default_factory=dict)

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, spec_dir: pathlib.Path | str = SPEC_DIR) -> ParameterSchema:
        path = pathlib.Path(spec_dir) / "parameters.json"
        if not path.is_file():
            # Refused rather than treated as an empty schema. With no schema there is nothing
            # to type a tenant's values against, and passing them through untyped is exactly
            # the state slice 21 removes.
            raise SpecError("no parameter schema at %s - a tenant's settings cannot be typed "
                            "without one" % path)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ParameterSchema:
        declared = raw.get("parameters") if isinstance(raw, dict) else None
        if not isinstance(declared, dict):
            raise SpecError("a parameter schema is an object with a `parameters` object")
        problems: list[str] = []
        parameters: dict[str, Parameter] = {}
        for name, definition in declared.items():
            parameter = _parameter(name, definition, problems)
            if parameter is not None:
                parameters[name] = parameter
        if problems:
            raise SpecError("; ".join(problems))
        return cls(parameters)

    # ------------------------------------------------------------------ typing a tenant
    def typed(self, settings: dict[str, Any], *, tenant_id: str,
              currencies: tuple[str, ...] | list[str]) -> dict[str, Any]:
        """Every stated value read into its type, `None` kept as `None` (not decided).

        Raises SpecError listing EVERY problem, each naming its parameter: a tenant file with
        two mistakes is fixed in one edit rather than discovered one failed load at a time.
        """
        if not isinstance(settings, dict):
            raise SpecError("tenant %r: settings must be an object, not a %s"
                            % (tenant_id, type(settings).__name__))
        problems: list[str] = []
        typed: dict[str, Any] = {}
        for name, value in settings.items():
            parameter = self.parameters.get(name)
            if parameter is None:
                problems.append(
                    "tenant %r states %r, which spec/parameters.json does not declare. A value "
                    "with no declared type cannot be checked, so it is refused rather than "
                    "passed through" % (tenant_id, name))
                continue
            if value is None:
                typed[name] = None                        # not decided - rule 1 above
                continue
            reading, problem = _READERS[parameter.type](parameter, value, tenant_id,
                                                        tuple(currencies))
            if problem is not None:
                problems.append(problem)
            else:
                typed[name] = reading
        for name, parameter in sorted(self.parameters.items()):
            if parameter.required and name not in settings:
                # Not inferred from the absence: a required parameter is STATED, as null if
                # the hotel has not decided, so "nobody wrote this down" is visible in the file.
                problems.append(
                    "tenant %r does not state %r. Write null if the hotel has not decided it: "
                    "an absent setting and an undecided one must not look alike"
                    % (tenant_id, name))
        if problems:
            raise SpecError("; ".join(problems))
        return typed


# --------------------------------------------------------------------------- the schema
def _parameter(name: str, definition: Any, problems: list[str]) -> Parameter | None:
    if not isinstance(definition, dict):
        problems.append("parameter %r must be an object" % name)
        return None
    found = len(problems)
    if "default" in definition:
        problems.append(
            "parameter %r declares a default. A parameter has none: a hotel decision nobody "
            "made must never be filled in by the engine - write null in the tenant file "
            "instead, which means not decided" % name)
    unknown = sorted(set(definition) - _KEYS - {"default"})
    if unknown:
        problems.append("parameter %r says %s, which a parameter schema does not know"
                        % (name, ", ".join(unknown)))
    kind = definition.get("type")
    if kind not in TYPES:
        problems.append("parameter %r has type %r, which is not one of: %s"
                        % (name, kind, ", ".join(sorted(TYPES))))
    if not isinstance(definition.get("required"), bool):
        problems.append(
            "parameter %r must state `required` as true or false - whether a tenant file has to "
            "state it (null if undecided) is part of the schema, not a default" % name)
    options = definition.get("options")
    if kind == "choice":
        if (not isinstance(options, list) or not options
                or not all(isinstance(o, str) and o.strip() for o in options)):
            problems.append("parameter %r is a choice and must list its options as text"
                            % name)
    elif options is not None:
        problems.append("parameter %r lists options, but only a choice has options" % name)
    if len(problems) > found:
        return None
    return Parameter(name, kind, definition["required"], tuple(options or ()),
                     definition.get("description", ""))


# --------------------------------------------------------------------------- the readers
# Each returns (value, None) or (None, the refusal naming the parameter).
def _text_list(parameter, value, tenant_id, _currencies):
    name = parameter.name
    if not isinstance(value, list):
        # The "RACK" hazard (#45): `"RACK" in tuple("RACK")` is False, so a one-code hotel
        # writing "RACK" for ["RACK"] excluded every record. Refused here, at load, where the
        # reason can name the setting, and not only when some control happens to read it.
        hint = (' Write ["%s"] even for one entry - a bare string would be tested character '
                "by character" % value) if isinstance(value, str) else ""
        return None, ("%r must be %s, and tenant %r supplies a %s (%r).%s"
                      % (name, TYPES["text_list"], tenant_id, type(value).__name__, value, hint))
    for item in value:
        if not isinstance(item, str):
            return None, ("%r must be %s, and holds %r, which is a %s"
                          % (name, TYPES["text_list"], item, type(item).__name__))
        if not item.strip():
            # A blank code matches nothing any PMS sends, so it would quietly do nothing.
            return None, "%r holds a blank entry, which can match nothing" % name
    return tuple(value), None


def _text_list_map(parameter, value, tenant_id, currencies):
    name = parameter.name
    if not isinstance(value, dict):
        return None, ("%r must be %s, and tenant %r supplies a %s"
                      % (name, TYPES["text_list_map"], tenant_id, type(value).__name__))
    mapped = {}
    for key, entries in value.items():
        if not key.strip():
            return None, "%r maps a blank key, which can match nothing" % name
        reading, problem = _text_list(parameter, entries, tenant_id, currencies)
        if problem is not None:
            return None, ("%r maps %r to %r, which is not a list of text"
                          % (name, key, entries))
        mapped[key] = reading
    return mapped, None


def _money(parameter, value, tenant_id, currencies):
    name = parameter.name
    if not isinstance(value, dict):
        # R9. A number with no currency cannot be compared with anything this engine holds:
        # the property's reservations and its folios are in different currencies.
        return None, ("%r is money, and tenant %r supplies a bare %r. Money is %s - a number "
                      "without its currency cannot be compared with anything (R9)"
                      % (name, tenant_id, value, TYPES["money"]))
    if set(value) != {"amount", "currency"}:
        return None, ("%r must have exactly an amount and a currency, and has: %s"
                      % (name, ", ".join(sorted(map(str, value))) or "nothing"))
    amount, currency = value["amount"], value["currency"]
    if not isinstance(amount, str):
        # Money is Decimal. A JSON number arrives as a binary float, so the amount is written
        # as text and read exactly as written.
        return None, ('%r has its amount as a JSON %s (%r). Write it as a string - "%s" - so '
                      "it is read exactly as written" % (name, type(amount).__name__, amount,
                                                         amount))
    if not isinstance(currency, str) or not currency.strip():
        return None, "%r has no currency, and an amount without one is not money (R9)" % name
    if not currencies:
        return None, ("%r is money, and tenant %r states no currencies, so whether it uses %s "
                      "cannot be checked. State `currencies` in the tenant file"
                      % (name, tenant_id, currency))
    if currency not in currencies:
        # Refused, never converted: there is no exchange rate anywhere in the API (R9).
        return None, ("%r is in %s, a currency tenant %r does not use (it uses %s)"
                      % (name, currency, tenant_id, ", ".join(currencies)))
    try:
        return Money.parse(amount, currency), None
    except (ValueError, ArithmeticError) as exc:
        return None, "%r has an amount that is not an amount: %s" % (name, exc)


def _time_of_day(parameter, value, tenant_id, _currencies):
    name = parameter.name
    if isinstance(value, str):
        matched = _TIME.fullmatch(value)
        if matched:
            return datetime.time(int(matched.group(1)), int(matched.group(2))), None
        another = _ANOTHER_CLOCK.fullmatch(value.strip())
        if another and another.group(2).upper() not in ("AM", "PM"):
            # F11. A hotel's times are on its own clock. An offset names a second clock, and
            # converting it would be the engine guessing which day the hotel meant.
            return None, ("%r is written %r, which names another clock. A hotel's times are on "
                          "its own clock (F11), so a time is written HH:MM with no offset or "
                          "zone" % (name, value))
    return None, ("%r must be %s, and tenant %r supplies %r"
                  % (name, TYPES["time_of_day"], tenant_id, value))


def _choice(parameter, value, tenant_id, _currencies):
    if value in parameter.options:
        return value, None
    return None, ("%r is %r, which is not one of its options: %s"
                  % (parameter.name, value, ", ".join(parameter.options)))


_READERS = {
    "text_list": _text_list,
    "text_list_map": _text_list_map,
    "money": _money,
    "time_of_day": _time_of_day,
    "choice": _choice,
}
