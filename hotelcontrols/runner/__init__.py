# -*- coding: utf-8 -*-
"""
RUNNER - assembling a run, judging whether it concluded anything, and reporting readiness.

Three things live here, and the second is the one v1 lacked:

    run()         orchestration, and a stated reason when a run cannot happen
    coverage_of() whether the run concluded ANYTHING - finding F5
    readiness()   what a control could answer on a provider, before it is ever run - finding F8
"""
from .coverage import Coverage, coverage_of
from .readiness import EvidenceSource, Readiness, readiness
from .run import Run, run

__all__ = ["Coverage", "EvidenceSource", "Readiness", "Run", "coverage_of", "readiness", "run"]
