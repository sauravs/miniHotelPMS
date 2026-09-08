# -*- coding: utf-8 -*-
"""
EVALUATOR - the rule, applied.

    evaluate_record(ir, bundle, settings) -> Verdict

A PURE FUNCTION. No I/O, no clock, no network, no knowledge of any PMS - it reads an IR and a
record's evidence and returns an answer with its working. That purity is asserted by a test
rather than assumed, because it is what makes a verdict reproducible: the same bundle yields the
same verdict forever, which is the difference between an audit trail and an anecdote.
"""
from .intervals import overlaps, within
from .predicates import (AGGREGATE_OPERATORS, PredicateResult, UnsupportedPredicate, describe,
                         evaluate_predicate)
from .population import evaluate_population
from .record import evaluate_record

__all__ = [
    "AGGREGATE_OPERATORS",
    "PredicateResult",
    "UnsupportedPredicate",
    "describe",
    "evaluate_population",
    "evaluate_predicate",
    "evaluate_record",
    "overlaps",
    "within",
]
