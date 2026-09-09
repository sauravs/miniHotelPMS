# -*- coding: utf-8 -*-
"""
PROBE - what this engine would ask a live PMS, printed before it asks anything.

    python3 -m tools.probe --plan                      prints the plan. Makes NO calls.
    python3 -m tools.probe --plan --control checkout_money_owed --property sandbox
    python3 -m tools.probe --run --yes                 would call. Refuses unless armed.

WHY A PLAN EXISTS AT ALL
-------------------------
Decision D3: calls to the vendor sandbox are approved individually, bounded and staged. R8: the
vendor asks integrators not to query wide ranges without prior agreement, and the sandbox
belongs to them. Both of those need something to approve, and "I will run the checkout control"
is not it. This prints the endpoint, the resolved window, the stage, and the exact request body
that would go out - so the thing being approved is the thing that happens.

The bodies are rendered with PLACEHOLDER credentials (`<user>`, `<password>`), never with what
is in the environment. A plan is made to be pasted into a message to somebody, and a plan that
leaked a password the first time it was useful would be worse than no plan.

WHAT MAKES IT BOUNDED
----------------------
Every stage is counted, and the total is compared against the property's own call budget - the
same `CallBudget` a run uses (R1). A folio takes one call per reservation and there is no bulk
journal endpoint, so the per-record stage is the one that grows, and it is the one printed last
and largest. The population call is a bound, not an afterthought.

WHAT `--run` DOES
------------------
Refuses, unless the live transport is armed - which needs `HOTELCONTROLS_LIVE=1`, credentials in
the environment with no default, and no test runner in the process. That last condition is why
this file is safe to have written: no test can make this call anything.
"""
from __future__ import annotations

import argparse
import sys

from hotelcontrols.evidence.population import build_request
from hotelcontrols.kernel import FixedClock, PropertyClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.providers.base import ProviderError, Request
from hotelcontrols.providers.transport import (Credentials, LiveSource, MissingCredential,
                                               Recorder, TransportDisabled, assert_armed)
from hotelcontrols.spec import (SpecError, TenantConfig, available,
                                available_tenants, load)

# What a plan prints where a credential would be. Never the environment's value.
PLACEHOLDER = Credentials(user="<user>", password="<password>", hotel="<hotel>",
                          base_url="<base-url>")

# A record id, for showing the SHAPE of a per-record call without naming a real guest's booking.
SAMPLE_RECORD = "<record-id>"


class Stage:
    """One group of calls, and what it costs.

    Grouped rather than listed flat because the cost shape is the point: bulk calls are O(1)
    and the per-record stage is O(N). An approver needs to see which is which.
    """

    __slots__ = ("name", "why", "requests", "per_record")

    def __init__(self, name: str, why: str, requests, per_record: bool = False) -> None:
        self.name = name
        self.why = why
        self.requests = list(requests)
        self.per_record = per_record

    @property
    def calls(self) -> int:
        return len(self.requests)


def plan_for(control_id: str, tenant: TenantConfig, adapter, clock) -> list[Stage]:
    """Every call this control would make, in the order it would make them."""
    ir = load(control_id)
    stages = [Stage(
        "population",
        "the bounded set of records to look at. Not an IF statement: it exists because a "
        "folio costs one call per record (R1)",
        [build_request(ir, adapter.name, clock)])]

    references = [adapter.reference_request(reference["entity"])
                  for reference in ir.references
                  if reference.get("source") != "tenant"]
    references = [request for request in references if request is not None]
    if references:
        stages.append(Stage(
            "references",
            "property-wide data, fetched ONCE per run however many records need it (F1)",
            references))

    follow_ups = _follow_up_requests(ir, adapter)
    if follow_ups:
        stages.append(Stage(
            "per record",
            "one call PER RECORD in the population. This is the stage that grows, and the "
            "reason the population query is bounded (R1)",
            follow_ups, per_record=True))
    return stages


