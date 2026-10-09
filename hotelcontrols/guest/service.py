# -*- coding: utf-8 -*-
"""
SERVICE - a request in, a decision out: evidence, then the table, then identity.

    answer(template, request, tenant=, policy=, adapter=, clock=, evidence_label=) -> Decision

The whole path, in the order the table reads it. Every input is handed in - the adapter by the
web layer, the clock injected (`kernel/clock.py` is the only wall-clock reader) - so nothing here
goes looking for a provider, a store or a model. Storing the decision and raising its task is the
layer above's job, as running a control and raising its findings is (slice 18's shape).
"""
from __future__ import annotations

from ..evidence import CallBudget
from ..kernel import Clock
from ..spec import TenantConfig
from .decision import Decision, decide, make_decision
from .evidence import look_up
from .policy import Policy
from .request import GuestRequest


def answer(template, request: GuestRequest, *, tenant: TenantConfig, policy: Policy, adapter,
           clock: Clock, evidence_label: str, budget: CallBudget | None = None) -> Decision:
    """Decide one request. `clock` decides "today" - the property's calendar day (F11)."""
    evidence = look_up(template, request.reservation_id, adapter, tenant, clock, budget)
    today = clock.today()
    ruling = decide(request, policy, evidence, today)
    return make_decision(template, request, policy, evidence, ruling, tenant_id=tenant.tenant_id,
                         received_at=clock.now(), received_on=today, provider=adapter.name,
                         evidence_label=evidence_label)
