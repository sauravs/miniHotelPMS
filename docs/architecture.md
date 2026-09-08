# Architecture — v2

> Eight layers, each a **deep module**: a wide capability behind a narrow interface. Every seam
> below is one or two function signatures, and everything a layer hides is listed with it.
> Evidence flows up; calls go down. Nothing above the provider layer knows a PMS exists.

---

## 1. The shape

```
                    ┌───────────────────────────────────────────────────┐
                    │  Browser · one page per control, evidence inline  │
                    └───────────────────────▲───────────────────────────┘
                                            │
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L7 · WEB            handle(path) -> (status, content_type, body)                 │
   │ routing · server-side rendering · JSON API · no framework, no JavaScript         │
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │ run(control_id, tenant, evidence, as_of) -> Run
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L6 · RUNNER         orchestration · Run + coverage verdict · readiness           │
   │ hides: how a run is assembled, costed, judged for coverage, and stored           │ ── UNKNOWN:
   │        ┌──────────────────────┬──────────────────────┬────────────────────────┐  │    run blocked
   │        │ L6a readiness        │ L6b scheduling       │ L6c store (sqlite)     │  │
   │        │ control × provider   │ next_evaluation()    │ history, re-read free  │  │
   │        └──────────────────────┴──────────────────────┴────────────────────────┘  │
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │ evaluate_population(ir, bundles) -> [Verdict]
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L5 · EVALUATOR      predicates · Kleene logic · scope · exceptions · aggregates  │ ── UNKNOWN:
   │ PURE. No I/O, no clock, no network, no PMS. Asserted by test, not assumed        │    value unknown
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │ gather(ir, tenant, as_of) -> EvidenceSet
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L4 · EVIDENCE       population · reference sets · run-scoped cache · budget      │ ── UNKNOWN:
   │ hides: that a folio costs one call per record, and how a join is keyed           │    fetch failed
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │ resolve(field, record) -> Value
 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┼─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
 CANONICAL BOUNDARY — no PMS name, endpoint, path or wire format appears above this line
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L3 · PROVIDERS      Provider protocol · one adapter per PMS                      │ ── UNKNOWN:
   │        ┌───────────────────────┬────────────────────┬───────────────────────┐    │    unmapped code,
   │        │ minihotel (XML)       │ demopms (JSON)     │ transport (opt-in)    │    │    0-means-unset,
   │        │ ElementTree, 3 date   │ different quirks,  │ rate limit · retry ·  │    │    currency
   │        │ formats, tenant maps  │ on purpose         │ record mode · OFF     │    │    unknown
   │        └───────────────────────┴────────────────────┴───────────────────────┘    │
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │ load_ir / registry / tenant config
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L2 · SPEC           canonical field registry · IR schema + loader · validator    │
   │        · tenant configuration (status maps, timezone, budget, nominated codes)   │
   └────────────────────────────────────────▲────────────────────────────────────────┘
                                            │
   ┌────────────────────────────────────────┴────────────────────────────────────────┐
   │ L1 · KERNEL         Value · Money(Decimal) · Outcome · Verdict · Clock · errors  │
   │ the vocabulary every other layer speaks. Depends on nothing                      │
   └─────────────────────────────────────────────────────────────────────────────────┘

   L0 · COMPILER  (English -> IR)  runs BESIDE the stack, not inside it: it produces spec
                  artifacts that L2 validates. Nothing at runtime depends on it.
```

Three properties matter more than the boxes.

**UNKNOWN originates at every layer.** It is not an error path. Any layer can legitimately produce
it, and it must survive to the screen without being flattened into a pass or a failure. This is the
property most likely to be quietly broken by an implementation that treats missing evidence as an
exception to swallow.

**The canonical boundary is absolute.** Above L3, no PMS identifier appears — no `TotalDebit`, no
`Booking@Status`, no XML, no JSON, no vendor name. That is what makes a second PMS an adapter rather
than a rewrite, and it is enforced by a grep test over the tree.

**Purity is load-bearing at L5.** The evaluator is a function of `(IR, evidence)` and nothing else.
That is what makes a verdict reproducible six months later, which is the difference between an audit
trail and an anecdote.

---

## 2. Why these layers

Each owns exactly one hard problem, and each boundary was drawn where v1's measurements showed a
seam actually is.