def _follow_up_requests(ir, adapter) -> list[Request]:
    """The per-record calls this control needs, one per distinct source rather than per field.

    Two fields from one response cost one call, not two - the same rule the evidence layer's
    cache enforces at run time. A plan that counted per field would overstate the cost and get
    a probe refused for the wrong reason.
    """
    seen: dict[str, Request] = {}
    for entry in ir["required_evidence"]:
        if entry.get("source") != "pms":
            # The hotel supplies this one, not the PMS (R13, open question 1.6). It costs no
            # call at all, and a plan that charged for it would overstate the probe.
            continue
        try:
            request = adapter.follow_up(entry["field"], SAMPLE_RECORD)
        except (ProviderError, SpecError):
            # A field this provider does not map cannot be asked for. That is a readiness
            # question - the index reports it as "connect a source for ..." - and it must not
            # stop a plan being printed for the calls that CAN be made.
            continue
        if request is not None:
            seen.setdefault(request.endpoint, request)
    return list(seen.values())


def render(control_id: str, tenant: TenantConfig, adapter, encoder, stages,
           records: int) -> str:
    """The plan, as something that can be pasted into a message and approved."""
    lines = ["", "=" * 78,
             "CONTROL   %s" % control_id,
             "PROPERTY  %s (%s), timezone %s" % (tenant.tenant_id, tenant.provider,
                                                 tenant.timezone),
             "BUDGET    %d call(s) per run; this plan assumes %d record(s) in the population"
             % (tenant.call_budget, records),
             "=" * 78]

    total = 0
    for stage in stages:
        cost = stage.calls * (records if stage.per_record else 1)
        total += cost
        lines.append("")
        lines.append("-- stage: %s  (%d call%s)" % (stage.name, cost, "" if cost == 1 else "s"))
        lines.append("   %s" % stage.why)
        for request in stage.requests:
            lines.append("")
            lines.append("   endpoint %s" % request.endpoint)
            lines.append("   filters  %s" % (request.params or "(none)"))
            lines.extend(_encoded(encoder, request))

    lines.append("")
    lines.append("TOTAL     %d call(s)%s" % (
        total, "" if total <= tenant.call_budget
        else "  -- OVER the property's budget of %d. Narrow the window rather than raising it "
             "(R1, R8)" % tenant.call_budget))
    return "\n".join(lines)


def _encoded(encoder, request: Request) -> list[str]:
    """The exact bytes that would go out, with placeholders where the credentials are.

    A provider with no encoder can be replayed and cannot be probed. That is a real difference
    - nobody has ever called it - and saying so is better than printing a plan for calls this
    engine does not know how to make.
    """
    if encoder is None:
        return ["   request  (this provider has no live request form: it can be replayed, "
                "not probed)"]
    try:
        call = encoder(request, PLACEHOLDER)
    except ProviderError as refusal:
        return ["   request  REFUSED: %s" % refusal]
    body = "\n".join("            | %s" % line for line in call.body.splitlines())
    return ["   %s %s" % (call.method, call.url), body]


