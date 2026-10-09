# -*- coding: utf-8 -*-
"""
ACTIONS - the findings queue: a FAIL becomes an advisory task, once (slice 18).

Above the runner and beside the store. A run does not create actions - `runner/` is
untouched - the layer above it does: the web layer saves a run, asks `findings_from` what it
raises, and hands that to the store, which keeps exactly one record per natural key.

    findings_from(run, ir) -> Findings      pure. Only a FAIL raises a record
    check_transition(current, target)       pending -> done | dismissed, and nothing else
    action_id_for(...)                      a record's identity: its natural key, digested
    dispatch(run, findings, store, notifier, ...)   slice 19: email each new task once
    render_message(record, ...)             what an email carries - never the verdict's reason
    guest_task(decision)                    slice 22: a guest decision's task, or None for DENIED

A `Notifier` is a protocol here and a backend in `tools/notifiers/`, injected and never
imported: nothing in the engine can reach a mail server.
"""
from .guest import GUEST_REQUEST, guest_task, is_guest_task, task_sentence
from .notify import (EMAIL, Delivery, Message, Notifier, NotifyFailed, amounts_of, dispatch,
                     render_message, task_link)
from .records import (DISMISSED, DONE, OPERATOR, PENDING, STATES, TRANSITIONS, ActionRecord,
                      Finding, Findings, TransitionRefused, action_id_for, check_transition,
                      findings_from)

__all__ = ["DISMISSED", "DONE", "EMAIL", "GUEST_REQUEST", "OPERATOR", "PENDING", "STATES",
           "TRANSITIONS", "ActionRecord", "Delivery", "Finding", "Findings", "Message",
           "Notifier", "NotifyFailed", "TransitionRefused", "action_id_for", "amounts_of",
           "check_transition", "dispatch", "findings_from", "guest_task", "is_guest_task",
           "render_message", "task_link", "task_sentence"]
