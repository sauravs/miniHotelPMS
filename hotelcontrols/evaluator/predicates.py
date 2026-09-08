# -*- coding: utf-8 -*-
"""
PREDICATES - one IR clause, applied to one record's evidence.

Every predicate returns one of THREE answers: it holds, it does not, or we cannot tell.

    PredicateResult.holds = True | False | None

The third is not an error. It is what a control says when the evidence is missing, unmapped,
or - in the case that shapes this whole project - denominated in a currency that cannot be
compared to the other side (R9). The kernel already refuses those comparisons by raising; this
module catches the refusal and records it as "cannot tell" WITH THE REASON, rather than letting
it become a crash or, far worse, a `False` that reads as a violation.

That last clause is the entire point. A `False` here becomes a FAIL on a screen in front of a
finance team, so every path that cannot establish an answer has to return None instead - and
each one has a test asserting it does.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..evidence import Bundle
from ..kernel import NOT_APPLICABLE, CurrencyMismatch, UnknownValue, Value
from .intervals import within as _within

# Operators that ask a question about a GROUP of records. Reaching one here means the IR is
# being evaluated the wrong way round; saying so beats answering about a single record.
AGGREGATE_OPERATORS = frozenset({"count_lte", "no_overlap"})


@dataclass(frozen=True, slots=True)
class PredicateResult:
    holds: bool | None
    reason: str
    fields: tuple[str, ...]

    def __repr__(self) -> str:
        return "PredicateResult(%r, %s)" % (self.holds, self.reason)


def describe(value: Value) -> str:
    """A value as it should read next to a verdict."""
    if not value.is_known:
        return "unknown (%s)" % value.reason
    if value.payload is NOT_APPLICABLE:
        return "not applicable"
    if isinstance(value.payload, tuple):
        return "one of %d values" % len(value.payload)
    return str(value)


def evaluate_predicate(predicate: dict[str, Any], bundle: Bundle,
                       settings: dict[str, Any] | None = None) -> PredicateResult:
    """Apply one IR predicate to one record's evidence."""
    name = predicate["field"]
    operator = predicate["operator"]
    fields = [name]

    if operator in AGGREGATE_OPERATORS:
        return PredicateResult(
            None, "%r asks a question about a group of records and cannot be answered about "
                  "one" % operator, tuple(fields))

    left = bundle.fields.get(name)
    if left is None:
        return PredicateResult(
            None, "%s is not among this record's evidence" % name, tuple(fields))

    if operator in ("reference_exists", "reference_missing"):
        return _reference(operator, name, bundle, fields)

    if operator in ("within", "not_within"):
        return _interval(predicate, operator, name, left, bundle, fields)

    right, right_text, problem = _right_hand_side(predicate, bundle, settings, fields)
    if problem is not None:
        return PredicateResult(None, problem, tuple(fields))

    handler = OPERATORS.get(operator)
    if handler is None:
        return PredicateResult(
            None, "this engine cannot evaluate the operator %r, which %s needs"
                  % (operator, name), tuple(fields))

    try:
        holds = handler(left, right)
    except UnknownValue:
        return PredicateResult(None, "%s is %s" % (name, describe(left)), tuple(fields))
    except CurrencyMismatch as exc:
        # R9 arriving as a product answer rather than a crash. The engine will not compare a
        # folio in ILS to a reservation in USD, and it says why on the screen.
        return PredicateResult(
            None, "%s cannot be compared to %s: %s" % (name, right_text, exc), tuple(fields))
    except UnsupportedPredicate as exc:
        return PredicateResult(None, "%s: %s" % (name, exc), tuple(fields))

    # Phrased so it reads as an explanation next to the verdict, for every operator:
    #   "folio.balance_due is 812.5 ILS, which does not satisfy `lte 0`"
    return PredicateResult(
        holds, "%s is %s, which %s `%s %s`"
               % (name, describe(left), "satisfies" if holds else "does not satisfy",
                  operator.replace("_", " "), right_text), tuple(fields))


class UnsupportedPredicate(Exception):
    """The IR is valid; this engine cannot evaluate it yet. Says so rather than guessing."""