# --------------------------------------------------------------------------- the command
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Print what a live probe would ask for. Makes no calls without --run.")
    parser.add_argument("--plan", action="store_true",
                        help="print the plan and make no calls at all (the default)")
    parser.add_argument("--run", action="store_true",
                        help="actually make the calls. Refuses unless the transport is armed")
    parser.add_argument("--yes", action="store_true",
                        help="confirm --run. Required, because D3 says each probe is approved")
    parser.add_argument("--property", default=None, help="which property to probe")
    parser.add_argument("--control", action="append", default=None,
                        help="one control id; repeatable. Default: every control")
    parser.add_argument("--as-of", default=None,
                        help="the date to resolve relative windows against (YYYY-MM-DD)")
    parser.add_argument("--records", type=int, default=10,
                        help="assumed population size, for costing the per-record stage")
    arguments = parser.parse_args(argv)

    tenants = available_tenants()
    property_id = arguments.property or (tenants[0] if tenants else None)
    if property_id not in tenants:
        print("No property called %r. This deployment has: %s"
              % (property_id, ", ".join(tenants) or "(none)"))
        return 2

    tenant = TenantConfig.load(property_id)
    package = providers.load(tenant.provider)
    # Built to be ASKED, never to be fetched from: the plan reads structure - which endpoint,
    # which key, which reference - and makes no call of any kind.
    adapter, source = package.build(tenant)
    clock = (FixedClock.at(arguments.as_of, tenant.timezone) if arguments.as_of
             else FixedClock.at(source.as_of, tenant.timezone))

    control_ids = arguments.control or list(available())
    unknown = [c for c in control_ids if c not in available()]
    if unknown:
        print("No control called %s. Try: %s" % (", ".join(unknown), ", ".join(available())))
        return 2

    for control_id in control_ids:
        print(render(control_id, tenant, adapter, package.encoder,
                     plan_for(control_id, tenant, adapter, clock), arguments.records))

    print("")
    print("Resolved against %s, the property's own clock." % clock.today().isoformat())
    if not arguments.run:
        print("PLAN ONLY. No call was made, and none can be: the live transport is off unless "
              "HOTELCONTROLS_LIVE is set, and it refuses to arm inside a test process at all.")
        return 0

    return _run(arguments, tenant, package, clock)


def _run(arguments, tenant, package, clock) -> int:
    """Make the calls - if, and only if, everything says yes.

    Three separate refusals, and each says which one it is. A probe that failed with one
    message for "you did not confirm", "the transport is off" and "there is no password" would
    send an operator looking in the wrong place two times out of three.
    """
    if not arguments.yes:
        print("REFUSED: --run needs --yes. Each probe is approved individually, bounded and "
              "staged (decision D3), and the plan above is the thing being approved.")
        return 2
    try:
        assert_armed()
        credentials = Credentials.from_environment(tenant.provider)
    except (TransportDisabled, MissingCredential) as refusal:
        print("REFUSED: %s" % refusal)
        return 2
    if package.encoder is None:
        print("REFUSED: %s has no live request form. It can be replayed, not probed."
              % tenant.provider)
        return 2

    # Recording is not optional on a probe. A response fetched from somebody else's server and
    # not written down is a call spent to learn something nobody can check afterwards - and
    # the fingerprint beside it is what stops a later replay answering a window the capture
    # never covered (F19c, issue #9).
    recorder = Recorder.for_provider(tenant.provider, capture="probe-%s" % clock.today(),
                                     observed_at=clock.today().isoformat())
    source = LiveSource(tenant.provider, package.encoder, credentials, clock,
                        recorder=recorder)
    adapter = package.adapter(tenant, source)
    print("ARMED. Recording into %s" % recorder.directory)
    print("Run tools/scrub_fixtures.py over it before committing anything: a live response "
          "carries guest names, emails and free-text remarks, and this repository is public "
          "(D6, F15).")
    return _execute(arguments, adapter, clock)


def _execute(arguments, adapter, clock) -> int:
    """The calls themselves, bounded by the property's own budget."""
    from hotelcontrols.evidence import BudgetExceeded, CallBudget
    from hotelcontrols.evidence.cache import ResponseCache

    budget = CallBudget(min(arguments.records + 5, adapter.tenant.call_budget)
                        if hasattr(adapter, "tenant") else arguments.records + 5)
    cache = ResponseCache(adapter.source.fetch, budget)
    for control_id in arguments.control or list(available()):
        ir = load(control_id)
        try:
            cache.get(build_request(ir, adapter.name, clock))
        except BudgetExceeded as stop:
            print("STOPPED: %s" % stop)
            return 1
        except ProviderError as gap:
            print("%s: %s" % (control_id, gap))
    print("Made %d call(s)." % budget.spent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
