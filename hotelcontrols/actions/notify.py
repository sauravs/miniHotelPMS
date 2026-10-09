# -*- coding: utf-8 -*-
"""
NOTIFY - telling a task's audience about it, once, without the engine touching a network.

    dispatch(run, findings, store, notifier, *, public_url, at) -> (Delivery, ...)

Slice 19 (G8 email). The engine holds a `Notifier` PROTOCOL and nothing that can send anything.
Every backend lives in `tools/notifiers/`, outside the engine, and is INJECTED by
`tools/serve.py` - exactly as `tools/proposers/` is (D10). So criterion 11 stays true ("exactly
one file in the engine imports an outbound client"), both AST guards pass unedited, and no
module here can reach a mail server, however it is called.

WHAT AN EMAIL CARRIES, AND WHAT IT NEVER DOES
----------------------------------------------
A record id, the control, the rule's version, the amount WITH ITS CURRENCY, and a link to the
task. Nothing else from the evidence. In particular NOT the verdict's reason: a reason is built
from field values, so a rule over a guest field would quote the guest - and an email leaves the
building in a way a page on a loopback demo does not (criterion V6). The amount is the one thing
that can be copied safely, because `Money` is a Decimal and three letters and cannot hold a
name, an address or a card token. Taking ONLY money-typed evidence is what makes "no PII in an
email" true by construction rather than by review.

ONE EMAIL PER RECORD PER CHANNEL
---------------------------------
The sent marker lives on the record. It is CLAIMED before the send - a guarded UPDATE that
succeeds for exactly one caller - and RELEASED, with the reason, if the send fails. So a second
dispatch finds the claim and sends nothing, two dispatches racing send one email, and a failure
leaves the task unsent and saying why rather than marked sent.

NOTHING IS SILENTLY DROPPED
----------------------------
An audience with no configured route leaves the task unsent with "no route configured for
audience finance". A rule that names no audience says so. A closed task is never emailed - a
person already decided it. Each of those is a `Delivery` with its own outcome and a note on
the task, never an absence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..kernel import Money, Outcome
from .records import ActionRecord, Findings

EMAIL = "email"


class NotifyFailed(RuntimeError):
    """A backend could not deliver, and says why. The ONLY failure dispatch turns into a note.

    Anything else a backend raises is a defect and propagates: a bug that became a line on a
    task ("not sent: KeyError") would be a bug nobody ever sees.
    """


@dataclass(frozen=True, slots=True)
class Message:
    """One email, as data. Rendered here; sent by a backend that the engine never imports."""

    action_id: str
    tenant_id: str
    audience: str
    to: tuple[str, ...]
    subject: str
    body: str
    channel: str = EMAIL


@runtime_checkable
class Notifier(Protocol):
    """What the engine is allowed to know about a way of telling somebody.

    `route` answers who an audience is - `()` when nobody configured it - so that "no route"
    is something the engine can state rather than something a backend swallows. Addresses are
    the backend's business: they are staff personal data, and they live in its environment.
    """

    name: str
    channel: str

    def route(self, audience: str) -> tuple[str, ...]:
        """The addresses for an audience, or () when none is configured."""

    def send(self, message: Message) -> None:
        """Deliver, or raise `NotifyFailed` saying why not."""


@dataclass(frozen=True, slots=True)
class Delivery:
    """What dispatch did with one task, so a caller - and slice 20's log - can say it."""

    action_id: str
    outcome: str        # sent | already_sent | no_route | no_audience | not_notify | closed | failed
    note: str | None = None


def amounts_of(verdict) -> tuple[str, ...]:
    """The money in a verdict's evidence, each as `field amount CURRENCY`. Nothing else.

    Money only, because it is the one evidence type that cannot carry a guest's details (see
    the module docstring). Rendered through `Value`'s own string, so the currency is never
    separated from the amount on the way out (R9).
    """
    return tuple("%s %s" % (line.field, line.value) for line in verdict.evidence
                 if line.value.is_known and isinstance(line.value.payload, Money))


