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

AND A RUN ON OLD EVIDENCE SAYS THAT TOO
----------------------------------------
Finding F7's second half. Every IR declares a `maximum_age`, and a run answering an hourly
control from a snapshot taken last month is making a claim about last month. It is still a real
answer about real records - staleness is not an error and must not suppress the verdicts - but a
reader deciding whether to act on it needs to know which. So a Run records WHEN its evidence was
obtained, and `freshness` compares that against what the control asked for. Evidence whose age
cannot be established is stale, never assumed current.

EVERY INSTANT ON A RUN COMES FROM THE INJECTED CLOCK. `created_at` used to come from
`datetime.now()`, which is a machine's opinion about what time it is at a hotel - the same
mistake F11 is about, one field further along.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from ..evaluator import evaluate_population
from ..evidence import BudgetExceeded, CallBudget, gather
from ..kernel import Clock, Outcome, Verdict
from ..providers.base import ProviderError
from ..spec import SpecError, TenantConfig, load
from .coverage import Coverage, coverage_of
from .scheduling import Freshness, freshness_of


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
    # When this run's evidence was OBTAINED, as opposed to what date it describes. None means
    # the body of evidence could not say - which makes the run stale rather than fresh.
    observed_at: datetime | None = None
    # What the control asks for, carried on the run so a stored run can still answer "was this
    # current?" months later without re-reading the IR it was made from.
    maximum_age: str = ""

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
    def freshness(self) -> Freshness:
        """How old this run's evidence was, against what the control asked for (F7).

        Measured against `created_at` - the instant the run happened - rather than against a
        wall clock read now, so re-reading a stored run six months later reports what was true
        WHEN IT RAN. A verdict's freshness is a property of the run, not of the reader.
        """
        return freshness_of(self.maximum_age, self.observed_at, self.created_at)

    @property
    def is_blocked(self) -> bool:
        return self.blocked is not None

    def __repr__(self) -> str:
        if self.is_blocked:
            return "Run(%s, blocked)" % self.control_id
        return "Run(%s, %s)" % (self.control_id, self.counts)


def run(control_id: str, tenant: TenantConfig, adapter, clock: Clock,
        evidence_label: str = "", budget: CallBudget | None = None,
        created_at: datetime | None = None, spec_dir=None,
        observed_at: datetime | None = None) -> Run:
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
        # From the CLOCK, never from the machine. `datetime.now()` here was F11 happening one
        # field further along: a run's own timestamp decides its freshness, and a laptop in
        # another timezone would have dated it differently from the hotel it describes.
        created_at=created_at or clock.now(),
        calls=budget.spent,
        verdicts=verdicts,
        blocked=blocked,
        observed_at=observed_at if observed_at is not None else _observed(source, clock),
        maximum_age=ir["freshness_requirement"]["maximum_age"])


def _observed(source, clock: Clock) -> datetime | None:
    """When this body of evidence was obtained, in the property's timezone.

    A source that cannot say returns None, and the run is then stale rather than fresh - the
    same rule that makes a value nobody could establish an UNKNOWN rather than a PASS. The date
    is anchored at the START of the property's day: the index records a date and not a time, and
    reading it as midnight is the reading that cannot make evidence look newer than it is.
    """
    when = getattr(source, "observed_at", None)
    if not when:
        return None
    try:
        return datetime.combine(date.fromisoformat(str(when)), time.min,
                                tzinfo=clock.now().tzinfo)
    except ValueError:
        return None
