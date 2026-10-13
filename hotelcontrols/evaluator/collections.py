# -*- coding: utf-8 -*-
"""
A COLLECTION, JUDGED RECORD BY RECORD - issue #109 (#87's option 2).

    judge_collection(ir, bundle, settings) -> Judgement

A `collection` reference joins MANY records to this one: a room's occupancy segments. Control 2
asks a question about all of them - "a room with an active closed window must not have an
arriving reservation" - and the only reading of that with no ambiguity is mode `none`: NO
related record may satisfy ANY predicate. The validator refuses every other placement (check
8), and `predicates._from_a_collection` still refuses one that was never validated.

THE ANSWER, IN KLEENE ORDER (P1)
--------------------------------
    any record satisfies a predicate            -> FAIL, naming that record
    else any record could not be judged         -> UNKNOWN, naming it
    else the collection is complete (P3)        -> PASS
    else                                        -> UNKNOWN, naming the dates nobody looked at

WHY A PASS NEEDS MORE THAN "NOTHING MATCHED" (P3)
-------------------------------------------------
No request asks for all of time (R8). A room's segments arrive for the window its reference
was fetched for, and "no segment overlaps the closure" is a statement about that window only.
So a PASS needs the question's dates, from the day the collection was asked onward, to lie
inside the fetched window. The question's dates are read from the rule itself - the record's
own date fields its predicates place a collection's dates against - so nothing here knows what
a room, a closure or a segment is. An overlap SEEN inside the window is a FAIL whatever lies
beyond it; an open-ended closure can therefore FAIL and never PASS.

That rests on one fact about the providers, pinned by the contract suite on the refresh
capture: a windowed occupancy response holds every segment TOUCHING the window, including one
begun before it and one beginning on its last day.

AN EMPTY COLLECTION IS NOT "NO GUESTS"
--------------------------------------
`bundle.related[entity]` is empty both when the room has no segments and when nobody could look
- the reference refused, the room's key unreadable. Which one it is lives in
`bundle.joins[entity]`, read FIRST: known(False) is a definite absence, unknown is a gap. And a
segment whose OWN key could not be read (`bundle.unplaced`) may be this room's guest, so it is
judged too: if it would satisfy a predicate here, the room cannot be shown clear.

Pure, like the rest of the evaluator: no clock, no I/O. The day the collection was asked on
arrives with its window, from the evidence layer that held the clock.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from ..evidence import Bundle
from ..kernel import NOT_APPLICABLE, Outcome, Value
from .predicates import DATE_UNITS, PredicateResult, describe, evaluate_predicate

_UNSET = (False, None, "")


@dataclass(frozen=True, slots=True)
class Judgement:
    outcome: Outcome
    reason: str
    fields: tuple[str, ...]                     # the fields that decided it
    seen: tuple[str, ...]                       # every field read, in order
    evidence: dict[str, Value]                  # the values its evidence table shows
    collections: frozenset[str]                 # the entities judged record by record


def collections_read(predicates, bundle: Bundle) -> frozenset[str]:
    """The collection entities these predicates read."""
    return frozenset(entity for predicate in predicates for entity in _entities(predicate)
                     if entity in bundle.related)


def judge_collection(ir, bundle: Bundle, settings: dict[str, Any] | None = None) -> Judgement:
    """Mode `none` over every record of each collection the assertion reads."""
    predicates = ir["assertion"]["predicates"]
    entities = collections_read(predicates, bundle)
    remote = {r["entity"]: r.get("remote_field") for r in ir.get("references", ())}

    seen: list[str] = []
    results: list[tuple[PredicateResult, dict[str, Value] | None]] = []

    def note(result):
        for name in result.fields:
            if name not in seen:
                seen.append(name)

    for predicate in predicates:
        read = sorted(set(_entities(predicate)) & entities)
        if not read:
            result = evaluate_predicate(predicate, bundle, settings)
            note(result)
            results.append((result, None))
            continue
        if len(read) > 1:
            results.append((PredicateResult(
                None, "%s reads two collections (%s), and which records pair with which is "
                      "not something this rule says" % (predicate["field"], ", ".join(read)),
                tuple(_operands(predicate))), None))
            continue
        results.extend(_each_record(predicate, read[0], bundle, settings, remote, note))

    for result, record in results:
        if result.holds is True:
            return _judged(Outcome.FAIL, result, record, bundle, seen, entities)
    for result, record in results:
        if result.holds is None:
            return _judged(Outcome.UNKNOWN, result, record, bundle, seen, entities)

    # Nothing satisfied, nothing unjudged: a PASS, if every collection is complete for this.
    reasons = []
    for entity in sorted(entities):
        covered, reason = _coverage(predicates, entity, bundle)
        if not covered:
            return _judged(Outcome.UNKNOWN, PredicateResult(None, reason, ()), None, bundle,
                           seen, entities)
        reasons.append(reason)
    return _judged(Outcome.PASS, PredicateResult(True, "; ".join(reasons), ()), None, bundle,
                   seen, entities)


# --------------------------------------------------------------------------- per record
def _each_record(predicate, entity, bundle, settings, remote, note):
    """One result per related record - and per unplaced one - for one predicate."""
    join = bundle.joins.get(entity)
    if join is None or not join.is_known:
        # Read BEFORE `related`: an empty tuple there is also what "could not look" leaves.
        why = join.reason if join is not None else "no join was recorded for it"
        yield PredicateResult(
            None, "this %s's %s records are not established: %s" % (bundle.entity, entity, why),
            tuple(_operands(predicate))), None
        return

    records = bundle.related.get(entity, ())
    for number, record in enumerate(records, 1):
        result = evaluate_predicate(predicate, _view(bundle, entity, record), settings)
        note(result)
        label = "%s record %d of %d (%s)" % (entity, number, len(records),
                                             _described(record, remote.get(entity)))
        yield replace(result, reason="%s: %s" % (label, result.reason)), record

    key = remote.get(entity)
    for record in bundle.unplaced.get(entity, ()):
        result = evaluate_predicate(predicate, _view(bundle, entity, record), settings)
        if result.holds is False:
            continue                            # cannot be this record's problem either way
        unread = record.get(key)
        label = ("a %s record whose %s is not established (%s), so it may be this %s's (%s)"
                 % (entity, key, unread.reason if unread is not None and not unread.is_known
                    else "unreadable", bundle.entity, _described(record, key)))
        # Never True: nobody knows it is this record's. It may be - so this cannot be clear.
        yield PredicateResult(None, "%s: %s" % (label, result.reason), result.fields), record


def _view(bundle: Bundle, entity: str, record: dict[str, Value]) -> Bundle:
    """This record, seen with ONE related record's fields in place of the collection's."""
    return Bundle(bundle.entity, bundle.record_id, {**bundle.fields, **record},
                  {k: v for k, v in bundle.related.items() if k != entity}, bundle.joins,
                  bundle.windows, bundle.unplaced)


def _described(record: dict[str, Value], key: str | None) -> str:
    return ", ".join("%s %s" % (name, describe(value)) for name, value in record.items()
                     if name != key)


def _judged(outcome, result, record, bundle, seen, entities) -> Judgement:
    if record is not None:
        evidence = {**bundle.fields, **record}
    else:
        # No one record decided it, so none is shown as if it had: a PASS is about all of them,
        # and the reason says how many and over which dates.
        evidence = {name: value for name, value in bundle.fields.items()
                    if name.split(".")[0] not in entities}
    return Judgement(outcome, result.reason, tuple(result.fields), tuple(seen), evidence,
                     frozenset(entities))


# --------------------------------------------------------------------------- completeness
def _coverage(predicates, entity, bundle) -> tuple[bool, str]:
    """Whether the collection was fetched for every date this question asks about (P3)."""
    count = len(bundle.related.get(entity, ()))
    window = bundle.windows.get(entity)
    if window is None:
        return False, ("none of this %s's %d %s records satisfies any condition, but they were "
                       "fetched for no window of dates, so they cannot be shown to be all of "
                       "them" % (bundle.entity, count, entity))

    starts, ends = [], []
    for predicate in predicates:
        if entity not in _entities(predicate):
            continue
        span = _span(predicate, entity, bundle)
        if isinstance(span, str):
            return False, span
        starts.append(span[0])
        ends.append(span[1])

    start = None if None in starts else min(starts)
    end = None if None in ends else max(ends)
    low = max(start, window.asked_on) if start else window.asked_on
    seen = ("none of this %s's %d %s records satisfies any condition, and they were fetched "
            "for %s" % (bundle.entity, count, entity, window))
    if end is not None and end < low:
        return False, ("%s; this question's dates end on %s, before %s, the day they were "
                       "asked from, so nothing fetched speaks to them" % (seen, end, low))

    missing = []
    if low < window.start:
        missing.append("%s..%s" % (low, _day(window.start, -1)))
    if end is None:
        missing.append("everything from %s on, because the question has no end date"
                       % max(_day(window.end, 1), low))
    elif end > window.end:
        missing.append("%s..%s" % (max(_day(window.end, 1), low), end))
    if missing:
        return False, ("%s only, so %s %s not looked at"
                       % (seen, " and ".join(missing), "was" if len(missing) == 1 else "were"))
    return True, "%s, which covers %s..%s" % (seen, low, end)


def _span(predicate, entity, bundle) -> tuple[str | None, str | None] | str:
    """The dates of THIS record a predicate places the collection's dates against.

    Two shapes, both `within`: a collection's date inside this record's window (the span is
    the window), or this record's date inside a related record's span (the span is that day).
    Anything else is not bounded by dates, and no fetched window can be complete for it.
    """
    interval = predicate.get("interval") or {}

    def inside(name):
        return name.split(".")[0] == entity

    unbounded = ("%s over %s records is not a question bounded by this %s's dates, so no "
                 "window they were fetched for can be shown complete for it"
                 % (predicate["field"], entity, bundle.entity))
    if predicate["operator"] != "within" or not interval:
        return unbounded
    bounds = (interval["start"], interval["end"])
    if inside(predicate["field"]) and not any(inside(b) for b in bounds):
        start, end = (_date(bundle.fields.get(b)) for b in bounds)
        if start is False or end is False:
            return unbounded
        return start, end
    if not inside(predicate["field"]) and all(inside(b) for b in bounds):
        day = _date(bundle.fields.get(predicate["field"]))
        return unbounded if day in (False, None) else (day, day)
    return unbounded


def _date(value: Value | None):
    """An ISO date, None for a declared absence (an open bound), False if it is no date."""
    if value is None or not value.is_known:
        return False
    if value.payload in _UNSET or value.payload is NOT_APPLICABLE:
        return None
    if value.unit not in DATE_UNITS:
        return False
    return str(value.payload)[:10]


def _day(iso: str, offset: int) -> str:
    return (date.fromisoformat(iso[:10]) + timedelta(days=offset)).isoformat()


# --------------------------------------------------------------------------- operands
def _operands(predicate) -> list[str]:
    names = [predicate["field"], predicate.get("compare_to"),
             *(predicate.get("interval") or {}).values()]
    return [name for name in names if name]


def _entities(predicate) -> list[str]:
    return [name.split(".")[0] for name in _operands(predicate)]
