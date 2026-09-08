# -*- coding: utf-8 -*-
"""
POPULATION EVALUATION - questions about a GROUP of records.

Some controls cannot be answered one record at a time. "Two active reservations must not share
the same OTA confirmation number" is not a property of a reservation; it is a property of a set
of them. Neither is "a room's occupancy must be consistent with the reservations assigned to
it". v1 declared `count_lte` and `overlaps` in its schema, used them in two controls, and
implemented neither - so duplicate detection returned zero answers while the fixtures contained
a confirmed real instance of the pattern (review finding F2).

Still a pure function. The group is assembled from bundles the caller already gathered; nothing
here fetches anything.

THE SHAPE
---------
    1. scope and exceptions, per record, exactly as at record level. A record that is EXCLUDED
       or UNKNOWN never reaches the group - and that ordering is the whole safety of the thing.
    2. the survivors are grouped by the IR's `group_by` field.
    3. the aggregate predicate judges each GROUP, and every record in it receives a verdict
       carrying the group's evidence.

TWO GUARDS DECIDE WHETHER THIS IS USEFUL OR LIBELLOUS, AND BOTH TRACE TO R7
--------------------------------------------------------------------------
An OTA modification in this provider is a CANCEL PLUS A RECREATE reusing the same portal id,
and 7 of 11 sandbox bookings are direct with no portal id at all. So:

  * cancelled records leave in step 1, or every modified booking is a duplicate of itself;
  * records with no key are excluded by the control's own exception clause, or every direct
    booking becomes a duplicate of every other direct booking - one enormous false group.

AN UNREADABLE NEIGHBOUR MAKES A GROUP UNCERTAIN, NOT CLEAN
----------------------------------------------------------
If a record sharing your key had a status this property cannot name (A5 - one reservation in
five), then "you are the only one" is a claim the evidence does not support. Those records
resolve to UNKNOWN rather than PASS. Reporting a confident PASS built on a record we could not
read is the same failure as reporting a confident FAIL.
"""
from __future__ import annotations

from typing import Any

from ..evidence import Bundle
from ..kernel import EvidenceLine, Outcome, Value, Verdict
from .intervals import overlaps
from .predicates import evaluate_predicate
from .record import evaluate_record


def evaluate_population(ir, bundles, settings: dict[str, Any] | None = None) -> list[Verdict]:
    """Every record's verdict. The single entry point a runner calls.

    A non-aggregate control is handed straight to the record evaluator, so a caller never has
    to know which shape a control is.
    """
    bundles = list(bundles)
    if ir["assertion"]["mode"] != "aggregate":
        return [evaluate_record(ir, bundle, settings) for bundle in bundles]

    # Positions are carried explicitly rather than looked up later: bundles are frozen
    # dataclasses, so two records with identical evidence compare EQUAL, and `list.index()`
    # would hand both of them the same slot - losing one verdict entirely.
    group_by = ir["assertion"]["group_by"]
    verdicts: dict[int, Verdict] = {}
    in_play: list[tuple[int, Bundle]] = []

    # ---- step 1: scope and exceptions, per record ---------------------------------------
    # A record settled here NEVER reaches the group, and that ordering is the whole safety of
    # the thing: cancelled records leave before counting (R7), and so do direct bookings with
    # no key, via the control's own exception clause.
    uncertain_keys: set[str] = set()
    for index, bundle in enumerate(bundles):
        settled = _scope_and_exceptions(ir, bundle, settings)
        if settled is None:
            in_play.append((index, bundle))
            continue
        verdicts[index] = settled
        if settled.outcome is Outcome.UNKNOWN:
            # We could not establish whether this record belongs. If it shares a key with a
            # group, that group's membership is uncertain - see below. EXCLUDED records are
            # NOT recorded here: those are definitely out, which is exactly what R7 needs.
            key = bundle.fields.get(group_by)
            if key is not None and key.is_known:
                uncertain_keys.add(str(key.payload))

    # ---- step 2: group the survivors ----------------------------------------------------
    groups: dict[str, list[tuple[int, Bundle]]] = {}
    for index, bundle in in_play:
        key = bundle.fields.get(group_by)
        if key is None or not key.is_known:
            reason = (key.reason if key is not None
                      else "%s is not among this record's evidence" % group_by)
            verdicts[index] = _verdict(
                ir, bundle, Outcome.UNKNOWN,
                "this record cannot be grouped: %s" % reason, [group_by], ())
            continue
        groups.setdefault(str(key.payload), []).append((index, bundle))

    # ---- step 3: judge each group -------------------------------------------------------
    predicate = ir["assertion"]["predicates"][0]
    for key, members in groups.items():
        bundles_in_group = [bundle for _index, bundle in members]
        judged = dict(_judge(predicate, key, bundles_in_group, group_by))
        for index, bundle in members:
            outcome, reason, fields = judged[id(bundle)]
            if outcome is Outcome.PASS and key in uncertain_keys:
                # "You are the only one" is a claim the evidence does not support while a
                # record we could not read holds the same key. Reporting a confident PASS
                # built on a record we could not read is the same failure as a confident FAIL.
                outcome = Outcome.UNKNOWN
                reason = ("%s; but whether another record shares %s %s could not be "
                          "established, so uniqueness is not proven" % (reason, group_by, key))
            verdicts[index] = _verdict(
                ir, bundle, outcome, reason, fields,
                tuple(other.record_id for _i, other in members if other is not bundle))

    return [verdicts[index] for index in range(len(bundles))]