| Layer | Owns the problem of… | Evidence it exists |
| --- | --- | --- |
| L1 Kernel | Representing a fact, or a reasoned admission that we have none | A number without its currency let a reservation in USD meet its own folio in ILS (R9) |
| L2 Spec | Keeping the vocabulary honest and the rules data | A rule referencing a field nobody defined must be stopped before it runs, not after |
| L3 Providers | Turning a PMS-shaped response into canonical values, and admitting when it cannot | Three date formats in one API; `0` meaning "unconfigured"; per-property status codes |
| L4 Evidence | Deciding which records to look at, and what each costs | The folio endpoint takes one reservation per call; no bulk journal exists (R1) |
| L5 Evaluator | Applying the rule and choosing between four outcomes, explainably | A verdict must be defensible line by line, not merely returned |
| L6 Runner | Assembling a run, judging whether it concluded anything, and keeping it | 28 EXCLUDED / 0 FAIL looked exactly like a clean bill of health in v1 |
| L7 Web | Showing the evidence behind the answer | An unexplained verdict is not auditable, and audit is the product |
| L0 Compiler | Turning a sentence into a rule **without** turning it into executable code | §17 is explicit: LLM → executable JSON is the risky path |

---

## 3. Interfaces

Everything above a layer sees only this.

### L1 · Kernel

```python
Value = Known(value, unit, source) | Unknown(reason, risk, source)
Money = Decimal amount + currency            # a bare number is never money
Outcome = PASS | FAIL | UNKNOWN | EXCLUDED
Verdict = (outcome, reason, evidence: [(field, Value, source)], control_id, record_id)
Clock   = Protocol: today() -> date, now() -> datetime   # always property-local
```

Enforced structurally, not by convention:

- A number cannot exist without a unit. A money amount cannot exist without a currency.
- Two amounts in different currencies **refuse to compare** — they raise. The single exception is
  comparison against literal zero, which means the same in every currency.
- An unknown **refuses to compare at all**. If `unknown == 0` returned `False`, the obvious
  `PASS if v == 0 else FAIL` would report FAIL for a balance that was never established. That one
  line is the failure mode the product exists to prevent.
- A `Verdict` cannot be constructed without a reason and at least one piece of evidence.
- `NOT_APPLICABLE` is a distinct sentinel from absent and from empty (R7): *"there is no channel
  confirmation because there was no channel"* is a fact, not a gap.

### L2 · Spec

```python
registry.field(name) -> FieldSpec        # type, absent_means, risk, description
ir.load(control_id)  -> IR               # validated on load, never trusted raw
ir.validate(ir)      -> [Problem]        # references only declared vocabulary
tenant.load(id)      -> TenantConfig     # status map, department map, timezone,
                                         # currency, call budget, nominated rate codes
```

Hides: JSON on disk, schema enforcement, cross-file reference checking, and the rule that anything
used in scope/exceptions/assertions must also be declared as required evidence.

**Tenant configuration is data here, not constants in a provider module.** Status codes and folio
departments are per-property; the provider map describes an API, the tenant config describes one
hotel's vocabulary. This resolves v1's open question 1.4.

### L3 · Providers — the canonical boundary

```python
class Provider(Protocol):
    name: str
    def fetch(endpoint, params) -> Response          # opaque above this layer
    def records(response, entity) -> [Record]        # cut / project into records
    def resolve(field, record) -> Value              # canonical name in, Value out
    def source_key(field) -> Token                   # opaque: "which call yields this"
    def follow_up(field, record_id) -> Request|None  # per-record call, or None
    def reference_request(entity) -> Request|None    # whole-property call for a join
```

Hides, per adapter: the wire format and its parsing · every field path · date formats · currency
attachment · zero-means-unset · per-tenant code maps · record boundaries and projections ·
frozen-versus-live switching · request replay against fixtures.

**Two structural changes from v1.** Parsing is a real document tree rather than regexes over raw
text — v1's mappings broke silently when two XML attributes were reordered, and never decoded XML
entities. And a **projection** may assemble a record from sibling lists by a declared join, which is
what makes occupancy addressable at all; where no projection can be defined, the provider says so by
name and the control is reported as blocked rather than crashing.

**Transport is a separate, opt-in component.** It is off unless an environment variable enables it,
carries a token-bucket rate limiter, bounded retry with backoff, and a record mode that writes each
response into the fixture set with its request fingerprint. No test can switch it on.

### L4 · Evidence

```python
gather(ir, provider, tenant, as_of, budget) -> EvidenceSet
EvidenceSet  = { bundles: [Bundle], references: {entity: ReferenceIndex}, calls: int }
Bundle       = { entity, record_id, fields: {canonical -> Value} }
ReferenceIndex = { key_value -> {canonical -> Value} }     # joined by canonical key only
```

Hides: translating the IR's population query into request filters (resolving relative dates through
the tenant clock) · the bounded first call, then reference sets once each, then one follow-up per
record · a **run-scoped response cache** so one response is never fetched twice · a call budget that
**raises rather than truncating** · assembling each record's evidence into one bundle.