def task_link(public_url: str, record: ActionRecord) -> str:
    """Where the task is: its property's queue, at the task. Carries `?property=` (slice 17)."""
    return "%s/queue?property=%s#task-%s" % (public_url.rstrip("/"), record.tenant_id,
                                             record.action_id)


def render_message(record: ActionRecord, *, to: tuple[str, ...], amounts: tuple[str, ...],
                   link: str) -> Message:
    """The email for one task. Built from the record's identity, the amounts and the link.

    The record's `reason` is deliberately not an input to anything below.
    """
    subject = "[%s] %s - record %s" % (record.severity, record.control_name, record.record_id)
    lines = [
        "A control found a violation that is waiting for %s." % (record.audience or "somebody"),
        "",
        "Control:   %s (%s), judged under v%d" % (record.control_name, record.control_id,
                                                 record.policy_version),
        "Record:    %s" % record.record_id,
        "Severity:  %s" % record.severity,
    ]
    lines.extend("Amount:    %s" % amount for amount in amounts)
    lines.extend([
        "Asked as of %s, over %s." % (record.as_of, record.evidence_label),
        "",
        "The task, with the evidence behind it: %s" % link,
        "",
        "This is advisory. Nothing has been changed in any system. A person marks the task done "
        "or dismisses it.",
    ])
    return Message(action_id=record.action_id, tenant_id=record.tenant_id,
                   audience=record.audience or "", to=tuple(to), subject=subject,
                   body="\n".join(lines) + "\n")


def dispatch(run, findings: Findings, store, notifier: Notifier, *, public_url: str,
             at: datetime) -> tuple[Delivery, ...]:
    """Email the tasks THIS run failed, each once, and say what happened to every one of them.

    Scoped to this run's FAILs on purpose: a run that concluded nothing or was blocked has no
    FAILs, so it sends nothing - stated by construction, not by a check that could be skipped
    (brief §8.5). A task left unsent for want of a route is tried again the next time a run
    still finds it failing.
    """
    verdicts = {v.record_id: v for v in run.verdicts if v.outcome is Outcome.FAIL}
    deliveries = []
    for finding in findings.failing:
        record = store.action(finding.action_id, tenant_id=findings.tenant_id)
        deliveries.append(_deliver(record, verdicts.get(record.record_id), store, notifier,
                                   public_url, at))
    return tuple(deliveries)


def _deliver(record: ActionRecord, verdict, store, notifier: Notifier, public_url: str,
             at: datetime) -> Delivery:
    tenant_id = record.tenant_id
    if record.notified_at is not None:
        return Delivery(record.action_id, "already_sent")
    if not record.is_pending:
        return Delivery(record.action_id, "closed")
    if record.kind != "notify":
        # A rule that asked for a dashboard or a report did not ask for an email.
        return Delivery(record.action_id, "not_notify")
    if not record.audience:
        note = "the rule names no audience, so there is nobody to email"
        store.note_notification(record.action_id, tenant_id=tenant_id, note=note)
        return Delivery(record.action_id, "no_audience", note)
    to = notifier.route(record.audience)
    if not to:
        note = "no route configured for audience %s" % record.audience
        store.note_notification(record.action_id, tenant_id=tenant_id, note=note)
        return Delivery(record.action_id, "no_route", note)
    if not store.claim_notification(record.action_id, tenant_id=tenant_id,
                                    channel=notifier.channel, at=at):
        return Delivery(record.action_id, "already_sent")       # another dispatch won the claim
    message = render_message(record, to=to,
                             amounts=amounts_of(verdict) if verdict is not None else (),
                             link=task_link(public_url, record))
    try:
        notifier.send(message)
    except NotifyFailed as exc:
        note = "not sent: %s" % exc
        store.release_notification(record.action_id, tenant_id=tenant_id, note=note)
        return Delivery(record.action_id, "failed", note)
    except BaseException:
        # A defect, not a delivery problem: release the claim so the task is not left looking
        # sent, and let the defect surface.
        store.release_notification(record.action_id, tenant_id=tenant_id, note=None)
        raise
    return Delivery(record.action_id, "sent")
