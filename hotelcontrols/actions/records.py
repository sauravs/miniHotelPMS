# -*- coding: utf-8 -*-
"""
ACTION RECORDS - a failed control, turned into a task a person can see, do or dismiss.

    findings_from(run, ir) -> Findings          pure: one run in, its would-be records out

Slice 18 (G2(a), G8's queue, G10c). Every IR has carried an `action` block since slice 1 -
`{type, severity, audience}` - and nothing has read it until now. This module reads it, and
invents no configuration of its own: a record's severity and audience are the rule's, word for
word, and an IR that names no audience gets a record for no audience rather than a plausible
default that routes a finance problem to the wrong desk.

ADVISORY, PERMANENTLY. A record is a row in OUR store with a state a PERSON changes (D12, open
question 1.10). Nothing here writes to a PMS, and nothing here closes a record: a later PASS
annotates one ("no longer failing as of run X"), because whether the money was refunded is
something a person did, and the evidence only says it stopped showing.

WHAT MAKES A RECORD, AND WHAT DOES NOT
--------------------------------------
Only a FAIL. Three things that look like they might, and do not:

  - UNKNOWN. Whether UNKNOWNs become a review queue is open question 1.1, the biggest product
    question in this project, and a findings queue that quietly filled up with them would have
    answered it by accident. A task saying "the evidence was missing" is a different product
    from a task saying "this guest is owed money", and this slice builds only the second.
  - EXCLUDED. The control does not apply to the record. There is nothing to do.
  - A run that concluded nothing, or a blocked one. The engine has not looked (finding F5), and
    a run that never obtained its evidence has nothing to say to anybody (brief §8.5). Neither
    can contain a FAIL, and both are refused by name below rather than left to that accident.

IDEMPOTENCY IS THE RECORD'S NATURAL KEY (G10c, narrowed)
---------------------------------------------------------
`(property, control, policy version, record)`. Run a control five times and there is one task.
Judge it under a new version of the rule and it is a new task, while the old one stays linked
to the rule that raised it - because "breaks v2" and "breaks v3" are findings of two different
rules. `make_run_id` is untouched (plan-v3 §6.6): a repeated run is honest history, and what
must not repeat is the TASK, which is what a person, and slice 19's email, act on.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from ..kernel import Outcome

PENDING, DONE, DISMISSED = "pending", "done", "dismissed"
STATES = (PENDING, DONE, DISMISSED)

# The only moves there are. Nothing leaves `done` or `dismissed`: a person closed it, and a run
# that finds the record failing again updates its receipt rather than overruling them.
TRANSITIONS: Mapping[str, frozenset[str]] = {
    PENDING: frozenset({DONE, DISMISSED}),
    DONE: frozenset(),
    DISMISSED: frozenset(),
}

# Who moved a record, until slice 24 gives the engine a verified identity. Named for what it is
# - whoever is at the keyboard of a single-operator demo - rather than for a person nobody
# authenticated. A made-up name in an audit column is worse than an honest generic one.
OPERATOR = "operator"


class TransitionRefused(Exception):
    """A move the state machine does not allow - a closed record asked to change again.

    Separate from `ValueError` (a state that does not exist) because the two are different
    answers to a caller: one is a conflict with the record as it now stands, the other is a
    request that never named a state at all.
    """


def check_transition(current: str, target: str) -> None:
    """Refuse every move but `pending -> done | dismissed`."""
    if target not in STATES:
        raise ValueError("%r is not a state an action record can be in: the states are %s"
                         % (target, ", ".join(STATES)))
    if target not in TRANSITIONS.get(current, frozenset()):
        raise TransitionRefused(
            "this record is %s, so it cannot be marked %s. Only a pending record moves, and "
            "only to done or dismissed - a person closed it, and a closed record stays closed."
            % (current, target))


def action_id_for(*, tenant_id: str, control_id: str, policy_version: int,
                  record_id: str) -> str:
    """A record's identity: a digest of its natural key and of nothing else.

    A digest rather than `hash()`, which Python salts per process - a file store reopened
    tomorrow must find the record it made today. Nothing else goes in: not the run, not the
    instant, not the reason. Those change from run to run, and the task does not.
    """
    seed = "|".join((tenant_id, control_id, str(policy_version), record_id))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Finding:
    """One FAIL, as the record it raises - or matches, if that record already exists.

    `reason` is the verdict's own sentence, which already carries the amount WITH its currency
    (R9): "folio.balance_due is -490.75 ILS, which does not satisfy `gte 0`". The full evidence
    trail is not copied: `run_id` links to the stored run that is this record's receipt, and a
    second copy would be a second place for the two to disagree.
    """

    tenant_id: str
    control_id: str
    control_name: str
    policy_version: int
    policy_digest: str
    record_id: str
    severity: str
    audience: str | None
    kind: str
    reason: str
    run_id: str
    raised_at: datetime
    as_of: str
    provider: str
    evidence_label: str

    @property
    def key(self) -> tuple[str, str, int, str]:
        return (self.tenant_id, self.control_id, self.policy_version, self.record_id)

    @property
    def action_id(self) -> str:
        return action_id_for(tenant_id=self.tenant_id, control_id=self.control_id,
                             policy_version=self.policy_version, record_id=self.record_id)


@dataclass(frozen=True, slots=True)
class Findings:
    """What one run says to the queue: the records it failed, and the records it passed.

    The passes are here so a later PASS can ANNOTATE a record raised earlier under the same
    rule. They never create a record and never close one.
    """

    run_id: str
    tenant_id: str
    control_id: str
    policy_version: int
    at: datetime
    as_of: str
    failing: tuple[Finding, ...] = ()
    passing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """A record as the store holds it: the finding, its state, and what later runs said."""

    action_id: str
    tenant_id: str
    control_id: str
    control_name: str
    policy_version: int
    policy_digest: str
    record_id: str
    severity: str
    audience: str | None
    kind: str
    reason: str
    raised_by_run: str
    raised_at: datetime
    as_of: str
    provider: str
    evidence_label: str
    state: str
    state_changed_at: datetime | None
    state_changed_by: str | None
    # The newest run that found it failing - the current receipt. Not who raised it; that is
    # `raised_by_run`, and it never changes.
    last_failing_run: str
    last_failing_at: datetime
    # A PASS after the newest failure, under the same rule. An annotation and never a state.
    cleared_by_run: str | None = None
    cleared_at: datetime | None = None
    cleared_as_of: str | None = None
    # The sent marker (slice 19): when the task was emailed and on which channel, or - when it
    # could not be - why not. One email per record per channel, because the marker is HERE,
    # on the record slice 18's natural key already deduplicates. None, None, None: never sent.
    notified_at: datetime | None = None
    notified_via: str | None = None
    notify_note: str | None = None

    @property
    def is_pending(self) -> bool:
        return self.state == PENDING

    @property
    def annotation(self) -> str | None:
        """What the evidence has said since, in a sentence - or None if nothing changed."""
        if self.cleared_by_run is None:
            return None
        return ("No longer failing as of run %s (asked as of %s). That does not close it: a "
                "person marks it done or dismisses it, because the evidence only says the "
                "problem stopped showing, not that anybody dealt with it."
                % (self.cleared_by_run, self.cleared_as_of))


def findings_from(run, ir) -> Findings:
    """Turn one run into the records it raises, using the IR's own `action` block.

    `ir` must be the rule that judged the run - same control, same version, same digest -
    because the record takes its severity and audience from it. Handed another rule, the record
    would carry somebody else's urgency and be routed to somebody else's desk, so that is
    refused rather than tolerated.
    """
    if run.control_id != ir.control_id:
        raise ValueError("run of %r cannot raise records under the rule %r"
                         % (run.control_id, ir.control_id))
    if run.policy_version != ir.version:
        # Includes a run stored before slice 16, which reads "version not recorded": a task
        # raised from it could not say which rule it enforces, so none is raised.
        raise ValueError("run of %r was judged under version %r, but the rule handed in is "
                         "version %d; a record names the rule that raised it, so it is not "
                         "raised from a mismatch" % (run.control_id, run.policy_version,
                                                     ir.version))
    if run.policy_digest != ir.digest:
        raise ValueError("run of %r was judged under a rule whose digest differs from the one "
                         "handed in - the rule was edited between the run and its records"
                         % run.control_id)
    if not run.run_id:
        raise ValueError("an unsaved run has no run id, and a record links to the run that is "
                         "its receipt; save the run first")

    empty = Findings(run_id=run.run_id, tenant_id=run.tenant_id, control_id=run.control_id,
                     policy_version=run.policy_version, at=run.created_at, as_of=run.as_of)
    # Stated rather than left to arithmetic: neither of these can contain a FAIL, and if one
    # ever did, a queue fed by a run that never looked would be the bug this project exists
    # to prevent (F5, brief §8.5).
    if run.is_blocked or not run.coverage.concluded:
        return empty

    action = ir["action"]
    failing, passing = [], []
    for verdict in run.verdicts:
        if verdict.outcome is Outcome.FAIL:
            if not verdict.record_id:
                # Two id-less FAILs would share one natural key and collapse into one record,
                # which is a violation dropped without a word. Refused loudly instead.
                raise ValueError("a FAIL in run %s carries no record id, so it cannot be keyed "
                                 "as a record and would be merged with any other" % run.run_id)
            failing.append(Finding(
                tenant_id=run.tenant_id, control_id=run.control_id,
                control_name=run.control_name, policy_version=run.policy_version,
                policy_digest=run.policy_digest, record_id=verdict.record_id,
                severity=action["severity"], audience=action.get("audience"),
                kind=action["type"], reason=verdict.reason, run_id=run.run_id,
                raised_at=run.created_at, as_of=run.as_of, provider=run.provider,
                evidence_label=run.evidence_label))
        elif verdict.outcome is Outcome.PASS and verdict.record_id:
            passing.append(verdict.record_id)
        # UNKNOWN and EXCLUDED: nothing, on purpose. See the module docstring - 1.1 is open.

    return Findings(run_id=empty.run_id, tenant_id=empty.tenant_id,
                    control_id=empty.control_id, policy_version=empty.policy_version,
                    at=empty.at, as_of=empty.as_of, failing=tuple(failing),
                    passing=tuple(passing))