Cost is `1 + R + N`: one population call, one per reference set, one per record needing a follow-up.
Asserted by counting invocations, never assumed.

**What it deliberately does not do.** It does not filter the records the provider returned — the
population query is a *bound*, not a verdict, and deciding a record is out of scope is L5's rule. A
reference key that does not match resolves to UNKNOWN with that reason; **a join never invents a
match**, because wrong evidence behind a right-looking verdict is the worst thing this system can
produce.

### L5 · Evaluator

```python
evaluate_record(ir, bundle, references)      -> Verdict
evaluate_population(ir, evidence_set)        -> [Verdict]     # for aggregate assertions
```

Hides: the predicate operators · scope filtering and exceptions · **unknown precedence** · interval
arithmetic for `within` / `not_within` / `overlaps` · group computation for `count_lte` and
`aggregate` · building the evidence table that explains each verdict.

Order, and it matters:

```
scope       does this control apply to this record?   -> EXCLUDED if not
exceptions  is this record exempt?                    -> EXCLUDED if so
assertion   does the rule hold?                       -> PASS / FAIL
```

At any step the answer may be "cannot tell", and then the verdict is UNKNOWN. A control that cannot
establish whether it even applies has not passed and has not excluded anything.

**Kleene three-valued logic, not "any unknown wins":**

```
all    any False -> FAIL     else any unknown -> UNKNOWN   else PASS
any    any True  -> PASS     else any unknown -> UNKNOWN   else FAIL
none   any True  -> FAIL     else any unknown -> UNKNOWN   else PASS
```

The first line is the subtle one. Under `all`, one predicate that definitively fails is a complete
answer — an outstanding balance is a violation whether or not some unrelated field was missing. The
reverse, a would-be pass outranking a missing field, must never happen, and is tested both ways.

**Population assertions are a second shape, not a special case of the first.** `aggregate` mode
computes over the whole bundle set (group by a field, count, compare), then attributes a verdict to
each contributing record with the group's evidence attached. That is what makes control 14 —
*"two active reservations must not share the same channel confirmation number"* — expressible at
all, and it must exclude cancelled records and `NOT_APPLICABLE` channel ids (R7) or every direct
booking looks like a duplicate of every other.

### L6 · Runner

```python
run(control_id, tenant, evidence, as_of) -> Run
Run = { control, as_of, provider, evidence_origin, is_synthetic, calls,
        verdicts, counts, coverage, blocked }
readiness(control_id, provider)          -> Readiness   # fields resolvable / total, per source
next_evaluation(ir, last_run_at, now, provider_capabilities) -> datetime | EventSubscription
store.save(run) / store.load(run_id) / store.history(control_id)
```

Hides: orchestrating four layers · labelling which body of evidence a run used and whether it is
real · **the coverage verdict** · turning any layer's refusal into a stated reason rather than a
stack trace · SQLite persistence.

**The coverage verdict is new and is a first-class part of a Run.** `evaluated = PASS + FAIL`. A run
with `evaluated == 0` is rendered as *"this control reached no conclusion about any record"* with the
dominant reason — never as four tiles containing a reassuring zero. v1 reported 28 EXCLUDED / 0 FAIL
for an out-of-service-room control on a property where the mechanism had never been observed
working, and it was indistinguishable on screen from a clean result.

**Scheduling is a pure function.** `next_evaluation` reads the IR's `execution` and
`freshness_requirement`, asks the provider what events it supports, and returns when to run or what
to subscribe to. A daemon is out of scope; the decision is not, and it is fully testable with an
injected clock.

### L7 · Web

```
GET  /                                the controls the spec defines, with readiness
GET  /run/<control_id>?evidence=&as_of=   run it and render every verdict
GET  /api/run/<control_id>            the same run as JSON
GET  /api/runs/<run_id>               a stored run, re-read without a provider call
GET  /history/<control_id>            past runs, with the trend
GET  /api/readiness/<control_id>      per-provider field availability
```

Server-side rendering, no JavaScript. The demo's single job is to show that a verdict traces to the
fields that produced it, and a page that assembles itself from an API call is a page a browser, a
CSP or a `file://` open can break.

UNKNOWN is distinguished from FAIL by **hue, border style and wording** — three signals, so the
distinction survives a monochrome screen or a colour-blind reader.

### L0 · Compiler

```python
compile(sentence, registry) -> Compilation
Compilation = { ir | None, problems: [Problem], confidence, ambiguities }
```

Two front ends behind one interface:

- **`GrammarCompiler`** — a restricted-English parser. Deterministic, offline, no model. This is
  what CI runs and what the tests assert against.
- **`ModelCompiler`** — an optional adapter that asks a language model for an IR. It is not trusted:
  its output goes through `ir.validate` unchanged, and a proposal that fails is shown to the author
  with the missing vocabulary named.

