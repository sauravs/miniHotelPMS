# -*- coding: utf-8 -*-
"""
RUNNER - one control, end to end, in a box that can be read six months later.

    run(control_id, tenant, evidence, as_of) -> Run

Orchestration only. It picks up an IR by id, asks the evidence layer for a bounded population,
asks the evaluator for verdicts, and records enough context to make the answer defensible:
which control, as of when, over which body of evidence, against which provider, and at what cost
in provider calls.

NOTHING HERE KNOWS WHAT ANY CONTROL IS. The control id names a file, the IR names its own
population and evidence, and a twelfth control is a file rather than a branch. The runner offers
whatever `spec/ir/` contains, which is the claim success criterion 6 rests on.

A RUN THAT COULD NOT HAPPEN SAYS SO, AS A SENTENCE
--------------------------------------------------
Any layer can refuse: a response this capture never held, an entity the provider cannot cut into
records, a call budget exhausted. Each of those reaches the screen as a stated reason rather than
a stack trace - and a blocked run shows NO COUNT TILES, because four zeroes read as a clean bill
of health for a control that never ran.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..evaluator import evaluate_population
from ..evidence import BudgetExceeded, CallBudget, gather
from ..kernel import Clock, Outcome, Verdict
from ..providers.base import ProviderError
from ..spec import SpecError, TenantConfig, load
from .coverage import Coverage, coverage_of


@dataclass(frozen=True, slots=True)
class Run:
    """One execution of one control: the verdicts, and everything needed to read them later."""

    control_id: str
    control_name: str
    natural_language: str
    tenant_id: str
    provider: str
    evidence_label: str
    evidence_is_synthetic: bool
    as_of: str
    created_at: datetime
    calls: int
    verdicts: tuple[Verdict, ...] = ()
    blocked: str | None = None
    run_id: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        """Every record lands in exactly one bucket, and EXCLUDED is its own.

        Folding exclusions into passes would let a run over a hundred records where ninety were
        out of scope report "90 passed" - a compliance number made of records nobody checked.
        """
        tally = {outcome.value: 0 for outcome in Outcome}
        for verdict in self.verdicts:
            tally[verdict.outcome.value] += 1
        tally["total"] = len(self.verdicts)
        return tally

    @property
    def coverage(self) -> Coverage:
        return coverage_of(self.verdicts)

    @property
    def is_blocked(self) -> bool:
        return self.blocked is not None

    def __repr__(self) -> str:
        if self.is_blocked:
            return "Run(%s, blocked)" % self.control_id
        return "Run(%s, %s)" % (self.control_id, self.counts)


def run(control_id: str, tenant: TenantConfig, adapter, clock: Clock,
        evidence_label: str = "", budget: CallBudget | None = None,
        created_at: datetime | None = None, spec_dir=None) -> Run:
    """Execute one control over one body of evidence."""
    ir = load(control_id, spec_dir) if spec_dir else load(control_id)
    budget = budget or CallBudget(tenant.call_budget)

    blocked = None
    verdicts: tuple[Verdict, ...] = ()
    try:
        evidence = gather(ir, adapter, tenant, clock, budget)
        verdicts = tuple(evaluate_population(ir, evidence.bundles, tenant.settings))
    except BudgetExceeded as exc:
        # R1/R8 - the budget stops the run. Saying so is the point; a stack trace is not.
        blocked = "This run was stopped by its call budget: %s" % exc
    except ProviderError as exc:
        blocked = ("This control needs evidence this body of responses does not hold: %s" % exc)
    except SpecError as exc:
        blocked = "This control's specification cannot be executed: %s" % exc

    source = getattr(adapter, "source", None)
    return Run(
        control_id=control_id,
        control_name=ir.name,
        natural_language=ir.natural_language,
        tenant_id=tenant.tenant_id,
        provider=adapter.name,
        evidence_label=evidence_label or getattr(source, "origin", "unspecified"),
        evidence_is_synthetic=bool(getattr(source, "is_synthetic", False)),
        as_of=clock.today().isoformat(),
        created_at=created_at or datetime.now(),
        calls=budget.spent,
        verdicts=verdicts,
        blocked=blocked)
