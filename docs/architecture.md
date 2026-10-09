# Architecture — v2

> Eight layers, each a **deep module**: a wide capability behind a narrow interface. Every seam
> below is one or two function signatures, and everything a layer hides is listed with it.
> Evidence flows up; calls go down. Nothing above the provider layer knows a PMS exists.

---

## 1. The shape

```
     ┌──────────────────────────────────┐        ┌──────────────────────────────────────┐
     │ Browser · the engine's own pages │        │ Browser · ui/  (Next.js + React)     │
     │ server-rendered, no JavaScript   │        │ OUTSIDE the engine. Reads JSON only  │
     └────────────────▲─────────────────┘        └───────────────────▲──────────────────┘
                      │ HTML                                         │ JSON, via ui/'s server
   ┌──────────────────┴──────────────────────────────────────────────┴───────────────┐
   │ L7 · WEB            handle(path) -> (status, content_type, body)                 │
   │ routing · server-side rendering · JSON API · no framework, no JavaScript in it   │
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

   L0 · COMPILER  (prose -> English -> IR)  runs BESIDE the stack, not inside it: it produces
                  spec artifacts that L2 validates. Nothing at runtime depends on it.
                  A sentence PROPOSER is injected from tools/, never imported - which is what
                  keeps the engine stdlib-only while a model can still draft a sentence (D10).
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
ir.version / ir.digest -> int / "sha256:..."   # since slice 16: which rule this is
lock.read_lock(spec) -> {control: (version, digest)}   # spec/ir.lock.json
lock.lock_problems(spec) -> [Problem]    # content changed without a bump; version went back
tenant.load(id)      -> TenantConfig     # status map, department map, timezone,
                                         # currency, call budget, nominated rate codes
```

**A version cannot lie (slice 16, G6b).** Every IR has carried `"version": 2`, and since slice 16
the loader reads it. A version kept by hand is a number that can drift from the rule, so it is paired
with a **digest** of the rule's verdict-bearing content: population, references, scope, exceptions,
assertion, required evidence, unknown conditions, and the sentences shown beside a verdict (entity,
name, natural and restricted language). `note` prose, the schedule, freshness, the action block and
caveats decide no verdict and are not hashed. `spec/ir.lock.json` records `(version, digest)` per
reviewed control, written by `tools/lock_spec.py` and never by hand. `tools/validate_spec.py` fails a
rule whose content moved under an unchanged version, or whose version went backwards. The lock tool
refuses to record such an edit, and the suite fails on a lock that is not current. A bump the lock
has not recorded yet passes validation and is reported as *not yet locked*.

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
    def events() -> tuple[str, ...]                  # canonical events this PMS publishes
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
response into the fixture set with its request fingerprint.

**No test can switch it on, and that needs two locks rather than one.** An environment variable
alone is a lock whose key is one line of `monkeypatch.setenv` away, so the transport also refuses to
arm while a test runner is loaded in the process — and the test that matters sets the variable and
is refused anyway. Exactly one file in the engine imports an outbound HTTP client.

The transport knows how to wait, how to retry, how to give up and how to write a response down. It
knows nothing about any PMS: the request-to-HTTP encoding is the ADAPTER's, handed in as a callable,
and the credential variable names are built from a provider name that arrives as data. So
`providers/transport/` is policed by the canonical-boundary grep exactly as the evaluator is. A
provider may honestly have no encoder at all — DemoPMS has none, because nobody has ever called it,
and it can be replayed but not probed.

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
        verdicts, counts, coverage, blocked,
        policy_version, policy_digest }        # slice 16: the rule that judged it
readiness(control_id, provider)          -> Readiness   # fields resolvable / total, per source
next_evaluation(ir, provider_events, clock, last_run_at, event_at) -> Plan
freshness_of(maximum_age, observed_at, now)                        -> Freshness
store.save(run) / store.load(run_id, *, tenant_id) / store.history(control_id, *, tenant_id)