**Neither may emit anything executable.** §17 of the requirements doc is explicit about why, and the
gate that makes it safe already works: fed the doc's own example — *"All VIP arrivals should have an
assigned room that is clean by 2 PM"* — v1's validator answered with the two canonical fields that
do not exist rather than producing a rule that runs and quietly answers about nothing.

---

## 4. Layout

```
hotelcontrols/
  kernel/         value.py · money.py · outcome.py · verdict.py · clock.py · errors.py
  spec/           registry.py · ir.py · validate.py · tenant.py
  providers/      base.py · registry.py
                  minihotel/  adapter.py · paths.py · transforms.py · records.py · fixtures.py
                  demopms/    adapter.py · transforms.py · fixtures.py
                  transport/  http.py · ratelimit.py · record.py     # opt-in, off by default
  evidence/       gather.py · population.py · reference.py · cache.py · budget.py
  evaluator/      record.py · population.py · predicates.py · intervals.py · logic.py
  runner/         run.py · coverage.py · readiness.py · scheduling.py
  store/          sqlite.py · schema.sql
  web/            app.py · render.py · server.py · assets/
  compiler/       grammar.py · model.py · problems.py
spec/             canonical_fields.json · ir_schema.json · ir/*.json
                  providers/minihotel.json · providers/demopms.json
                  tenants/*.json
fixtures/         minihotel/  (pseudonymised captures + request fingerprints)
                  demopms/    (fictional, by construction)
tests/            unit/ · integration/ · e2e/ · contract/
docs/             every markdown document
tools/            validate_spec.py · scrub_fixtures.py · probe.py · build_workbook.py
```

`spec/` is **data the engine reads at runtime**. Nothing in `hotelcontrols/` knows what control 6 is:
it is one IR file among eleven, and a twelfth control is a file rather than a branch. That is the
claim criterion 6 makes good on — otherwise this is a hard-coded balance check wearing an
architecture as a costume.

---

## 5. Testing strategy

Four layers, each answering a different question. **No test touches the network, ever** — a suite
that needs someone else's server to be up is not a suite.

| Layer | Question | Runs against |
| --- | --- | --- |
| **Unit** | Does this transformation do what the spec says? | Literal values, no files |
| **Integration** | Does this layer work on real captured responses? | Pseudonymised fixtures |
| **Contract** | Does every provider honour the `Provider` protocol identically? | One shared suite, run against both adapters |
| **End to end** | Does a run produce the right verdicts with their evidence? | Full stack, frozen source |

The **contract suite** is the piece v1 did not have and the one that makes criterion 7 real: a single
set of tests parameterised over every registered provider, so adding Mews means running an existing
suite rather than writing a new one.

Every test names the IR clause or the risk id it protects. `PYTHONDONTWRITEBYTECODE=1` in CI —
v1 recorded a real incident where a stale `.pyc` made the suite silently run old code and report a
green that meant nothing.

---

## 6. Deliberately out of scope

Each is recoverable later without reworking what is built now.

- **Mews.** Designed for; DemoPMS proves the seam works. Credentials do not exist.
- **A running scheduler.** The decision function is built and tested; the loop is not.
- **Webhook ingestion.** IRs declare their events; nothing subscribes.
- **Authentication, multi-tenancy at the HTTP layer, rate-limited public API.** Local demo.
- **Writing to a PMS.** Read-only, permanently.
- **Unstructured text as evidence.** Open question 3 — and if it is ever answered yes, the extractor
  must return a value only with the exact quotation it relied on, and UNKNOWN whenever the text is
  ambiguous.
- **A rule-editing UI.** Sentences arrive through the compiler; IRs arrive as files.

---

## 7. Build order, and why

1. **Kernel and spec first** — everything speaks that vocabulary, and getting `Value` wrong
   invalidates every layer above it.
2. **The provider layer next, and it is the largest.** Every quirk lives here. If evidence is right
   the layers above are comparatively small; if it is wrong, nothing above it can be trusted.
3. **Evidence before evaluator**, even though the evaluator is a pure function and pleasant to test.
   Without real bundles the evaluator gets written against imagined data rather than the shape the
   provider actually returns.
4. **Record evaluation before population evaluation** — the second is a generalisation of the first
   and is much easier to get right once the first is pinned by tests.
5. **The second provider immediately after the first end-to-end control works**, not at the end.
   Late portability work finds the boundary was already broken; early portability work keeps it.
6. **Compiler and scheduling last among features** — they sit at the edges and depend on a stable IR.
7. **Web thin, and continuously.** Its job is to prove the verdict is explainable, not to look like
   a product.

Per-slice tests and gates are in `plan.md`.
