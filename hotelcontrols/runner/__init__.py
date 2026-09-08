# -*- coding: utf-8 -*-
"""
RUNNER - assembling a run, judging whether it concluded anything, deciding when it should
happen again, and reporting readiness.

Four things live here, and the last two are what v1 lacked entirely:

    run()             orchestration, and a stated reason when a run cannot happen
    coverage_of()     whether the run concluded ANYTHING - finding F5
    readiness()       what a control could answer on a provider, before it is ever run - F8
    next_evaluation() when it should run next on this provider, and why - finding F7
    freshness_of()    whether the evidence it ran on was still current - finding F7
"""
from .coverage import Coverage, coverage_of
from .readiness import EvidenceSource, Readiness, readiness
from .run import Run, run
from .scheduling import (Freshness, Plan, ScheduleError, freshness_of, next_evaluation,
                         parse_duration)

__all__ = ["Coverage", "EvidenceSource", "Freshness", "Plan", "Readiness", "Run",
           "ScheduleError", "coverage_of", "freshness_of", "next_evaluation",
           "parse_duration", "readiness", "run"]