# slice 18 - the findings queue. ABOVE the runner: a run does not create actions
actions.findings_from(run, ir)                         -> Findings   # pure; only a FAIL raises
store.record_findings(findings)                        -> int        # how many tasks are NEW
store.actions(*, tenant_id) / store.action(action_id, *, tenant_id)
store.transition(action_id, state, *, tenant_id, at, actor)          # pending -> done | dismissed
```

Hides: orchestrating four layers · labelling which body of evidence a run used and whether it is
real · **the coverage verdict** · turning any layer's refusal into a stated reason rather than a
stack trace · SQLite persistence.

**The coverage verdict is new and is a first-class part of a Run.** `evaluated = PASS + FAIL`. A run
with `evaluated == 0` is rendered as *"this control reached no conclusion about any record"* with the
dominant reason — never as four tiles containing a reassuring zero. v1 reported 28 EXCLUDED / 0 FAIL
for an out-of-service-room control on a property where the mechanism had never been observed
working, and it was indistinguishable on screen from a clean result.

**A run names the rule that judged it** (slice 16). `policy_version` and `policy_digest` are read
from the IR the run actually loaded, so a rule edited without its bump is visible on the run even
when its version is not. The store keeps both in two nullable columns added by `_migrate`. **A run
stored before slice 16 reads back with neither, and every surface says *version not recorded***.
It never borrows today's version: the freshness rule, applied to identity. `make_run_id` is
unchanged (plan-v3 §6.6). The same question at the same instant keeps one identity, so in the demo,
whose clock is fixed at the capture's instant, re-running after a version bump replaces that row.
The replacement carries the new rule's verdicts and the new rule's version together.

**Every read names its property** (slice 17, G5's data half). `tenant_id` is keyword-only with no
default, so a call without one is a `TypeError` where it is written, never a query that returns
every hotel's runs. Another property's run reads as `None`, exactly like a run that never existed,
and the web layer answers both with the same 404 word for word. A run id cannot be probed for
existence. `verdicts` and `evidence` carry no property of their own and are scoped through their
run. A save is an upsert whose update half fires only for the same property, so a run carrying
another property's id is refused rather than replacing that property's verdicts.

**A failed control becomes one task, once** (slice 18; G2(a), G8's queue, G10c). The layer
above the run - the web layer's `_execute` - saves a run, asks `actions.findings_from` what it
raises, and hands that to the store. `runner/` is untouched. Severity and audience are the IR's
own `action` block, read for the first time; an IR naming no audience gets a task for no
audience. **Only a FAIL raises a task**: UNKNOWN does not, because whether it should is open
question 1.1, and nor do EXCLUDED, a run that concluded nothing, or a blocked run. Only a
**reviewed** control raises one; a draft's `action` block was borrowed with its population, so
nobody decided its severity. **Idempotency is the task's natural key** - property, control,
policy version, record - so a control run five times raises one task, a new version of the rule
raises a new one while the old stays linked to its version, and `make_run_id` is unchanged.
**Only a person moves a task**: `pending -> done | dismissed`, stamped through an injected clock
with an actor (`operator` until slice 24). A later run updates the task's receipt (the newest
run still finding it failing) or annotates it (*no longer failing as of run X*); it never
closes it. The `actions` table is tenant-owned under slice 17's structural guard, discovered
from `schema.sql`.

**Scheduling is a pure function.** `next_evaluation` reads the IR's `execution`, asks the provider
what events it publishes, and returns a `Plan`: a subscription, a due time, or `unschedulable`. A
daemon is out of scope; the decision is not, and it is fully testable with an injected clock.

A control whose events a provider does not publish falls back to its declared interval and the plan
**names the missing event**. With no fallback it is `unschedulable` rather than given a plausible
interval — there is no honest default, and inventing one produces a control that merely appears to
be running. That is the scheduling form of turning an UNKNOWN into a PASS.

**Freshness is the same rule applied to time.** A `Run` records when its evidence was OBTAINED, as
distinct from what date it describes, and `freshness_of` compares that against the IR's
`maximum_age`. Evidence whose age cannot be established is stale, never assumed current — and a
stale run still shows every verdict, because staleness qualifies an answer rather than removing it.

### L7 · Web

```
GET  /?property=&evidence=            the controls the spec defines, with readiness
GET  /run/<control_id>?property=&evidence=&as_of=   run it and render every verdict
GET  /api/run/<control_id>            the same run as JSON
GET  /api/runs/<run_id>?property=     a stored run, re-read without a provider call - for ITS property
GET  /history/<control_id>?property=  one property's past runs, newest first, grouped by rule
GET  /api/readiness/<control_id>      per-provider field availability
GET  /api/controls                    every reviewed control with its readiness, in one request
GET  /api/properties                  each property, its provider, its captures, and the default
GET  /api/history/<control_id>?property=   one property's past runs as JSON, naming the property
GET  /api/drafts?property=            one property's composed drafts, flagged unreviewed
GET  /api/outcomes                    the four answers' badges and meanings, served once
GET  /api/plan/<control_id>?property=&as_of=   when it runs next (F7), for a stored run
GET  /api/compose                     whether compose is wired, and a conversation's transcript
POST /api/compose                     one turn, as JSON - the same core as POST /compose
POST /api/compose/accept              file a draft (201) or say why not (422); does not run it
GET  /queue?property=                one property's findings queue, and what each control last concluded
GET  /api/actions?property=           the same as JSON: tasks, persistence, each control's coverage
GET  /api/actions/<action_id>?property=   one task, for ITS property; another's is the same 404
POST /api/actions/<action_id>         state=done|dismissed - a person moves a task. Our store only
POST /queue/<action_id>               the same from the page's buttons, then 303 back to the queue
GET  /style.css                       served from the package, never from a CDN
GET  /compose                         the compose window, or a page saying it is switched off
POST /compose                         one turn: prose in, a sentence or a question out
POST /compose/accept                  compile the sentence in the box, file a draft, run it
```

**`as_of` defaults to the instant the evidence describes**, not to today. Each capture declares
which moment it is a picture of, and asking it about that moment is the only honest default - a
capture of July answers questions about July, and asking today's date instead would produce a
page of refusals for a reason that has nothing to do with the controls. The page always states
which instant it asked about, and `?as_of=` overrides it. A date the engine cannot read is
refused rather than guessed at.

`handle(path)` stays a pure function of the path. The two routes that write get a second entry
point, `handle_post(path, body)`, so that signature and everything asserted about it stay true.
Nothing here writes to a PMS — what a POST writes is our own `spec/drafts/` and our own run store,
which since slice 18 includes the findings queue.

Server-side rendering, no JavaScript. The demo's single job is to show that a verdict traces to the
fields that produced it, and a page that assembles itself from an API call is a page a browser, a
CSP or a `file://` open can break.

