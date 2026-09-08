# -*- coding: utf-8 -*-
"""
hotelcontrols - a PMS-agnostic engine for hotel governance controls.

A hotel states a rule in plain English; the engine compiles it to a representation that names
no PMS, resolves the evidence it needs from whichever property management system the hotel
runs, and answers PASS / FAIL / UNKNOWN / EXCLUDED with the evidence that produced it.

Layers, bottom to top (see docs/architecture.md):

    kernel      the vocabulary every other layer speaks. Depends on nothing
    spec        canonical field registry, control IR, tenant configuration
    providers   one adapter per PMS. THE CANONICAL BOUNDARY - nothing above knows a PMS exists
    evidence    bounded population, reference joins, call budget
    evaluator   pure. Predicates, three-valued logic, four outcomes
    runner      orchestration, coverage, readiness, scheduling
    store       run history
    web         server-rendered pages and a JSON API
    compiler    English -> IR. Runs beside the stack, not inside it

No module here imports anything outside the standard library. That is success criterion 11,
and tests/unit/test_stdlib_only.py enforces it by walking this tree.
"""

__version__ = "2.0.0.dev0"
