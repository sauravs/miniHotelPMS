# -*- coding: utf-8 -*-
"""
GUEST - guest services: a structured request, decided by a table the owner approved (slice 22).

    load_template("LATE_CHECKOUT")     spec/guest/late_checkout.json, approved and checked
    parse_request(form)                a reservation id and an HH:MM - or a 400 naming the field
    load_policy(template, tenant)      the hotel's six parameters, typed by slice 21; null kept
    answer(template, request, ...)     evidence -> the table -> an identified, versioned Decision

One template in v3, `LATE_CHECKOUT` (D12): a guest asks to check out at 3 PM, and staff see
"approved, 25.00 USD" - or "a person needs to decide, because..." - as a task to carry out.

STAFF_REVIEW is guest services' UNKNOWN. Missing evidence and an undecided parameter are always
STAFF_REVIEW naming what was missing; DENIED and UNAVAILABLE come only from established evidence
or stated policy (D15), and UNAVAILABLE not at all in v3 (G12a). Every outcome is ADVISORY: the
engine never writes to a PMS and never posts a fee. No model is reachable from this package
(D12, D10) - `tests/unit/test_guest_no_model.py` walks its imports to prove it.

Pure apart from `look_up`, which spends provider calls through an adapter it is handed, by way
of the unchanged evidence layer.
"""
from .decision import (APPROVED, APPROVED_WITH_FEE, DECISIONS, DENIED, EVIDENCE_FIELDS,
                       PARAMETERS, RULES, STAFF_REVIEW, STATUSES, UNAVAILABLE, Decision, Gap,
                       Ruling, decide, decision_id_for, make_decision)
from .evidence import ReservationEvidence, look_up, window
from .fee import ROUNDINGS, charged_hours, fee_for
from .policy import Policy, load_policy, policy_from_block
from .request import GuestRequest, RequestRefused, parse_request
from .service import answer
from .template import Template, load_template, template_digest

__all__ = [
    "APPROVED", "APPROVED_WITH_FEE", "DECISIONS", "DENIED", "EVIDENCE_FIELDS", "PARAMETERS",
    "ROUNDINGS", "RULES", "STAFF_REVIEW", "STATUSES", "UNAVAILABLE",
    "Decision", "Gap", "GuestRequest", "Policy", "RequestRefused", "ReservationEvidence",
    "Ruling", "Template",
    "answer", "charged_hours", "decide", "decision_id_for", "fee_for", "load_policy",
    "load_template", "look_up", "make_decision", "parse_request", "policy_from_block",
    "template_digest", "window",
]