**Since slice 15 there are two surfaces, and this one stays.** A Next.js UI under `ui/` is a second
*client* of the `/api/` routes above. It lives outside `hotelcontrols/` for the same reason
`tools/proposers/` does: the engine stays standard-library only (criterion 11) and can be shipped,
audited or demoed with `ui/` deleted. The read-only routes added for it cost no provider call. The
compose routes are its one write path, signed off by the owner. They share one core with the HTML
window, and they write only `spec/drafts/` and the run store, never a PMS. Their payloads are pinned as golden files in `fixtures/api/`, generated by
`tools/dump_api_fixtures.py` and never edited, so a change here that alters the contract fails as a
stale rebuild instead of breaking the UI later. Three properties of this API are traps for any
client:

- **`coverage.concluded` gates the tiles, not the presence of `counts`.** A run that concluded
  nothing still carries its counts.
- **Money is a string carrying its currency (R9).** A client renders it as it is and never parses
  it.
- **`GET /api/run/` spends provider calls and writes a row.** A client fetches a run once, on
  purpose, and re-reads it from `/api/runs/<run_id>`.
- **`policy_version` and `policy_digest` are null on a run stored before slice 16.** That means
  *version not recorded*. A client never fills it in with the current version.
- **A stored run, a history and the drafts are read for a property** (slice 17). A link to
  `/api/runs/<id>` carries `?property=`. Without it the engine selects its default property, and
  another property's run is a 404. Until slice 24 `?property=` is a *selection*, not an
  identity. What slice 17 guarantees is that the selection is honoured all the way down.
- **Drafts are per property**: filed under `<drafts>/<property>/ir/`, listed and run only for that
  property. Reviewed controls in `spec/ir/` stay one shared library by design.
- **An empty findings queue is not an all-clear** (slice 18). `records: []` says nothing by
  itself: `controls` says, per control, whether its latest run was `not_run`, `blocked`,
  reached `no_conclusion`, or `concluded`, with the engine's `label` and `headline`. A client
  renders those beside the tasks. `persistent: false` means the queue is lost on restart, and
  `persistence` says so in the engine's words. The demo's store is in memory unless the server
  is started with `--store PATH`.

UNKNOWN is distinguished from FAIL by **hue, border style and wording** — three signals, so the
distinction survives a monochrome screen or a colour-blind reader.

### L0 · Compiler

```python
compile(sentence, registry, deployment=None, tenant=None) -> Compilation
Compilation = { ir | None, problems: [Problem], confidence, ambiguities, logic }
```

Three front ends behind one gate:

- **`GrammarCompiler`** — a restricted-English parser. Deterministic, offline, no model. This is
  what CI runs and what the tests assert against.
- **`normalise(prose, proposer, ...)`** — decision D10, slice 13. Takes an **injected**
  `SentenceProposer` that rewrites prose into restricted English, then hands that sentence to the
  grammar above. The intermediate is a sentence a person reads and edits, so nothing new decides
  what a rule means: a composed control still carries `confidence == 1.0` and `source ==
  "grammar"`, because the parse was exact whatever drafted the text.
- **`ModelCompiler`** — an optional adapter that asks a language model for an IR directly. It is not
  trusted: its output goes through `ir.validate` unchanged. Decision D9: built, exercised against a
  stub, no model wired.

**None of the three finds a model, holds a key, or makes a request.** A proposer is always handed
in, and every backend lives in `tools/proposers/`, outside the engine — which is what keeps
criterion 11 true for `hotelcontrols/` and keeps both AST guards passing unchanged. A live backend
sits behind the same two locks as the transport: an environment variable, **and** a refusal to arm
while a test runner is loaded.

**The sentence is the rule; it is not the deployment.** An IR carries a
`population.provider_query` — an endpoint and its filters, per provider — and a sentence that could
name one would be a sentence that breaks criterion 5. So the document is split: the SENTENCE owns
entity, references, scope, exceptions, the assertion and therefore the evidence; the DEPLOYMENT
owns the bounded query, the trigger, the freshness requirement and the action, and arrives as data.
The split is enforced both ways — a deployment carrying a `scope` clause is refused, because then
the sentence printed beside a verdict would be a partial account of the rule that produced it.

**`confidence` is reported, never acted on.** A deterministic parse is `1.0` because the parse is
exact rather than probable. A model's proposal is `None`: nothing here established a number, and a
model's opinion of itself is not evidence. No acceptance decision reads the field.

**Neither may emit anything executable.** §17 of the requirements doc is explicit about why, and the
gate that makes it safe already works: fed the doc's own example — *"All VIP arrivals should have an
assigned room that is clean by 2 PM"* — v1's validator answered with the two canonical fields that
do not exist rather than producing a rule that runs and quietly answers about nothing.

---

## 4. Layout