# --------------------------------------------------------------------------- right-hand sides
def _right_hand_side(predicate, bundle, settings, fields):
    """The value on the right, its rendering, and a reason if it cannot be established."""
    if "compare_to" in predicate:
        other = predicate["compare_to"]
        fields.append(other)
        value = bundle.fields.get(other)
        if value is None:
            return None, None, "%s is not among this record's evidence" % other
        return value, "%s (%s)" % (describe(value), other), None

    if "tenant_setting" in predicate:
        name = predicate["tenant_setting"]
        if settings is None or name not in settings:
            # The validator catches this before a run, so reaching it means a rule is being
            # evaluated against a tenant that never declared the setting.
            return None, None, ("this property has not supplied %r, which this control needs"
                                % name)
        return settings[name], "the property's %s" % name.replace("_", " "), None

    return predicate.get("value"), repr(predicate.get("value")), None


# --------------------------------------------------------------------------- special operators
def _reference(operator, name, bundle, fields):
    """Did this record's join actually match?

    Three answers, and keeping them apart is the point: a room the master does not hold is a
    definite violation (control 1a), while a master we could not read is an evidence gap. v1
    could express neither.
    """
    entity = name.split(".")[0]
    matched = bundle.joins.get(entity)
    if matched is None:
        return PredicateResult(
            None, "%s declares no join for %s, so whether it resolves cannot be established"
                  % (name, entity), tuple(fields))
    if not matched.is_known:
        return PredicateResult(None, "the %s reference is unavailable: %s"
                               % (entity, matched.reason), tuple(fields))
    holds = matched.payload if operator == "reference_exists" else not matched.payload
    return PredicateResult(
        holds, "%s %s in this property's %s records"
               % (name, "resolves" if matched.payload else "does not resolve", entity),
        tuple(fields))


def _interval(predicate, operator, name, left, bundle, fields):
    interval = predicate["interval"]
    fields.extend((interval["start"], interval["end"]))
    start = bundle.fields.get(interval["start"])
    end = bundle.fields.get(interval["end"])
    if start is None or end is None:
        return PredicateResult(
            None, "the window bounding this test is not among this record's evidence",
            tuple(fields))

    inside = _within(left, start, end)
    if inside is None:
        return PredicateResult(
            None, "%s is %s and the window is %s..%s, so this cannot be established"
                  % (name, describe(left), describe(start), describe(end)), tuple(fields))

    holds = inside if operator == "within" else not inside
    return PredicateResult(
        holds, "%s is %s, which is %s the window %s..%s"
               % (name, describe(left), "inside" if inside else "outside",
                  describe(start), describe(end)), tuple(fields))


# --------------------------------------------------------------------------- operators
def _exists(left, right=None):
    if not left.is_known:
        raise UnknownValue(left.reason)
    # `0` exists; `False` and "not applicable" do not. Written with `is` because in Python
    # 0 == False, and a settled folio balance of zero must not read as an absent field.
    if left.payload is False or left.payload is NOT_APPLICABLE:
        return False
    if isinstance(left.payload, str) and not left.payload.strip():
        return False
    return True


def _ordering(compare):
    def operator(left, right):
        this, other = left.comparable_pair(right)
        return compare(this, other)
    return operator


def _membership(left, right):
    if isinstance(right, Value):
        if not right.is_known:
            # NOT False. An unfetched set would otherwise report every room's type as
            # undefined - a wall of violations about a property whose data is fine.
            raise UnknownValue(right.reason)
        right = right.payload
    if not left.is_known:
        raise UnknownValue(left.reason)
    if right is None:
        raise UnsupportedPredicate("the collection to test membership against is not available")
    return left.payload in tuple(right)


def _matches_ignore_case(left, right):
    this, other = left.comparable_pair(right)
    return str(this).casefold() == str(other).casefold()


OPERATORS = {
    "equals": lambda left, right: left.equals(right),
    "not_equals": lambda left, right: not left.equals(right),
    "exists": _exists,
    "not_exists": lambda left, right=None: not _exists(left),
    "in": _membership,
    "not_in": lambda left, right: not _membership(left, right),
    "lt": _ordering(lambda a, b: a < b),
    "lte": _ordering(lambda a, b: a <= b),
    "gt": _ordering(lambda a, b: a > b),
    "gte": _ordering(lambda a, b: a >= b),
    "matches_ignore_case": _matches_ignore_case,
}
