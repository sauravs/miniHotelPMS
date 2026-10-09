# -*- coding: utf-8 -*-
"""
GUEST TASKS - a guest decision, as an advisory task in slice 18's queue (slice 22).

    guest_task(decision) -> Finding | None        None for DENIED, which raises no task

The same table, the same natural key, the same state machine as a FAIL's task: (property,
template, template version, decision) - so a request submitted twice, which is one decision, is
one task, by the same `ON CONFLICT` that keeps a control run five times to one task. A person
moves it pending -> done | dismissed; nothing else does.

A GUEST TASK IS NOT A VIOLATION. It carries kind `guest_request`, and the findings queue
(`/queue`, `/api/actions`) keeps listing violations only, pointing at the guest view for these,
so no client renders "approved, 25.00 USD" with a VIOLATION badge. Its receipt is the stored
decision, not a run: `raised_by_run` holds the decision id, and the payload names it as one.

WHAT THE TASK SAYS is what a person must do, and what the engine did not: it writes nothing to
the PMS and posts no fee (G2(b) rejected), and an approval did not check whether the room is
needed for an arrival, because no evidence can establish that (G12a). Duck-typed on the decision
so this package does not import `guest/` - the dependency runs the other way.
"""
from __future__ import annotations

from .records import Finding

GUEST_REQUEST = "guest_request"

_WORDS = {"APPROVED": "APPROVED", "APPROVED_WITH_FEE": "APPROVED WITH FEE",
          "STAFF_REVIEW": "a person must decide"}

_NOT_CHECKED = ("It did not check whether the room is needed for an arrival: no evidence can "
                "establish that (G12a).")


def is_guest_task(record) -> bool:
    return getattr(record, "kind", None) == GUEST_REQUEST


def task_sentence(decision) -> str:
    """What the person carrying out the task reads. The decision's own reason travels with it,
    so a fee travels with its currency (R9)."""
    head = "Late checkout at %s for reservation %s on %s: " % (
        decision.requested_time.strftime("%H:%M"), decision.reservation_id,
        decision.received_on.isoformat())
    if decision.decision == "APPROVED_WITH_FEE":
        return ("%sAPPROVED WITH FEE %s. %s Tell the guest, record the new departure time and "
                "post the fee in the PMS - this engine writes and posts nothing. %s"
                % (head, decision.fee, decision.reason, _NOT_CHECKED))
    if decision.decision == "APPROVED":
        return ("%sAPPROVED. %s Tell the guest and record the new departure time in the PMS - "
                "this engine writes nothing. %s" % (head, decision.reason, _NOT_CHECKED))
    return "%s%s. %s" % (head, _WORDS.get(decision.decision, decision.decision),
                         decision.reason)


def guest_task(decision) -> Finding | None:
    """The task a decision raises, or None. Severity and audience are the table's, word for
    word (owner point 3), copied onto the decision when it was made."""
    if decision.action_id is None:
        return None
    task = Finding(
        tenant_id=decision.tenant_id, control_id=decision.template_id,
        control_name=decision.template_name, policy_version=decision.template_version,
        policy_digest=decision.template_digest, record_id=decision.decision_id,
        severity=decision.severity, audience=decision.audience, kind=GUEST_REQUEST,
        reason=task_sentence(decision), run_id=decision.decision_id,
        raised_at=decision.received_at, as_of=decision.received_on.isoformat(),
        provider=decision.provider, evidence_label=decision.evidence_label)
    if task.action_id != decision.action_id:
        # The decision named its task by the same natural key; if they differ, one of them was
        # built from another rule's identity, and the task would not be the decision's.
        raise ValueError("decision %s names task %s, but its natural key gives %s"
                         % (decision.decision_id, decision.action_id, task.action_id))
    return task