```
hotelcontrols/
  kernel/         value.py · money.py · outcome.py · verdict.py · clock.py · errors.py
  spec/           registry.py · ir.py · lock.py · tenant.py · schema.py
  providers/      base.py · registry.py
                  minihotel/  adapter.py · paths.py · transforms.py · records.py · fixtures.py
                  demopms/    adapter.py · paths.py · records.py · transforms.py · fixtures.py
                  transport/  http.py · ratelimit.py · record.py     # opt-in, off by default
  evidence/       gather.py · population.py · reference.py · cache.py · budget.py
  evaluator/      record.py · population.py · predicates.py · intervals.py · logic.py
  runner/         run.py · coverage.py · readiness.py · scheduling.py
  actions/        records.py                  # slice 18: a FAIL -> one task. Pure
  store/          sqlite.py · schema.sql      # runs, verdicts, evidence, actions
  web/            app.py · render.py · server.py · assets/
  compiler/       grammar.py · sentences.py · model.py · problems.py
spec/             canonical_fields.json · ir_schema.json · ir/*.json
                  ir.lock.json            # version + digest per control - GENERATED
                  drafts/ir/*.json        # composed from prose, runnable, UNREVIEWED
                  providers/minihotel.json · providers/demopms.json
                  tenants/*.json
fixtures/         minihotel/  (pseudonymised captures + request fingerprints)
                  demopms/    (fictional, by construction)
                  api/        (the JSON API's own answers - GENERATED, the React UI's contract)
tests/            unit/ · integration/ · e2e/ · contract/
docs/             every markdown document
tools/            validate_spec.py · lock_spec.py · scrub_fixtures.py · transcode_demopms.py
                  probe.py
                  serve.py                # the demo WITH the compose front end wired
                  proposers/  base.py · local.py · anthropic_api.py · stub.py
                              # every model client. OUTSIDE the engine, injected in.
                  dump_api_fixtures.py    # writes fixtures/api/ from the live API
ui/               Next.js + React + TypeScript. A CLIENT of the JSON API, never imported by
                  the engine. app/ · components/ · lib/api.ts (the only module that calls the
                  engine) · proxy.ts (nonce CSP) · test/ (Vitest) · e2e/ (Playwright)
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
| **Locks** | Can a test reach the network, or a model? | Asserted negatively: the transport and every proposer refuse inside a test process **with their variable set** |
| **End to end** | Does a run produce the right verdicts with their evidence? | Full stack, frozen source |

The **contract suite** is the piece v1 did not have and the one that makes criterion 7 real: a single
set of tests parameterised over every registered provider, so adding Mews means running an existing
suite rather than writing a new one. `providers/registry.py` discovers adapters by importing the
sub-packages that declare themselves, so no module above an adapter names a PMS — a dictionary of
`{"somepms": SomePmsAdapter}` would be the first place the boundary leaked.

**The two fixture sets describe one hotel.** `fixtures/demopms/` is generated from the MiniHotel
captures by `tools/transcode_demopms.py`, field by field, gaps included — so "the same hotel through
two providers" is checked rather than asserted. A hand-written second fixture set would drift towards
whatever answers looked best, which is exactly what v1's `fixtures/synthetic/` did.

**The compose front end is tested against a stub and nothing else.** `tools/proposers/stub.py` is a
dictionary of fixed replies chosen to reach each outcome — a sentence that compiles, one naming an
undeclared field, one carrying a population word, one that asks a policy question, and one that
raises. A stub exercises the validator harder than a real model would, because a real model mostly
emits plausible sentences. No test reaches a model; both live backends refuse to arm while a test
runner is loaded, and the test that sets their environment variable is refused anyway.

**The second surface is tested from the engine's own answers.** `tools/dump_api_fixtures.py` writes
the JSON API's response for every control × property × capture, plus history, readiness and the
compose window's states, to `fixtures/api/`. The engine's suite asserts the rebuild is
byte-identical, and pins the shapes the UI depends on: above all, that a run which concluded nothing
still carries `counts`, so `coverage.concluded` has to be the gate. The UI's own suite renders from
those files, with no engine process and no socket, and it can never trigger a run. It has three
layers:

| Layer | Question | Runs against |
| --- | --- | --- |
| **Components** (Vitest) | Do criteria 2, 3, 8 and 10 hold on this screen too? Is the wording different with all styling stripped? | Golden payloads, in jsdom |
| **Parity** (Vitest) | Is any record dropped, duplicated or mis-grouped? Is every evidence row verbatim? Are there tiles if and only if the run concluded? | All 88 run payloads, live and stored |
| **Real browser** (Playwright) | Are the four computed border styles four different values? Is every disclosure reachable by keyboard? Does axe pass? | Components rendered to HTML and loaded with `setContent`. No server |

The UI's CI job is separate and not required, so a broken npm can never block an engine fix. The
rules that matter most about `ui/` are therefore checked by the **required** Python suite as well:
no parsed money, no PMS identifier, no injected HTML, one module that makes requests, and exact
pins (`test_ui_hygiene.py`, `test_canonical_boundary.py`).

**v3 adds a structural tenant guard** (slice 17). `tests/unit/test_tenant_scoped_store.py` reads
every SQL literal in `store/`, and every statement SQLite executes through each public method. It
fails one that reads, updates or deletes a tenant-owned table without a bound `tenant_id = ?`
after its `WHERE`. The tables come from `schema.sql`, so a table v3 adds later is covered the day
it is created. It was seen failing on a planted unscoped `SELECT` before it was relied on, and
again on slice 18's `actions` table: a planted `SELECT * FROM actions WHERE action_id = ?` failed
both the literal scan and the traced execution before it was removed.

**v3 adds two guards that run on every push.** `tests/unit/test_v3_slice_scope.py` holds each v3
slice's *may change* line from `docs/plan-v3.md` §5 as an allow-list. It fails a `slice/16-*` …
`slice/24-*` branch that touches anything else, and it refuses an edited file where a slice promised
new files only. `tests/integration/test_v1_no_answer_changed.py` compares the verdicts, counts and
coverage of all 88 run goldens with `7f384c4`, the commit v3 was planned on (criterion V1).

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
- **A rule-editing UI.** Sentences arrive through the compiler; IRs arrive as files. The slice-13
  compose window (on both surfaces since slice 15) is a chat box over `normalise`, not an editor: it files **drafts** into
  `spec/drafts/`, and promoting one into `spec/ir/` is a deliberate manual step.
- **A model anywhere near a verdict.** D10 puts one in front of the *compiler*. The evidence layer
  and the evaluator never learn it exists.

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