# --------------------------------------------------------------------------- step 1
def _scope_and_exceptions(ir, bundle, settings):
    """A verdict if the record never reaches the group, or None if it does.

    Reuses the record evaluator's semantics by asking it about a rule with no assertion of its
    own - so scope and exceptions cannot drift between the two shapes of control.
    """
    for clause, excluded_reason, unknown_reason in (
            ("scope", "this control does not apply here: %s",
             "whether this control applies could not be established: %s"),
            ("exceptions", "an exception applies: %s",
             "whether an exception applies could not be established: %s")):
        for predicate in ir.get(clause, []):
            result = evaluate_predicate(predicate, bundle, settings)
            holds_excludes = (result.holds is False) if clause == "scope" \
                else (result.holds is True)
            if holds_excludes:
                return _verdict(ir, bundle, Outcome.EXCLUDED, excluded_reason % result.reason,
                                result.fields, ())
            if result.holds is None:
                return _verdict(ir, bundle, Outcome.UNKNOWN, unknown_reason % result.reason,
                                result.fields, ())
    return None


# --------------------------------------------------------------------------- step 3
def _judge(predicate, key, members, group_by):
    """One group, judged. Yields (id(bundle), (outcome, reason, fields)) per member.

    Keyed by identity rather than by value: two records with identical evidence are still two
    records, and a dict keyed on the bundle itself would silently merge them.
    """
    operator = predicate["operator"]
    if operator == "count_lte":
        rows = _count_lte(predicate, key, members, group_by)
    elif operator == "no_overlap":
        rows = _no_overlap(predicate, key, members, group_by)
    else:
        rows = [(bundle, Outcome.UNKNOWN,
                 "this engine cannot evaluate the aggregate operator %r" % operator,
                 [group_by]) for bundle in members]
    return [(id(bundle), (outcome, reason, fields)) for bundle, outcome, reason, fields in rows]


def _count_lte(predicate, key, members, group_by):
    """At most N DISTINCT values of `field` may share this key.

    Distinct, not rows: a reservation can appear more than once in a population - several room
    stays, or a provider repeating it - and counting rows would report every multi-room booking
    as a duplicate of itself.
    """
    name, limit = predicate["field"], predicate["value"]
    identifiers = {str(b.fields[name].payload) for b in members
                   if name in b.fields and b.fields[name].is_known}
    fields = [group_by, name]

    if len(identifiers) <= limit:
        return [(b, Outcome.PASS,
                 "%s is the only %s with %s %s" % (b.record_id, b.entity, group_by, key)
                 if len(identifiers) == 1 else
                 "%d records share %s %s, which is within the limit of %d"
                 % (len(identifiers), group_by, key, limit), fields) for b in members]

    return [(b, Outcome.FAIL,
             "%d records share %s %s, which exceeds the limit of %d: %s"
             % (len(identifiers), group_by, key, limit, ", ".join(sorted(identifiers))),
             fields) for b in members]


def _no_overlap(predicate, key, members, group_by):
    """No two DISTINCT records in this group may hold overlapping intervals.

    Distinct matters here too: reservation 007003204 holds two segments on room 303 in the
    capture, and a reservation cannot double-book itself.
    """
    name = predicate["field"]
    start_field, end_field = predicate["interval"]["start"], predicate["interval"]["end"]
    fields = [group_by, name, start_field, end_field]

    readable, unreadable = [], []
    for bundle in members:
        start, end = bundle.fields.get(start_field), bundle.fields.get(end_field)
        identity = bundle.fields.get(name)
        if (start is None or not start.is_known or end is None or not end.is_known
                or identity is None or not identity.is_known):
            unreadable.append(bundle)
        else:
            readable.append((bundle, str(identity.payload), str(start.payload),
                             str(end.payload)))

    conflicts: dict[int, set[str]] = {}
    for i, (one, one_id, one_from, one_to) in enumerate(readable):
        for two, two_id, two_from, two_to in readable[i + 1:]:
            if one_id == two_id:
                continue
            if overlaps(one_from, one_to, two_from, two_to):
                conflicts.setdefault(id(one), set()).add(two_id)
                conflicts.setdefault(id(two), set()).add(one_id)

    results = []
    for bundle in unreadable:
        results.append((bundle, Outcome.UNKNOWN,
                        "this occupancy segment could not be read, so whether it conflicts "
                        "with anything cannot be established", fields))
    for bundle, identity, _from, _to in readable:
        clashing = conflicts.get(id(bundle))
        if clashing:
            results.append((bundle, Outcome.FAIL,
                            "%s overlaps %s on %s %s"
                            % (identity, ", ".join(sorted(clashing)), group_by, key), fields))
        elif unreadable:
            # A neighbour we could not read might be the conflict. Claiming a clean room on
            # that basis would be a confident answer built on evidence we do not have.
            results.append((bundle, Outcome.UNKNOWN,
                            "%s conflicts with nothing we could read, but %d segment(s) on %s "
                            "%s could not be read" % (identity, len(unreadable), group_by, key),
                            fields))
        else:
            results.append((bundle, Outcome.PASS,
                            "%s holds %s %s alone for %s..%s"
                            % (identity, group_by, key, _from, _to), fields))
    return results


# --------------------------------------------------------------------------- evidence
def _verdict(ir, bundle, outcome, reason, fields, others):
    """Build a verdict whose evidence names the rest of its group.

    An accusation that does not say who else is involved cannot be acted on: a front-office
    manager has to be able to open both reservations.
    """
    order = []
    declared = [entry["field"] for entry in ir.get("required_evidence", [])]
    for name in list(fields) + declared:
        if name not in order and name in bundle.fields:
            order.append(name)
    if not order:
        order = list(bundle.fields)

    lines = [EvidenceLine(name, bundle.fields[name]) for name in order]
    if others:
        lines.append(EvidenceLine(
            "other records in this group", Value.known(tuple(sorted(str(o) for o in others))),
            source="this run's population"))
    return Verdict(outcome, reason, lines, control_id=ir.get("control_id"),
                   record_id=bundle.record_id)
