# -*- coding: utf-8 -*-
"""
EVIDENCE - which records to look at, and what each one costs.

    gather(ir, provider, tenant, clock, budget) -> EvidenceSet

The first layer above the canonical boundary, so it does not know which PMS is answering. The
strict test of that claim is a grep: no provider name, endpoint or field path appears anywhere
in this package, prose included.

It works with canonical field names, opaque `Request` objects carried as data in the IR, and two
tokens the adapter hands out - `source_key`, saying which call yields a field, and `follow_up`,
building the per-record call. It never interprets either.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not filter the records the provider returned. The population query is a BOUND, not a
verdict: deciding a record is out of scope is the evaluator's job, and doing it here as well
would mean the scope rule could never be exercised on real data.

It does not invent a join. A reference key that matches nothing resolves to UNKNOWN with that
reason - because wrong evidence behind a right-looking verdict is the worst thing this system
can produce.
"""
from .budget import BudgetExceeded, CallBudget
from .cache import ResponseCache
from .gather import Bundle, EvidenceSet, gather
from .population import build_request, population
from .reference import ReferenceIndex, build_references

__all__ = [
    "Bundle",
    "BudgetExceeded",
    "CallBudget",
    "EvidenceSet",
    "ReferenceIndex",
    "ResponseCache",
    "build_references",
    "build_request",
    "gather",
    "population",
]
