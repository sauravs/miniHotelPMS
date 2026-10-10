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

Armed, it sends EXACTLY the distinct requests the same arguments print, each once, and nothing
else (issue #70). The first version sent each control's population call and nothing more, while
the plan above it printed the references too - so the command written down for open question
1.2 would have sent a 90-day reservation query nobody approved instead of the two room calls it
was for. A plan that cannot be sent as printed is refused whole: a per-record call (printed
with a placeholder record id), or a request the live form refuses.

ONE CALL AT A TIME
-------------------
D3 approves calls, and one control's plan can hold three. `--endpoint` narrows a plan to the
requests to one endpoint, and `--reask FILE` asks again, verbatim, the question recorded beside
a captured response - which is how a capture is refreshed so that old and new answer the same
question. `--with` may add one option to a re-asked question, from a list of one (#49) - or to
a control's own POPULATION question (#92), which is how a capture asks a window nobody recorded
yet: #71's covering capture is six controls' arrival window, with room prices. A reference or a
per-record call never takes the option; it is a different question from the one the control
asks of them.
"""
from __future__ import annotations

import argparse
import json
import sys

from hotelcontrols.evidence.population import build_request
from hotelcontrols.kernel import FixedClock, PropertyClock
from hotelcontrols.providers import registry as providers
from hotelcontrols.providers.base import ProviderError, Request
from hotelcontrols.providers.transport import (Credentials, LiveSource, MissingCredential,
                                               Recorder, TransportDisabled, assert_armed)
from hotelcontrols.providers.transport.record import FIXTURE_ROOT
from hotelcontrols.spec import (SpecError, TenantConfig, available,
                                available_tenants, load)

# What a plan prints where a credential would be. Never the environment's value.
PLACEHOLDER = Credentials(user="<user>", password="<password>", hotel="<hotel>",
                          base_url="<base-url>")

# A record id, for showing the SHAPE of a per-record call without naming a real guest's booking.
SAMPLE_RECORD = "<record-id>"

# What `--with` may add to a re-asked question, and why each is allowed. One entry, on purpose.
# An option can change WHICH records come back as well as what each carries - `Cancellations`
# would widen a population - so adding a name here is a decision about R1 and R8, not a flag.
ADDABLE = {
    "IncludeRoomPrices": "no reservation capture was taken with room prices, so `stay.rate_code` "
                         "is absent from every one of them and control 15 has never seen a "
                         "rate code (#49)",
}


class Refused(Exception):
    """A plan that cannot be made, or cannot be sent as printed. Says which, and what to do."""


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


class Section:
    """One heading in a printed plan - a control, or a re-asked question - and its stages."""

    __slots__ = ("title", "stages")

    def __init__(self, title: str, stages) -> None:
        self.title = title
        self.stages = list(stages)


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


def narrow(stages: list[Stage], endpoint: str) -> list[Stage]:
    """The same stages, keeping only the requests to one endpoint (issue #70).

    The stage survives with its name and its reason, so a narrowed plan still says whether the
    call it holds is a population, a reference or a per-record call."""
    kept = [Stage(stage.name, stage.why,
                  [request for request in stage.requests if request.endpoint == endpoint],
                  per_record=stage.per_record)
            for stage in stages]
    return [stage for stage in kept if stage.requests]


def reask(provider: str, filename: str, additions=()) -> list[Stage]:
    """The question recorded beside a captured response, asked again verbatim.

    Verbatim because a refreshed capture is only comparable with the old one if both answered
    the same question - the fingerprint is what a replay is checked against (F19c, issue #9).
    The only change allowed is an option from `ADDABLE`, and never one the recorded question
    already carries: overwriting a recorded parameter would be a different question wearing
    the old one's name.
    """
    index = json.loads((FIXTURE_ROOT / provider / "index.json").read_text(encoding="utf-8"))
    entry = next((r for r in index["responses"] if r["file"] == filename), None)
    if entry is None:
        raise Refused("No recorded response called %r in fixtures/%s/index.json. Recorded: %s"
                      % (filename, provider,
                         ", ".join(r["file"] for r in index["responses"])))

    params = json.loads(json.dumps(entry["request"]))         # a copy the index never sees
    reasons = _add(params, additions, filename)

    why = "the question recorded for %s (captured %s), asked again verbatim" % (
        filename, entry.get("captured_at", "on a date not recorded"))
    return [Stage("re-ask", "; ".join([why] + reasons),
                  [Request(entry["endpoint"], params)])]


def with_options(stages: list[Stage], additions, title: str) -> list[Stage]:
    """A control's plan with each `--with` option added to its POPULATION question (#92).

    Only there: the population is the question a control asks about records, and the options
    on `ADDABLE` qualify that question. A reference asks for the property's master data and a
    per-record call names one record; adding an option to either would print - and send - a
    call the control never makes. A plan with no population question to add to is refused,
    rather than printed as if the option had been applied.
    """
    if not additions:
        return stages
    if not any(stage.name == "population" for stage in stages):
        raise Refused("--with adds an option to a control's population question, and the plan "
                      "for %s holds none. It holds: %s"
                      % (title, ", ".join(sorted({request.endpoint for stage in stages
                                                  for request in stage.requests}))))
    changed = []
    for stage in stages:
        if stage.name != "population":
            changed.append(stage)
            continue
        requests, reasons = [], []
        for request in stage.requests:
            params = json.loads(json.dumps(request.params or {}))    # never the IR's own dict
            reasons = _add(params, additions, "the population question of %s" % title)
            requests.append(Request(request.endpoint, params))
        changed.append(Stage(stage.name, "; ".join([stage.why] + reasons), requests,
                             per_record=stage.per_record))
    return changed


def _add(params: dict, additions, question: str) -> list[str]:
    """Set each option in `additions` on `params`, in place. Returns the reasons to print.

    The one gate for `--with`, wherever it adds: only an option on `ADDABLE`, and never one the
    question already asks - overwriting a parameter would be a different question wearing the
    old one's name.
    """
    reasons = []
    for name in additions:
        if name not in ADDABLE:
            raise Refused("--with %s is not allowed. A question may add only: %s. An option "
                          "can widen which records come back, so the list is a decision "
                          "(R1, R8)" % (name, ", ".join(sorted(ADDABLE))))
        if name in params:
            raise Refused("%s already asks %s=%r. --with adds an option; it never overwrites "
                          "what the question asked" % (question, name, params[name]))
        params[name] = True
        reasons.append("plus %s: %s" % (name, ADDABLE[name]))
    return reasons


def sendable(sections: list[Section], encoder) -> list[Request]:
    """The distinct requests a printed plan names, in printed order - or a refusal (issue #70).

    All or nothing. Sending the part of a plan that can be sent would be sending a different
    plan from the one approved, which is the defect this function exists to close.
    """
    chosen: dict[str, Request] = {}
    for section in sections:
        for stage in section.stages:
            if stage.per_record:
                raise Refused(
                    "%s holds a per-record call (%s), printed with a placeholder record id, so "
                    "it cannot be sent as printed. Narrow the plan with --endpoint to the calls "
                    "that can" % (section.title.split()[-1],
                                  ", ".join(r.endpoint for r in stage.requests)))
            for request in stage.requests:
                try:
                    encoder(request, PLACEHOLDER)
                except ProviderError as refusal:
                    raise Refused("%s cannot be sent: %s" % (request.endpoint, refusal)) \
                        from refusal
                chosen.setdefault(request.key(), request)
    return list(chosen.values())


def render(section: Section, tenant: TenantConfig, encoder, records: int) -> str:
    """The plan, as something that can be pasted into a message and approved."""
    stages = section.stages
    lines = ["", "=" * 78,
             section.title,
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
class Prepared:
    """Everything one invocation resolved before printing anything: shared by `--plan` and
    `--run`, so the plan printed and the requests sent cannot come from two computations."""

    __slots__ = ("tenant", "package", "clock", "sections")

    def __init__(self, tenant, package, clock, sections) -> None:
        self.tenant = tenant
        self.package = package
        self.clock = clock
        self.sections = sections


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print what a live probe would ask for. Makes no calls without --run.")
    parser.add_argument("--plan", action="store_true",
                        help="print the plan and make no calls at all (the default)")
    parser.add_argument("--run", action="store_true",
                        help="send exactly the requests the plan prints. Refuses unless armed")
    parser.add_argument("--yes", action="store_true",
                        help="confirm --run. Required, because D3 says each probe is approved")
    parser.add_argument("--property", default=None, help="which property to probe")
    parser.add_argument("--control", action="append", default=None,
                        help="one control id; repeatable. Default: every control")
    parser.add_argument("--endpoint", default=None,
                        help="narrow the plan to its requests to this one endpoint")
    parser.add_argument("--reask", default=None, metavar="FILE",
                        help="ask again, verbatim, the question recorded for FILE in the "
                             "provider's fixture index")
    parser.add_argument("--with", dest="additions", action="append", default=[],
                        metavar="OPTION", help="add OPTION to a --reask question, or to a "
                        "control's population question (never a reference or a per-record "
                        "call). Allowed: %s" % ", ".join(sorted(ADDABLE)))
    parser.add_argument("--as-of", default=None,
                        help="the date to resolve relative windows against (YYYY-MM-DD)")
    parser.add_argument("--records", type=int, default=10,
                        help="assumed population size, for costing the per-record stage")
    return parser


def prepare(argv=None, arguments=None) -> Prepared:
    """Resolve the property, the clock and the plan. Raises `Refused`, saying why."""
    arguments = arguments or _parser().parse_args(argv)

    tenants = available_tenants()
    property_id = arguments.property or (tenants[0] if tenants else None)
    if property_id not in tenants:
        raise Refused("No property called %r. This deployment has: %s"
                      % (property_id, ", ".join(tenants) or "(none)"))
    if arguments.reask and arguments.control:
        raise Refused("REFUSED: --reask and --control are one or the other. A plan made of "
                      "both would be approved as one thing and be two")

    tenant = TenantConfig.load(property_id)
    package = providers.load(tenant.provider)
    # Built to be ASKED, never to be fetched from: the plan reads structure - which endpoint,
    # which key, which reference - and makes no call of any kind.
    adapter, source = package.build(tenant)
    clock = (FixedClock.at(arguments.as_of, tenant.timezone) if arguments.as_of
             else FixedClock.at(source.as_of, tenant.timezone))

    if arguments.reask:
        try:
            stages = reask(tenant.provider, arguments.reask, arguments.additions)
        except Refused as refusal:
            raise Refused("REFUSED: %s" % refusal) from refusal
        sections = [Section("RE-ASK    %s" % arguments.reask, stages)]
    else:
        control_ids = arguments.control or list(available())
        unknown = [c for c in control_ids if c not in available()]
        if unknown:
            raise Refused("No control called %s. Try: %s"
                          % (", ".join(unknown), ", ".join(available())))
        sections = [Section("CONTROL   %s" % control_id,
                            plan_for(control_id, tenant, adapter, clock))
                    for control_id in control_ids]

    if arguments.endpoint:
        narrowed = [Section(section.title, narrow(section.stages, arguments.endpoint))
                    for section in sections]
        for before, after in zip(sections, narrowed):
            if not after.stages:
                held = sorted({request.endpoint for stage in before.stages
                               for request in stage.requests})
                raise Refused("REFUSED: the plan for %s holds no %s request. It holds: %s"
                              % (before.title.split()[-1], arguments.endpoint,
                                 ", ".join(held)))
        sections = narrowed
    if arguments.additions and not arguments.reask:
        # After narrowing, so `--endpoint getRooms --with ...` is refused for holding no
        # population question rather than printing a reference with an option it never takes.
        try:
            sections = [Section(section.title,
                                with_options(section.stages, arguments.additions,
                                             section.title.split()[-1]))
                        for section in sections]
        except Refused as refusal:
            raise Refused("REFUSED: %s" % refusal) from refusal
    return Prepared(tenant, package, clock, sections)


def main(argv=None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        prepared = prepare(arguments=arguments)
    except Refused as refusal:
        print(refusal)
        return 2

    for section in prepared.sections:
        print(render(section, prepared.tenant, prepared.package.encoder, arguments.records))

    print("")
    print("Resolved against %s, the property's own clock." % prepared.clock.today().isoformat())
    if not arguments.run:
        print("PLAN ONLY. No call was made, and none can be: the live transport is off unless "
              "HOTELCONTROLS_LIVE is set, and it refuses to arm inside a test process at all.")
        return 0

    return _run(arguments, prepared)


def _run(arguments, prepared: Prepared) -> int:
    """Make the calls - if, and only if, everything says yes.

    Separate refusals, and each says which one it is. A probe that failed with one message for
    "you did not confirm", "the transport is off", "there is no password" and "this plan cannot
    be sent as printed" would send an operator looking in the wrong place most of the time.
    """
    tenant, package = prepared.tenant, prepared.package
    if not arguments.yes:
        print("REFUSED: --run needs --yes. Each probe is approved individually, bounded and "
              "staged (decision D3), and the plan above is the thing being approved.")
        return 2
    try:
        assert_armed()
        # THIS property's account (issue #22): two hotels on one PMS hold two accounts, and
        # the property the plan was printed for is the one whose credentials are read.
        credentials = Credentials.from_environment(tenant.provider, tenant.tenant_id)
    except (TransportDisabled, MissingCredential) as refusal:
        print("REFUSED: %s" % refusal)
        return 2
    if package.encoder is None:
        print("REFUSED: %s has no live request form. It can be replayed, not probed."
              % tenant.provider)
        return 2
    try:
        requests = sendable(prepared.sections, package.encoder)
    except Refused as refusal:
        print("REFUSED: %s" % refusal)
        return 2

    # Recording is not optional on a probe. A response fetched from somebody else's server and
    # not written down is a call spent to learn something nobody can check afterwards - and
    # the fingerprint beside it is what stops a later replay answering a window the capture
    # never covered (F19c, issue #9).
    recorder = recorder_for(tenant, prepared.clock, PropertyClock(tenant.timezone))
    # ONE attempt. The transport retries a transient failure, which is right for a run and
    # wrong here: a retry is a second call to somebody else's server that nobody approved
    # (D3, R8). A probe that fails says so, and asking again is a new approval.
    source = LiveSource(tenant.provider, package.encoder, credentials, prepared.clock,
                        recorder=recorder, attempts=1)
    adapter = package.adapter(tenant, source)
    print("ARMED. Sending %d call(s), each once, recording into %s"
          % (len(requests), recorder.directory))
    print("Run tools/scrub_fixtures.py over it before committing anything: a live response "
          "carries guest names, emails and free-text remarks, and this repository is public "
          "(D6, F15).")
    return send(requests, adapter)


def recorder_for(tenant: TenantConfig, plan_clock, wall_clock, **kwargs) -> Recorder:
    """Where a probe's responses are written, dated by when they were OBTAINED.

    Two dates, kept apart (F7). `as_of` is the day the plan's windows were resolved against;
    `observed_at` is the day the call is made, read from the property's clock rather than the
    machine's (F11). The first version stamped both with the plan's date, so a call made in
    October would have been recorded as observed on the July day it asked about.
    """
    observed = wall_clock.today().isoformat()
    return Recorder.for_provider(tenant.provider, capture="probe-%s" % observed,
                                 observed_at=observed, as_of=plan_clock.today().isoformat(),
                                 **kwargs)


def send(requests: list[Request], adapter) -> int:
    """The calls themselves: these and only these, each once, within the property's budget."""
    from hotelcontrols.evidence import BudgetExceeded, CallBudget
    from hotelcontrols.evidence.cache import ResponseCache

    limit = len(requests)
    if hasattr(adapter, "tenant"):
        limit = min(limit, adapter.tenant.call_budget)
    cache = ResponseCache(adapter.source.fetch, CallBudget(max(limit, 1)))
    failed = 0
    for request in requests:
        try:
            cache.get(request)
        except BudgetExceeded as stop:
            print("STOPPED: %s" % stop)
            return 1
        except ProviderError as gap:
            print("%s: %s" % (request.endpoint, gap))
            failed += 1
            continue
        print("SENT      %s %s" % (request.endpoint, request.params or "(none)"))
    print("Made %d call(s)." % cache.calls)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
