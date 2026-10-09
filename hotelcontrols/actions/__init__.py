# -*- coding: utf-8 -*-
"""
ACTIONS - the findings queue: a FAIL becomes an advisory task, once (slice 18).

Above the runner and beside the store. A run does not create actions - `runner/` is
untouched - the layer above it does: the web layer saves a run, asks `findings_from` what it
raises, and hands that to the store, which keeps exactly one record per natural key.

    findings_from(run, ir) -> Findings      pure. Only a FAIL raises a record
    check_transition(current, target)       pending -> done | dismissed, and nothing else
    action_id_for(...)                      a record's identity: its natural key, digested
"""
from .records import (DISMISSED, DONE, OPERATOR, PENDING, STATES, TRANSITIONS, ActionRecord,
                      Finding, Findings, TransitionRefused, action_id_for, check_transition,
                      findings_from)

__all__ = ["DISMISSED", "DONE", "OPERATOR", "PENDING", "STATES", "TRANSITIONS",
           "ActionRecord", "Finding", "Findings", "TransitionRefused", "action_id_for",
           "check_transition", "findings_from"]
