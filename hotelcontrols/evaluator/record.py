# -*- coding: utf-8 -*-
"""
EVALUATE ONE RECORD - the rule, applied, with its working shown.

    evaluate_record(ir, bundle, settings) -> Verdict

A pure function. No I/O, no clock, no network, no knowledge of any PMS. That purity is what
makes a verdict reproducible six months later, which is the difference between an audit trail
and an anecdote - and it is asserted by a test rather than assumed.

THE ORDER, AND WHY
------------------
    scope       does this control apply to this record?      -> EXCLUDED if not
    exceptions  is this record exempt?                       -> EXCLUDED if so
    assertion   does the rule hold?                          -> PASS / FAIL

At each step the answer may be "cannot tell", and then the whole verdict is UNKNOWN. A control
that cannot establish whether it even applies has not passed, and it has not excluded anything
either - it simply has nothing to say yet, and says so.

THREE-VALUED LOGIC, ON PURPOSE
------------------------------
Combining predicates uses Kleene logic rather than "any unknown wins":

    all   any False -> FAIL      else any unknown -> UNKNOWN   else PASS
    any   any True  -> PASS      else any unknown -> UNKNOWN   else FAIL
    none  any True  -> FAIL      else any unknown -> UNKNOWN   else PASS

The first line is the subtle one. `all` means every predicate must hold, so ONE that definitely
does not is a complete answer - an outstanding balance is a violation whether or not some
unrelated field was missing. Calling that UNKNOWN would hide a real violation behind an
unrelated gap.

What must NEVER happen is the reverse: a predicate that would pass outranking a missing one.
Both directions are tested.
"""
from __future__ import annotations

from typing import Any

from ..evidence import Bundle
from ..kernel import EvidenceLine, Outcome, Verdict
from .predicates import evaluate_predicate


def evaluate_record(ir, bundle: Bundle, settings: dict[str, Any] | None = None) -> Verdict:
    """Apply one control to one record's evidence."""
    seen: list[str] = []                     # every field read, in the order it was read

    def run(predicates):
        results = []
        for predicate in predicates:
            result = evaluate_predicate(predicate, bundle, settings)
            for name in result.fields:
                if name not in seen:
                    seen.append(name)
            results.append(result)
        return results

    def answer(outcome, reason, decisive):
        return Verdict(outcome, reason, _evidence(ir, bundle, decisive, seen),
                       control_id=ir.get("control_id"), record_id=bundle.record_id)

    # ---- scope: does the control apply at all? ------------------------------------------
    scope = run(ir.get("scope", []))
    failed = _first(scope, False)
    if failed is not None:
        return answer(Outcome.EXCLUDED, "this control does not apply here: %s" % failed.reason,
                      failed.fields)
    unsure = _first(scope, None)
    if unsure is not None:
        return answer(Outcome.UNKNOWN,
                      "whether this control applies could not be established: %s"
                      % unsure.reason, unsure.fields)

    # ---- exceptions: is the record exempt? ----------------------------------------------
    exceptions = run(ir.get("exceptions", []))
    exempt = _first(exceptions, True)
    if exempt is not None:
        return answer(Outcome.EXCLUDED, "an exception applies: %s" % exempt.reason,
                      exempt.fields)
    unsure = _first(exceptions, None)
    if unsure is not None:
        return answer(Outcome.UNKNOWN,
                      "whether an exception applies could not be established: %s"
                      % unsure.reason, unsure.fields)

    # ---- assertion: does the rule hold? -------------------------------------------------
    assertion = ir["assertion"]
    mode = assertion["mode"]
    if mode not in _MODES:
        # `aggregate` lands here at record level. It is answered by the population evaluator,
        # and saying so is better than answering the wrong question about one record.
        return answer(Outcome.UNKNOWN,
                      "this control's assertion is %r, which is a question about a group of "
                      "records rather than about this one" % mode,
                      [p["field"] for p in assertion["predicates"]])

    results = run(assertion["predicates"])
    outcome, decisive = _MODES[mode](results)
    return answer(outcome, "; ".join(result.reason for result in decisive),
                  [name for result in decisive for name in result.fields])


# --------------------------------------------------------------------------- combination
def _first(results, holds):
    for result in results:
        if result.holds is holds:
            return result
    return None


def _mode_all(results):
    violated = _first(results, False)
    if violated is not None:
        return Outcome.FAIL, [violated]
    unsure = _first(results, None)
    if unsure is not None:
        return Outcome.UNKNOWN, [unsure]
    return Outcome.PASS, results


def _mode_any(results):
    satisfied = _first(results, True)
    if satisfied is not None:
        return Outcome.PASS, [satisfied]
    unsure = _first(results, None)
    if unsure is not None:
        return Outcome.UNKNOWN, [unsure]
    return Outcome.FAIL, results


def _mode_none(results):
    satisfied = _first(results, True)
    if satisfied is not None:
        return Outcome.FAIL, [satisfied]
    unsure = _first(results, None)
    if unsure is not None:
        return Outcome.UNKNOWN, [unsure]
    return Outcome.PASS, results


_MODES = {"all": _mode_all, "any": _mode_any, "none": _mode_none}


# --------------------------------------------------------------------------- evidence table
def _evidence(ir, bundle, decisive, seen):
    """The fields that produced the verdict first, then the rest of what was read, then the
    context the control declared it needed.

    `reservation.currency` is the reason for that last group: no predicate in the checkout
    controls compares against it, but it is declared required evidence precisely so the
    currency split (R9) is visible on screen next to the answer.
    """
    order = []
    declared = [entry["field"] for entry in ir.get("required_evidence", [])]
    for name in list(decisive) + list(seen) + declared:
        if name not in order and name in bundle.fields:
            order.append(name)
    if not order:
        order = list(bundle.fields)
    return [EvidenceLine(name, bundle.fields[name]) for name in order]
