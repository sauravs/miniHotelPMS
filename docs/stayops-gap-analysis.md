# StayOps — gap analysis

**What the three StayOps design documents require, against what this repository actually implements.**
Reconnaissance and measurement date: **2026-09-28**, on `main` at `5d5143c`.

> **Why this document quotes so much.** The three source documents live in a directory that is
> git-ignored, so a reader of this repository cannot open them. This report is therefore the only
> committed record of those requirements, and it quotes and paraphrases generously rather than
> pointing at section numbers nobody can follow.
>
> The three sources, all supplied by the project owner's manager:
>
> | | Document | Version |
> | --- | --- | --- |
> | **D1** | StayOps Controls & Guest Services — Product, Architecture & Implementation Design | 1.0 |
> | **D2** | StayOps Controls & Guest Services — Technical Design & Coding Specification | 1.1 |
> | **D3** | StayOps Controls & Guest Services — Developer Implementation Package | 1.0 |
>
> Section references below are written `D1 §12`, and are section numbers within those documents.
> The business-language account of what they *ask for* is `docs/stayOps_Cotrols_Rule_Engine_V2.md`;
> this document is the comparison and nothing else.

**Everything measured here was measured, not recalled.** `pytest` → 1610 passed, 1 skipped in 9.6s.
`tools.validate_spec` → 1080 checks passed. 61 Python files, 9,732 lines under `hotelcontrols/`.
11 control IRs in `spec/ir/`, 53 canonical fields, 2 providers. Where a claim rests on reading rather
than running, it says **UNVERIFIED**.

---

## 1. Executive summary

**The honest headline: we have built one of the two described capabilities, and built it deeper than
described — but we have built almost none of the platform that was supposed to hold it.**

The cleanest way to see this is through D1 §12's own six architectural layers:

| D1 §12 layer | State | One-line reason |
| --- | --- | --- |
| **L1 Experience** — admin UI, guest interface | **partial** | Results and evidence render well; no admin, no create-control form, no guest-facing anything |
| **L2 Policy** — templates, policies, versions, compilation, validation | **partial** | Compilation and validation are strong; templates-with-parameters, versions and lifecycle are absent |
| **L3 Evidence** — canonical fields, mappings, retrieval, provenance | **complete, and ahead** | Plus a bounded call budget and asserted cost the documents never asked for |
| **L4 Provider** — adapters, auth, normalisation | **complete, and ahead** | Two adapters passing one shared contract suite; not Mews |
| **L5 Evaluation** — deterministic evaluation, PASS/FAIL/UNKNOWN | **complete and ahead for controls; absent for guest services** | Four outcomes not three, Kleene logic, aggregates across records |
| **L6 Execution** — scheduling, events, actions, notifications | **mostly absent** | The scheduling *decision* is a tested pure function; nothing runs it, and nothing acts on a result |

Three statements, each defensible from something run or read:

1. **Hotel Controls is real and exceeds its specification in five specific ways** (§5). Eleven
   controls where five were asked for, a fourth outcome the documents lack, money that carries its
   currency and refuses to compare across currencies, a call cost asserted rather than hoped for, and
   a canonical boundary enforced by a test rather than by discipline.

2. **Guest Service Rules — the second of the two co-equal capabilities — does not exist at all.**
   Not partially. Searching the engine, the spec directory and the whole test suite for
   `late_checkout`, `intent`, `APPROVED_WITH_FEE` or `staff_review` returns **zero matches**. Half the
   product, by the documents' own framing, is absent, and D3 §86's Definition of Done cannot be met
   without it.

3. **The single biggest structural absence is multi-tenancy as a security boundary** — and it is
   easy to mis-score, because this repository already contains files called *tenants*. Those describe
   one hotel's **vocabulary and policy** (status codes, timezone, call budget). What the documents
   mean by tenant is an **isolation boundary** between paying customers who must never see each
   other's data. We have the configuration sense and none of the isolation sense. It is verified
   concretely below, twice: the property is chosen by a URL query parameter with no authentication,
   and the run store carries a `tenant_id` column that **no query ever filters on**.

**A rough measure, offered with its method rather than as a fact.** Of 14 requirement areas in §3's
matrix: 4 are present and ahead of spec, 5 are partial, 5 are absent. Weighting by the documents'
own emphasis, somewhere around a third of the described product exists. **What matters more than the
fraction is its shape: nearly everything missing sits *above* the canonical boundary.** The layers
that were hard to get right — evidence, normalisation, deterministic evaluation — are done, and the
missing work is the platform wrapped around them. That is a much better position than the fraction
suggests, and §6's roadmap is built on it.

**And one thing that is not a gap but a decision, which is the highest-value question in this
report:** Guest Service Rules imply *doing* things — applying a $25 charge, creating a service
request, raising a maintenance ticket. This engine cannot write to a PMS by design, by PRD §6, and by
a test that refuses to arm an HTTP client even with its environment variable set. Whether guest
services stays **advisory** or **crosses that boundary** is a product decision that changes the
architecture, and nobody should assume either answer. It is gap **G2** and it gates roughly half the
roadmap.

---

## 2. The risk metric

Every missed requirement below carries four scores and one derived number.

| Score | 1 | 3 | 5 |
| --- | --- | --- | --- |
| **Impact** — what breaks, or cannot be sold, without it | cosmetic | a named requirement unmet | the product cannot be sold or the Definition of Done cannot be met |
| **Effort** — S/M/L/XL | a `spec/` data change | a new module | an architectural reversal |
| **Blast radius** — how many of the eight architecture layers it disturbs | one layer, additive | three layers | crosses the canonical boundary or the read-only rule |
| **Evidence risk** — does the PMS data to support it demonstrably exist | captured and observed populated | mapped but unverified since the system changed | no captured response can support it |

```
EXPOSURE  =  Impact  ×  max(blast radius, evidence risk)
```

**Why that formula, and why effort is not in it.** Exposure is meant to rank *danger*, and effort is
a cost, not a danger. Multiply effort in and a cheap catastrophe ranks below an expensive
inconvenience — precisely backwards for deciding what to worry about. So effort is reported in every
row and used only to sequence the roadmap.

**Why `max` and not a sum of blast radius and evidence risk.** They are alternative routes to the
same outcome — a requirement is dangerous if it wrecks the architecture *or* if no data can support
it, and a requirement that does both is not twice as dangerous, it is dangerous once for whichever
reason is worse. Summing would also double-count the several rows where an architectural reversal is
being contemplated *because* the evidence is thin.

Scores range 1–25. **Every row must be defensible from something read or run; a row whose evidence is
thin is marked UNVERIFIED rather than guessed at.** That habit is this project's whole personality,
and a gap report that manufactured confidence would be the wrong artifact for this codebase.

---

## 3. Capability matrix

`present` · `partial` · `absent`. Evidence for each claim is in the right-hand column and expanded in §4.

### A · The two product capabilities

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Hotel Controls — hotel states a rule, system finds violations | D1 §2.1, D2 §1A | **present** | 11 IRs run end to end; 5 reach PASS/FAIL on captured evidence, 6 name their blocker |
| Guest Service Rules — guest asks, system decides | D1 §2.2, D2 §16–26, D3 §27 | **absent** | grep for `late_checkout`/`intent`/`APPROVED_WITH_FEE`/`staff_review` across `hotelcontrols/`, `spec/`, `tests/` → 0 hits |
| One shared policy engine serving both | D2 §2, §27, D3 §25 | **partial** | The condition evaluator is a superset of D2 §27's operator list; nothing calls it from a request path |

### B · Policy and natural language

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Natural language → supported template + parameters | D1 §22–23, D3 §38–40 | **partial** | NL → restricted English → full IR. Correct in spirit; not template-plus-parameters shaped. See G6 |
| Global template library, tenant-specific parameters | D1 §8–9, §36, D3 §26–27 | **partial** | Tenant `settings` exist and the grammar reads them (`one of setting nominated_rate_codes`), but only 2 settings and no parameter schema |
| Never LLM → executable | D1 §23, §57, D3 §41, §52 | **present, stronger** | The model emits a *sentence*, not IR; backends live outside the engine and are AST-asserted |
| `COMPILED` / `NEEDS_CLARIFICATION` / `UNSUPPORTED` | D3 §40, §82–83 | **present** | Compose returns a question with no run button; undeclared vocabulary refused by name |
| Show the compiled policy before activation | D3 §67–68 | **partial** | The restricted sentence is shown and editable; there is no activation step to gate |
| Policy versioning, decisions tied to their version | D1 §38, §66, D3 §43–44, §59 | **absent** | IRs carry a `version` field **no loader reads**; `Run` has no version field; `runs` table has no version column |
| Lifecycle DRAFT→VALIDATING→READY→ACTIVE→PAUSED→ARCHIVED | D1 §25 | **absent** | Two states only, expressed as a directory: `spec/drafts/ir/` vs `spec/ir/` |
| Four-stage validation: syntax, template, evidence, provider | D3 §45 | **partial** | Validator + per-provider readiness both exist; no gate refuses activation (there is no activation) |
| Policy not activatable without evidence | D1 §54, D3 §46 | **absent** | Readiness is computed and displayed; it blocks nothing |

### C · Canonical model

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Reservation, Room, Room Category | D2 §6, §8, D3 §8, §10 | **present** | 22 + 9 + 2 canonical fields |
| Guest as its own entity with a `guest_id` | D2 §7, D3 §9 | **partial** | Guest fields are inlined on the reservation (`reservation.guest.phone`); no guest entity, no guest id |
| Payment | D2 §6, D3 §12 | **partial** | Present as `folio.*` (8 fields) including transactions; no `Payment` object |
| Availability, Rate | D1 §18, D2 §33, D3 §21 | **absent** | No availability entity. `rate_plan.*` exists and is flagged `resolvable: false` (R13) |
| `reservation.payment_guarantee_status` | D2 §9, D3 §11 | **absent** | Only `reservation.guest.payment_card_present` (masked → presence only). See G4 |
| `reservation.complimentary` | D2 §10, D3 §28 | **absent** | No mapping; no captured field |
| `guest.vip_status` | D2 §33, D3 §9 | **absent** | Exists in live data only as Hebrew free text in a remarks field (open question 1.5) |
| `reservation.company_id` | D2 §6, D3 §8 | **absent** | No company or corporate-account entity anywhere in the API (structurally blocked) |
| Money carries its currency | D3 §8 | **present, stronger** | `Decimal` + currency; cross-currency comparison **raises**. D2 §6 specifies a bare float — see §5.2 |
| Canonical enumerations | D2 §9, D3 §11 | **partial, divergent** | We lack `TENTATIVE`, add `waitlist`; and we admit an unnameable status where the docs' enum cannot. See §5.5 |
| Stable StayOps ids + `provider_entity_mappings` | D2 §35, D3 §19 | **absent** | Records are keyed by provider-native ids throughout |

### D · Evidence layer

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Evidence registry of requestable canonical fields | D1 §19–20, D3 §20–22 | **present** | `spec/canonical_fields.json`, 53 fields, validated on load |
| Provider mappings as data, developer-managed | D2 §37, D3 §77 | **present** | `spec/providers/*.json`; every mapping's regex asserted against its probe file |
| Provenance on every value | D1 §21, D2 §39, D3 §23, §60 | **present, stronger** | A `Verdict` **cannot be constructed** without evidence; provenance survives a store round trip |
| Unmapped provider value → UNKNOWN, logged | D2 §38, D3 §18 | **present** | Three unmapped statuses declared per tenant so the gap is a decision, not an oversight |
| Population resolver — only the affected entities | D1 §29, D3 §48 | **present, stronger** | Plus a call budget that **raises rather than truncating**, cost asserted at `1 + R + N` |
| Evidence freshness | D3 §22 | **present, stronger** | Declared *and computed*; evidence whose age cannot be established is stale, never assumed fresh |

### E · Provider layer

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| One adapter interface, all PMSs behind it | D2 §36, D3 §12–13 | **present, different shape** | A field-resolution protocol (`resolve(field, record)`) rather than `getReservations()`/`getRooms()`. See G7 |
| Normalisation into canonical values | D1 §16–17, D3 §16–17 | **present** | Structured parsing, not regex over raw text |
| Nothing above normalisation knows the PMS | D3 §87 ("most important rule") | **present, stronger** | A grep test over the tree, 28 identifiers from **both** providers, allowed dirs discovered not listed |
| MiniHotel adapter | D1 §56, D3 §84 Phase 3 | **present** | Real captures, 6 endpoints, verified 2026-09-01/04 |
| Mews adapter | D1 header, §14; D3 §78 | **absent** | No credentials exist. DemoPMS (JSON, fictional) stands in and proves the seam |
| Provider capabilities declaration | D3 §14 | **partial, finer** | Readiness is per control × provider at **field** level, not a boolean map per endpoint |
| Rate limiting, retry, backoff, timeouts | D1 §64 | **present** | Opt-in transport with token-bucket limiter and bounded retry; off by default, two locks |
| Limits applied per tenant + provider | D1 §64 | **absent** | Limiter is per process; credentials are keyed by provider alone (open question 1.9) |
| Mapping versioning | D1 §51 | **partial** | Provider maps carry a `version` and a `verified_against` date; git is the history. No mapping-version resolution at runtime |

### F · Evaluation

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Deterministic evaluation, no model in the path | D1 §24, §71 Rule 4, D3 §52 | **present** | The evaluator is a pure function of (IR, evidence); asserted by test |
| PASS / FAIL / UNKNOWN | D1 §27, D2 §1A, D3 §50 | **present, stronger** | Plus **EXCLUDED** and a coverage verdict. See §5.1 |
| UNKNOWN must never become FAIL | D1 §27 | **present** | The rule that outranks every other in `CLAUDE.md` |
| Common condition evaluator, 10 operators | D2 §27 | **present, superset** | All ten, plus `matches_ignore_case`, `count_lte`, `no_overlap`, `within`, `overlaps` |
| Guest decisions + fee calculation | D2 §24, §30, D3 §51, §53 | **absent** | No decision type, no fee arithmetic |

### G · Execution

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Manual execution | D3 §55 | **present** | `GET /run/<control_id>` and the JSON API |
| EVENT / HOURLY / DAILY scheduling | D1 §28, D3 §55 | **partial** | `next_evaluation()` is a tested pure function returning subscription, due-time or `unschedulable`. **Nothing runs it** |
| Event ingestion / webhooks | D1 §28 | **absent** | IRs declare their events; providers declare what they publish; nothing subscribes |
| Job queue and workers | D1 §42, §63, D3 §58 | **absent** | No queue, no worker, no async anything |
| Idempotency keys | D1 §65, D3 §57 | **absent** | `make_run_id` hashes `created_at` in, so it is a content hash, not an idempotency key: a retried job produces a second run |
| Result storage with tenant and policy version | D3 §59 | **partial** | `tenant_id` stored (never filtered on); no `policy_version` column at all |
| Evidence storage with provenance | D3 §60 | **present** | Value, unit, known-ness, reason, risk id and source all round-trip |

### H · Multi-tenant SaaS platform

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| `tenant_id` on every tenant-owned record | D1 §46, D3 §5 | **partial — label only** | `runs.tenant_id` exists; `history()` filters by `control_id`, `load()` by `run_id`. **No query filters by tenant** |
| Tenant context established by authentication | D1 §6, §45, D3 §6 | **absent** | The property comes from `?property=` in the URL, unauthenticated — exactly what D1 §45 forbids |
| Authentication | D1 §6, D3 §73 | **absent** | `web/server.py` states it: "This demo has no authentication" |
| Role model (ADMIN / MANAGER / STAFF) | D3 §74 | **absent** | No user concept at all |
| Tenant-aware repositories enforcing the filter | D3 §7 | **absent** | `RunStore` methods take no tenant context |
| Cross-tenant isolation tests ("mandatory") | D1 §62, D3 §80 | **absent** | Nothing to test; no boundary exists to attack |
| Encrypted per-tenant PMS credentials | D1 §14, §43, D3 §15 | **absent** | Environment variables keyed by **provider**, so two properties on one PMS cannot hold distinct credentials |
| Organisation → hotel hierarchy | D1 §5, §48 | **absent** | Explicitly deferred by the documents too — not a gap today |

### I · Actions and notifications

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Action model | D1 §34, D2 §26, D3 §71 | **declared, not implemented** | Every IR carries `action: {type, severity, audience}`. **Nothing in the engine reads it** |
| Email notification on FAIL | D2 §44, D3 §72 | **absent** | No `smtplib`, no notifier, no outbound anything except the opt-in PMS transport |
| Staff review queue | D2 §44, D3 §70 | **absent** | — |
| Create service / maintenance request | D1 §34, D3 §37, §71 | **absent, and conflicted** | Would write to a hotel system. See G2 |

### J · API surface

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Controls: create, validate, activate, pause, execute, results | D1 §45, D3 §61, §64 | **partial** | We have run, stored-run, readiness and history (all GET) + `POST /compose`. No create / validate / activate / pause |
| Guest service policy and request APIs | D1 §45, D3 §62 | **absent** | — |
| PMS connection APIs (connect, test, disconnect) | D3 §63 | **absent** | — |
| Tenant derived from auth, never from the browser | D1 §45, D3 §6 | **absent** | Derived from the browser |

### K · Observability, security, onboarding, UI

| Requirement | Source | State | Evidence |
| --- | --- | --- | --- |
| Structured logs carrying tenant / execution / policy / provider ids | D1 §49, D3 §75 | **absent** | The engine has no logging layer; the run store is the only trace |
| Distinguish policy violation from system failure | D1 §50, D3 §76 | **present** | FAIL vs UNKNOWN vs a blocked run, each rendered differently |
| Never log credentials or unnecessary PII | D1 §49, D3 §73 | **present** | Credentials from environment with no default; fixtures pseudonymised at capture |
| Hotel onboarding flow | D1 §13 | **absent** | Tenants are hand-written JSON files committed to the repo |
| Controls UI: list, results, evidence | D2 §45, D3 §66, §69 | **present** | Server-rendered, no JavaScript, every verdict traces to its fields |
| Create-control UI | D2 §45, D3 §66 | **partial** | The compose window takes prose; there is no template-and-parameters form and no activate button |
| Guest policy UI, guest request UI, staff queue | D2 §46–47, D3 §67, §70 | **absent** | — |

---

## 4. Gap by gap

Each gap: what the documents ask, what exists, why the gap exists — **often a deliberate earlier
decision rather than an oversight** — an analogy where one genuinely clarifies, and the risk row.

---

### G1 · Guest Service Rules — the whole second capability

**Asked for.** D1 §2.2 and D2 §1B make this co-equal with Hotel Controls, not an extension of it.
A hotel writes *"Guests can have late checkout until 2 PM for free. Between 2 PM and 4 PM, charge $25
per hour. Anything after 4 PM requires manager approval."* A guest asks *"Can I check out at 3 PM?"*
The system extracts the intent, finds the reservation, loads the policy, fetches evidence, evaluates
deterministically, and returns a decision — `APPROVED`, `APPROVED_WITH_FEE`, `DENIED`, `STAFF_REVIEW`
or `UNAVAILABLE` — with a fee and any actions. Five templates: `LATE_CHECKOUT`, `EARLY_CHECKIN`,
`ROOM_UPGRADE`, `EXTRA_TOWELS`, `MAINTENANCE_REQUEST`. D2 §49 makes the late-checkout case half of
the project's Definition of Done.

**What exists.** Nothing. This is the one place in this report where "partial" would be generous
rather than accurate: there is no request object, no intent, no decision type, no fee arithmetic, no
policy-per-intent storage, and no route that accepts a guest question.

**Why.** It was never asked for before. Everything in this repository descends from two earlier
documents about *controls* — a twenty-control governance table and an architecture note. Guest
services is new scope arriving with these three documents, not something dropped.

**What is reusable, which is most of the hard part.** The condition evaluator already implements a
superset of D2 §27's operator list. Money already carries its currency, which a `$25/hour` fee needs
and which D2 §6's bare `250.00` would have got wrong. The evidence layer already resolves
`reservation.departure_date` and `room.housekeeping_status` from both providers. What has to be
built is the *request-shaped* path around them: an intent, a policy keyed by intent, a decision type,
and a different evaluator shape — because a control asks "is this record compliant?" over a
population, and a guest rule asks "what should happen?" about one request.

**The honest mapping of our principles onto theirs, which is worth stating.** Guest services has no
UNKNOWN in the documents; D3 §79 maps missing evidence to `STAFF_REVIEW` / `UNAVAILABLE` instead.
That is not a contradiction — **`STAFF_REVIEW` *is* guest services' UNKNOWN.** A guest must get an
answer, and "a person will confirm this" is the honest answer when evidence is missing, exactly as
UNKNOWN is on the controls side. Adopting that reading means the founding principle transfers intact,
and it should be written down as such rather than rediscovered later.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G1 machinery** (request, intent, decision, fee, policy-per-intent) | 5 | 5 (XL — new module) | 3 (additive above L5; no existing layer changes) | 1 (needs no PMS evidence of its own) | **15** |

Per-template evidence risk is scored separately in G3, because it differs sharply between them and
an aggregate would hide that.

---

### G2 · Read-only versus actions — a decision, not a task

**This is the highest-value question in the report.** It is listed as a gap so it cannot be skipped,
but no amount of engineering closes it; one sentence from the project owner does.

**Asked for.** D1 §34: `APPROVED_WITH_FEE` → *calculate charge → create/modify service request →
respond to guest*. D3 §37: a maintenance request is *created*, given a priority, and engineering is
notified. D3 §71's action types include `CREATE_SERVICE_REQUEST` and `CREATE_MAINTENANCE_REQUEST`.

**What exists.** A permanent, deliberate, tested refusal to write anywhere. PRD §6 lists *"Writing to
a PMS. The hotel types controls, not commands. Read-only, permanently."* The engine contains exactly
one file that imports an outbound HTTP client, it is off unless an environment variable is set, and it
**additionally refuses to arm while a test runner is loaded in the process** — the test that sets the
variable is refused anyway.

**The two futures, and they are different products.**

- **(a) Advisory.** StayOps decides and hands staff a task. *"Late checkout until 3 PM: approved,
  $25. Confirm at the desk."* The read-only rule survives untouched, blast radius stays at 3, and the
  product is a decision service. It also degrades honestly: if the charge is never posted, StayOps has
  still been right.
- **(b) Acting.** StayOps posts the charge and creates the request in the hotel's system. This
  **reverses a founding constraint**, and the cost is not the HTTP client — it is that every write
  needs idempotency (D1 §65), rollback thinking, a permissions model for who may authorise a charge,
  and a much harder conversation with each PMS vendor about credentials that can write. Blast radius 5.

**Analogy.** An advisory StayOps is a doctor writing a prescription; an acting StayOps is a doctor who
also dispenses the drug. The second is more useful and needs a fundamentally different licence.

**Recommendation.** Ship (a) first, and design the action layer so that each action is a *record* with
a state — `pending`, `done`, `dismissed` — performed by a human today and, if (b) is ever chosen,
performed by an adapter later without the decision path changing. That keeps (b) available at the cost
of one indirection, and it is the only version of this that does not have to be redone.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G2 (a) advisory** | 4 | 2 | 2 | 1 | **8** |
| **G2 (b) acting** | 5 | 4 | **5** (reverses the read-only rule) | 3 (UNVERIFIED — no write endpoint has ever been called, or read about, or priced) | **25** |

---

### G3 · The five guest-service templates, scored individually

Aggregating these would hide the useful fact: **two of the five need almost no PMS evidence, and one
may not be answerable at all.** That ordering is the whole roadmap for guest services.

| Template | What it needs | Evidence state | Evidence risk |
| --- | --- | --- | --- |
| `EXTRA_TOWELS` | quantity from the request; a maximum from policy | needs nothing from the PMS | **1** |
| `MAINTENANCE_REQUEST` | the guest's room, a category, a priority | room identity is captured and populated; categories are policy | **1** |
| `LATE_CHECKOUT` | `reservation.departure_date`, requested time, the hotel's normal checkout time | departure date is captured and populated. **`hotel.checkout_time` does not exist — there is no `hotel` entity in the canonical vocabulary at all.** One new field, tenant-supplied | **2** |
| `EARLY_CHECKIN` | arrival date, whether the room is ready | `room.housekeeping_status` **is** mapped and observed populated (`getRooms/rm_status`). Room-readiness semantics per property are not established | **3** |
| `ROOM_UPGRADE` | requested category, **availability**, **rate difference** | No availability entity exists. `rate_plan.permitted_room_types` is flagged `resolvable: false`: a reservation's rate code and the price-list code are different key spaces (R13), and the only relevant capture is from 2024 on a system known to have moved on | **5** |

D1 §35 says these five were chosen to prove five *different patterns* — time-based approval; time
plus room availability; availability plus a commercial decision; simple fulfilment; and
classification/routing. That is a good reason to build all five eventually, and no reason at all to
build them in the order listed. **Build `LATE_CHECKOUT` first** (D3 §84 Phase 8 says so too, and it
is half the Definition of Done), then the two that need no evidence, then `EARLY_CHECKIN`, and treat
`ROOM_UPGRADE` as an evidence investigation before it is treated as code.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G3 — the five templates as a set** | 5 | 4 | 2 | 5 (`ROOM_UPGRADE` caps it) | **25** |
| G3a `LATE_CHECKOUT` alone | 5 | 2 | 2 | 2 | **10** |
| G3b `EXTRA_TOWELS` + `MAINTENANCE_REQUEST` | 3 | 2 | 2 | 1 | **6** |
| G3c `EARLY_CHECKIN` | 3 | 2 | 2 | 3 | **9** |
| G3d `ROOM_UPGRADE` | 3 | 3 | 2 | **5** | **15** |

---

### G4 · `PAYMENT_GUARANTEE_BEFORE_ARRIVAL` — the one missing control of the manager's five

**Asked for.** D2 §10 and D3 §28. *"All reservations arriving within 24 hours must have a valid
payment guarantee unless the reservation is complimentary."* Parameters: hours before arrival,
required statuses, a complimentary exception. Required evidence: `reservation.arrival_date`,
`reservation.status`, `reservation.payment_guarantee_status`, `reservation.complimentary`.

**What exists.** Four of the manager's five hotel-control templates are present (one of them split in
two, because two separate business events were hiding in it). This one is not — and the reason is
evidence, not effort.

Of the four fields the template needs, **two do not exist and cannot be made to exist from any
captured response**:

- `reservation.payment_guarantee_status` — the API exposes no *configured guarantee requirement*. What
  it does expose is `reservation.guest.payment_card_present`, which **is** mapped on both providers and
  observed populated — but the card number is masked/tokenised, so **presence can be asserted and
  validity never can.** A card on file is not a guarantee.
- `reservation.complimentary` — no such field, and no exception marker anywhere.

**So the template as specified is not buildable, and a narrower one is.** The honest version is:
*"every reservation arriving within N hours must have a payment card on file"*, which is a real
control a hotel can act on, and which returns UNKNOWN — naming the missing field — wherever the
hotel's actual guarantee policy is what matters. That is this project's standard move, and it is
better than either shipping nothing or shipping a control that calls a masked token a guarantee.

**What would close it fully:** a hotel telling us which rate codes or market segments are
comp/guaranteed as tenant configuration, which is the same shape as open question 1.4. That makes it
a conversation, not a sprint.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G4 as specified** (guarantee status + complimentary) | 4 | 2 | 1 (spec data + one field) | **5** (no captured response can support it) | **20** |
| G4 narrowed (card-present, UNKNOWN elsewhere) | 3 | 1 (a `spec/` change) | 1 | 2 | **6** |

---

### G5 · Multi-tenancy as an isolation boundary

**The single easiest thing in this report to score wrongly, and the reason is a word.**

This repository has `spec/tenants/*.json`. Those files describe **one hotel's vocabulary and policy**
— its status-code map, its posting-category map, its timezone, its call budget, its nominated rate
codes. They exist because MiniHotel lets each property customise its status codes, so those maps
belong to the property rather than to the adapter. That is a real and useful thing, and it is **not
what the documents mean.**

D1 §5–7, §40, §43–47 and D3 §5–7, §73–74, §80 mean tenant as a **security and isolation boundary**:
separate paying customers on shared infrastructure who must never see each other's data. D1 §44 is
explicit — *"a developer should not be able to accidentally write `SELECT * FROM controls` where the
application should have executed `SELECT * FROM controls WHERE tenant_id = current_tenant`"* — and D3
§80 calls cross-tenant isolation tests **mandatory**, to be attempted *"directly through APIs, not
only through the UI."*

**We have the configuration sense and none of the isolation sense.** Verified twice, concretely:

1. **The property is chosen by the browser.** `_selection(query)` reads `?property=` from the URL; if
   it names nothing it silently falls back to the first configured property. There is no
   authentication anywhere — `web/server.py` says so in a comment — so any visitor can run any
   control against any configured property.
2. **The `tenant_id` column is a label, not a filter.** `runs.tenant_id` exists and every run records
   it. But `history()` filters on `control_id` and `load()` on `run_id`, and **no query in
   `store/sqlite.py` mentions `tenant_id` in a `WHERE` clause at all.** The column that D1 §46
   requires is present; the enforcement D1 §44 requires is not.

**Why the gap exists.** Deliberately and on the record: the PRD scopes out *"Authentication and
multi-user access. Single-operator demo."* The engine was built to prove that a PMS-agnostic control
can be evaluated honestly, and a login screen would have proved nothing about that. This is not an
oversight; it is a scope boundary that these three documents move.

**Analogy.** We have built a bank vault with excellent locks on the safety-deposit boxes and no
front door on the building. Both matter, and the order they were built in was not wrong — but the
building cannot open for business.

**Analogy for the naming trap specifically.** Finding the word *tenant* here and concluding
multi-tenancy is half-done is like finding a file named `users.json` holding font preferences and
concluding the app has accounts.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G5** | 5 (cannot be sold as SaaS; D3 §80's mandatory tests cannot exist) | 5 (XL — new layer, plus every store query) | 4 (new layer above L7, store rewrite, credential rekeying; L1–L5 untouched) | 1 (needs no PMS evidence) | **20** |

---

### G6 · Templates with parameters, versions, and a lifecycle

Three requirements that look separate and are one body of work, because each needs the same missing
object: **a policy that is distinct from its parameters.**

**Asked for.**

- **D1 §8–9 and §36** — a *global* template library (`LATE_CHECKOUT`, `ROOM_CAPACITY`, …) with
  *tenant-specific parameters*. Hotel A: free until 2 PM, $25/hour. Hotel B: free until 1 PM,
  $50/hour. Hotel C: everything to staff review. **"The evaluator remains the same. No custom code is
  necessary."** D1 §74 makes the absence of *"customer-specific business logic"* and *"separate code
  branches"* an explicit success criterion.
- **D1 §38, §66 and D3 §43–44, §59** — policies are versioned, and *"existing decisions remain
  associated with the version under which they were made."* Every stored result carries
  `policy_version`.
- **D1 §25** — `DRAFT → VALIDATING → READY → ACTIVE → PAUSED → ARCHIVED`, and *"only validated
  policies can become ACTIVE."* D3 §46: a policy whose evidence is unavailable **must not be
  activatable**.

**What exists.**

- A control is **one IR file** holding its rule *and* its thresholds together. There is a
  parameterisation mechanism — tenant `settings`, which the restricted-English grammar can read
  (`stay.rate_code one of setting nominated_rate_codes`) — but only two settings exist and there is no
  parameter schema, no typed validation of parameters, and no notion of a template that several
  tenants instantiate differently.
- IR files carry a `version` field. **No loader reads it.** `Run` has no version field and the `runs`
  table has no version column. Git is the version history.
- Two lifecycle states, expressed as a directory: `spec/drafts/ir/` (badged unreviewed, excluded from
  the headline figure) and `spec/ir/` (reviewed). There is no activation step, so nothing can gate it.

**What this actually costs today, stated plainly.** If a second hotel wants the same control with a
different threshold, the move available right now is to copy the IR file and edit the number. That is
exactly the *"customer-specific"* duplication D1 §9 and §74 forbid — not because anyone chose it, but
because a single-operator engine with one property never had to distinguish a rule from its settings.
**This is the gap that decides whether the 50th customer is cheap**, and it is worth more than its
exposure score suggests, which is why the roadmap puts it before guest services rather than after.

**On versioning, one piece of credit and one real gap.** A stored run already copies the control's
name and its natural-language text into the run record, so an old verdict displays the rule it was
actually judged by — which is most of what D1 §66 wants from versioning, and stronger than a bare
integer. What is genuinely missing is *identity*: no way to say "these 40 decisions were made under
v1 and these 12 under v2", no version store other than git, and no version on the result row.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G6a template + parameters** | 4 (per-customer duplication; D1 §74 unmet) | 3 (spec shape + compiler + tenant settings) | 3 (L2, L0, and the runner's control loading) | 1 | **12** |
| **G6b policy versioning** | 4 (D1 §66's audit question unanswerable) | 2 | 2 (L2 + store) | 1 | **8** |
| **G6c lifecycle + activation gate** | 3 | 2 | 2 (L2 + L6 + web) | 1 | **6** |

---

### G7 · The provider adapter interface has a different shape

Listed as a gap because a reviewer comparing the two will notice, and **assessed as a divergence to
keep** rather than a shortfall to fix.

**Asked for.** D2 §36 and D3 §12: `getReservations(query)`, `getRooms(query)`, `getGuests(ids)`,
`getPayments(reservationId)`, `getAvailability(query)`, `getCapabilities()` — entity-shaped methods
returning canonical objects.

**What exists.** A field-shaped protocol: `fetch`, `records`, `resolve(field, record)`,
`source_key(field)`, `follow_up(field, record_id)`, `reference_request(entity)`, `events()`.

**Why ours went that way, and it was measured rather than guessed.** Three facts about the real API
drove it:

- **Cost.** A folio takes one call per reservation and there is no bulk endpoint. `getPayments()` per
  reservation hides that; a `follow_up(field, record_id)` seam makes it countable, which is how the
  `1 + R + N` budget is asserted rather than hoped for.
- **Partial knowledge.** A canonical object with 22 fields forces every field to have a value. Half of
  what this API returns is *unknown with a reason* — a status nobody can name, a `0` that means
  "nobody configured this". Field-level resolution lets each field carry its own known-ness and its
  own provenance, which is what makes `Verdict` unconstructible without evidence.
- **Records that are not objects.** Occupancy has no single block in the response; it is assembled by
  a declared join across sibling lists. `getOccupancy()` would have to invent an object the provider
  does not have.

D3 §2 says the architectural requirement matters more than the layout or the language, and D3 §87's
actual rule — *nothing above normalisation knows which PMS the hotel uses* — is satisfied more
strictly here than the entity-method shape would achieve. **No change recommended; recorded so the
difference is a decision on the record.** If a caller ever wants entity methods, they are a thin
convenience over what exists.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G7** (no action recommended) | 1 | 2 | 2 | 1 | **2** |

---

### G8 · The action and notification layer

**Asked for.** D2 §44: FAIL → email or dashboard alert. D1 §34 and D3 §71: a common `Action`
interface with `SEND_EMAIL`, `CREATE_SERVICE_REQUEST`, `CREATE_MAINTENANCE_REQUEST`, `STAFF_REVIEW`,
`GUEST_RESPONSE`. D3 §72 is firm about scope: **email first**, and WhatsApp/SMS/Slack/Teams are not
MVP prerequisites.

**What exists.** Every one of the eleven IRs already declares its action —
`{"type": "notify", "severity": "high", "audience": "finance"}` on the checkout-money control.
**Nothing in the engine reads that block.** There is no notifier, no `smtplib`, no queue, and no
outbound path of any kind except the opt-in PMS transport.

**Why.** The engine's demo surface is a page someone looks at. A control that emails a finance team
needs a scheduler to have run it, which needs G10; sending alerts from a hand-triggered page run
would produce an email every time someone reloaded.

**The consequence, stated plainly: a violation nobody is told about is not a control.** The data
needed to route alerts — severity and audience, per control — has been carried since slice 1. What is
missing is the two hundred lines that read it, and the thing that runs unattended.

**Note the one-way door.** `SEND_EMAIL` and `STAFF_REVIEW` are advisory and cheap.
`CREATE_SERVICE_REQUEST` and `CREATE_MAINTENANCE_REQUEST` are writes into a hotel system and belong to
G2's decision, not to this gap. Build the interface so the first two work and the second two are a
later adapter.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G8 advisory** (email, staff queue) | 4 | 2 | 2 | 1 | **8** |
| G8 acting (creates records in a PMS) | — | — | — | — | *see G2(b)* |

---

### G9 · Mews, the second live PMS

**Asked for.** Named on the front page of all three documents. D3 §78: implement the adapter,
normaliser, mappings, capabilities and contract tests, and *"existing policies should run
unchanged."* Its acceptance test is precise — the same policy against MiniHotel evidence and against
Mews evidence must produce equivalent canonical behaviour.

**What exists.** **That acceptance test already passes — against a different second provider.**
DemoPMS is fictional, speaks JSON, and its quirks were chosen to *disagree* with MiniHotel's on
purpose: one date format carrying a month name against three numeric ones; an out-of-band "unset"
sentinel against an overloaded `0`; money self-describing against money split from its currency;
occupancy nested inside its room against occupancy as sibling lists. Its fixtures are not
hand-written — they are the MiniHotel captures re-encoded field by field, **gaps included**, so the
23 rooms with no configured capacity are still unconfigured and the statuses nobody can name are
still unnameable. A test asserts the rebuild is byte-identical. One shared contract suite runs against
both adapters, and 11 controls × 3 as-of dates produce identical verdicts per record id with identical
call counts.

**So the engineering risk of Mews is genuinely low and its *evidence* risk is maximal.** Nobody has
credentials, and nobody has had them for the life of the project. This is the clearest case in the
report where a small code change carries a large exposure, which is exactly what the evidence-risk
axis exists to surface.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G9** | 4 (a named requirement; the architectural proof the manager asked for) | 3 (a directory, a mapping file, a tenant file) | 1 (the seam exists and is tested) | **5** (no credentials exist; UNVERIFIED against any real Mews response) | **20** |

---

### G10 · Scheduler, queue, workers, idempotency

**Asked for.** D1 §41–42 and §63: a shared scheduler serving all tenants, jobs carrying tenant
context, a job queue, workers, horizontal scaling. D1 §65 and D3 §57: idempotency, so a retried job
does not produce duplicate notifications or duplicate service requests. D3 §55: `EVENT`, `HOURLY`,
`DAILY`, `MANUAL`, and *"manual execution is important for testing and customer confidence."*

**What exists.** `MANUAL`, fully. And the scheduling *decision* as a tested pure function:
`next_evaluation(ir, provider_events, clock, last_run_at, event_at)` returns a subscription, a due
time, or `unschedulable` — and where a provider does not publish the event a control wants, the plan
**names the missing event** rather than quietly substituting a plausible interval. That refusal is
the same principle as UNKNOWN, applied to time.

**What does not exist:** the loop that runs it, any queue, any worker, any event ingestion, and
idempotency. On that last point, one precise correction to an easy assumption: `make_run_id` looks
like an idempotency key but hashes `created_at` into its seed, so it is a content hash including the
instant. **Two deliveries of the same job produce two runs.** Today that is harmless, because nothing
downstream acts on a run. It stops being harmless the moment G8 sends email.

**Why.** On the record as a deliberate engineering gap: *"the decision is the hard part and is
testable. A loop around it is a day's work whenever it is wanted."* Webhook ingestion was separately
deferred as needing a public endpoint, authentication and replay protection — *"a different project"*.

**Analogy.** We have a correct, tested train timetable and no trains.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G10a scheduler daemon** | 3 ("continuously checks" is not true without it) | 2 | 2 | 1 | **6** |
| **G10b queue + workers** | 2 (unneeded below a few hundred properties) | 3 | 3 | 1 | **6** |
| **G10c idempotency keys** | 4 (duplicate alerts, and duplicate charges if G2(b) is ever chosen) | 2 | 2 | 1 | **8** |
| **G10d event ingestion / webhooks** | 3 | 3 | 3 (a public endpoint changes the security posture) | 3 (UNVERIFIED — MiniHotel's webhook payloads have never been observed) | **9** |

---

### G11 · Onboarding and PMS connection management

**Asked for.** D1 §13: create hotel → create admin user → select PMS → connect → **test connection**
→ discover available data → configure policies → validate → activate, and *"the hotel should not need
to understand the underlying integration architecture."* D1 §14 and §43: each hotel's connection is
its own record with encrypted credentials, and *"provider credentials must never be shared between
tenants."* D3 §63: connect / test / disconnect endpoints.

**What exists.** A property is a JSON file written by hand and committed to the repository. There is
no connect flow, no connection test, and no discovery step. Credentials come from the environment
with no default, which is right — but they are keyed by **provider**
(`HOTELCONTROLS_<PROVIDER>_{USER,PASSWORD,HOTEL,BASE_URL}`), and the only caller passes the
provider and discards the tenant id.

**The consequence is specific and already recorded as open question 1.9: two properties on the same
PMS cannot hold distinct credentials — the second would overwrite the first.** That is not a scaling
concern for later; it is the second customer.

**The closest thing we do have** is worth naming, because it is the genuinely hard half of
"discover available data": readiness already reports, per control and per provider, how many required
fields are resolvable and from which source. D1 §13's *discover* step is largely that, wired to a
connection instead of to a fixture.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G11** | 4 (blocks the second customer outright) | 3 | 3 (credential keying, transport, a new module, web) | 1 | **12** |

---

### G12 · Canonical model gaps

The vocabulary is 53 fields across 7 entities and was hardened across eleven controls and two
providers. Against D3 §21's list, four things are genuinely missing and they differ completely in
character.

| Missing | Why | Evidence risk |
| --- | --- | --- |
| **`availability` / inventory** | No canonical entity. The one relevant endpoint is keyed by price-list code rather than rate code (R13) and was last captured in 2024 on a system known to have moved on | **5** — and it gates `ROOM_UPGRADE` |
| **`guest.vip_status`** | The API has no VIP field and market segment is empty on every reservation. VIP status exists in live data **only as Hebrew free text in a remarks field**, alongside — remarkably — the manager's approval: *"VIP policy is met. Approved by the manager on Telegram."* Whether free text is evidence is open question 1.5, and it is a genuinely dangerous question: it would put the natural-language problem in the *evidence* path as well as the rule path | **5** |
| **`reservation.company_id`** | Structurally blocked: no company or corporate-account entity exists anywhere in the API | **5** |
| **Guest as an entity with an id; stable StayOps ids** | Guest fields are inlined on the reservation; records are keyed by provider-native ids. D2 §35 and D3 §19 ask for a `provider_entity_mappings` table so StayOps ids stay stable when a provider changes its internal identifier | **1** — this one is purely our own design choice |

**On the last row, the argument for doing it and the argument against.** For: D2 §35's warning is
sound, and the day a provider renumbers its rooms, every stored verdict's `record_id` becomes a
dangling reference. Against: an id-mapping table is a second source of truth that can disagree with
the provider, and inventing an identity where the provider has one is how joins start matching things
that are not the same thing. **Recommendation: not yet, and revisit the first time a provider
renumbers anything.** Recorded so it is a decision.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G12a availability entity** | 3 | 3 | 2 | **5** | **15** |
| **G12b `vip_status`** | 3 | 4 (an extractor that must quote its source, or nothing) | 3 | **5** | **15** |
| **G12c `company_id`** | 2 | — (not buildable) | 1 | **5** | **10** |
| **G12d stable ids / entity mapping** | 2 | 2 | 3 (record ids thread through verdicts and the store) | 1 | **6** |

---

### G13 · Management API surface and admin UI

**Asked for.** D3 §61–65: `POST /api/controls` taking `{"sourceText": "..."}` and returning a
compiled control, plus validate / activate / pause / execute / results; the guest-service policy and
request endpoints; and the PMS connection endpoints. D3 §66–69 and D2 §45–46: a create-control
screen, a results dashboard, guest policy screens, a staff queue.

**What exists.** A server-rendered page and a JSON API that do the *reading* half well — the control
list with per-provider readiness, a run with every verdict traced to the fields that produced it, a
stored run re-read with zero provider calls, run history, readiness per control per provider — plus a
compose window that takes prose and files a draft. What is missing is the *writing* half: no create
from a template with parameters, no validate, no activate, no pause.

**Why.** There is no lifecycle to drive (G6c) and no tenant to authorise the call (G5). The API is
thin because the objects it would manage do not exist yet, which is the right order.

**One thing to fix when the dashboard is built, and it is not a gap in our code but in the
specification.** D2 §45's mock UI shows a tile row: *8 Active · 1,284 Passed · 17 Failed · 6
Unknown*. There is no EXCLUDED tile and no coverage line. Reproduce that faithfully and a run where
every record was out of scope renders as a clean bill of health — which is **measured, not
hypothetical**: v1 reported 28 EXCLUDED / 0 FAIL for a control on a property where the underlying
mechanism had never been observed working, and on screen it was indistinguishable from compliance.
That is the failure this repository's coverage verdict exists to prevent. Any StayOps dashboard needs
a fifth tile and a coverage headline.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G13** | 3 | 3 | 2 (web + runner) | 1 | **6** |

---

### G14 · Observability

**Asked for.** D1 §49 and D3 §75: every significant operation carries `tenant_id`, `hotel_id`,
`request_id`, `execution_id`, `control_id`, `policy_version`, `provider`, `timestamp`, `result`; logs
must let a developer trace user request → compilation → evidence retrieval → PMS call →
normalisation → evaluation → action. And explicitly: never log credentials, guest PII, or payment
details.

**What exists.** No logging layer at all. What stands in for it is better than logs for one purpose
and useless for the others: the run store keeps every verdict with every field's value, unit,
known-ness, reason, risk id and provenance, re-readable months later without spending a provider
call. That is a far stronger audit trail than a log file. It says nothing at all about *operations* —
latency, error rates, which tenant is consuming the call budget, which provider is failing.

The prohibitions are already satisfied for a different reason: credentials come from the environment
with no default, and fixtures are pseudonymised at capture time.

**Why.** A single-operator local demo has a console and a person watching it.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G14** | 3 (a multi-tenant service cannot be operated blind) | 2 | 2 (cross-cutting but additive) | 1 | **6** |

---

### G15 · Per-tenant + per-provider rate limiting

**Asked for.** D1 §64: different hotels may share one PMS provider, so limits should apply per
`tenant + provider` rather than globally — *"this prevents one hotel from consuming capacity needed by
another."*

**What exists.** Two halves of it, neither joined up. A token-bucket rate limiter with bounded retry
and backoff lives in the opt-in transport, but it is **per process**, not per tenant. A call budget is
**per tenant** — and it *raises rather than truncating*, which is stronger than the documents ask —
but it bounds one run's evidence, not a tenant's share of a provider's capacity. Since credentials are
keyed by provider (G11), there is not yet a per-tenant-per-provider identity for a limiter to key on.

| | Impact | Effort | Blast | Evidence | **Exposure** |
| --- | --- | --- | --- | --- | --- |
| **G15** | 2 | 2 | 2 | 1 | **4** |

---

## 5. Where we are deliberately ahead, or deliberately different

**A report listing only shortfalls would misinform the reader about this codebase's maturity.** Each
item below is a place where the implementation goes beyond the three documents or knowingly departs
from them — every one with a reason found by calling the API rather than by reading about it.

### 5.1 EXCLUDED is a fourth outcome, and a run says when it concluded nothing

The documents specify three outcomes. This engine has four. **EXCLUDED means the control does not
apply to this record** — and it is separate from PASS because a record the control never examined has
not passed it. A run over a hundred reservations where ninety were out of scope must not report
"90 passed"; a compliance number inflated with records nobody checked is worse than no number.

On top of that, every run carries a **coverage verdict**: `evaluated = PASS + FAIL`, and a run where
`evaluated == 0` renders as *"this control reached no conclusion about any record"*, with the dominant
reason and **no count tiles at all**. This is not theoretical tidiness. It was measured: v1 reported
28 EXCLUDED / 0 FAIL for an out-of-service-room control on a property where the mechanism had never
been observed working, and on screen it looked exactly like compliance.

**Recommendation: adopt both into the specification.** They are improvements, not deviations to
correct, and D2 §45's own mock dashboard would reintroduce the exact failure they prevent.

### 5.2 Money carries its currency and refuses to compare across currencies

D2 §6's canonical reservation specifies `"rate": 250.00` as a bare number, `"balance": 0` as a bare
number, and `currency` as a separate sibling field. **That shape would reintroduce a bug this project
found in live data.**

Reservation `007003199` reports a total of **870 USD**. Its own folio reports a balance of
**3262.5 ILS**. No exchange rate exists anywhere in the API. A bare-number model invites exactly the
comparison that produces a confident, wrong answer about whether a guest still owes money.

Here, money is a `Decimal` plus its currency, constructible no other way; two amounts in different
currencies **raise** on comparison rather than returning a plausible boolean; and the one permitted
cross-currency comparison is against literal zero, which means the same in every currency. The
checkout controls are written against zero for precisely that reason. There is deliberately no FX
source: *"inventing a rate would be the single most damaging thing this engine could do to a finance
team."*

Note also that D2 §6 places `balance` **on the reservation**. In the real API the balance lives on the
folio, in a different currency, and costs a separate call per reservation. Three problems in one
field.

**Recommendation: D3 §8's `Money` type is right and D2 §6's bare numbers should be corrected.**

### 5.3 Kleene three-valued logic, not "any missing field wins"

D2 §29's template example is `if (!evidence.complete()) return UNKNOWN;` — all-or-nothing.

This evaluator is finer, and the difference matters in the hotel's favour:

```
all    any False → FAIL     else any unknown → UNKNOWN   else PASS
any    any True  → PASS     else any unknown → UNKNOWN   else FAIL
none   any True  → FAIL     else any unknown → UNKNOWN   else PASS
```

The first line is the subtle one: **one predicate that definitively fails is a complete answer.** An
outstanding balance is a violation whether or not some unrelated field was missing. The reverse — a
would-be PASS outranking a missing field — must never happen, and is tested in both directions.

### 5.4 `0` is not a number, and other facts the documents could not know

D2 §12 specifies room capacity as `adult_count + child_count <= room.capacity`. Implemented
literally, against this property, that control produces a wall of false FAILs: **23 of 28 rooms report
adult capacity `0`, meaning "nobody configured this" rather than "sleeps nobody".** Some per-room
prices are `0` on demonstrably paid bookings. Capacity and per-room price therefore carry
`zero_is_unknown`, and the control returns UNKNOWN rather than FAIL — which is why
`room_capacity_compliance` is one of the controls recorded as reaching no conclusion. **That is the
design working, not the engine failing**, and any implementation of D2 §12 that does not do this will
ship false accusations.

Three more of the same kind: `createDateTime` is date-only, so same-day precision is impossible and
must be stated rather than implied; room-type codes differ in case between endpoints, so comparison is
case-insensitive; and an OTA modification is a cancel-plus-recreate reusing the same portal id, so any
duplicate check must exclude cancelled records *and* records with no portal id — otherwise every
direct booking looks like a duplicate of every other.

### 5.5 A status nobody can name gets UNKNOWN, and the documents' enums cannot express that

D2 §9 and D3 §11 both define `ReservationStatus` as a closed set of six values with **no UNKNOWN
member** — while D2 §38 and D3 §18 both require that an unmapped provider value must never be guessed
at and must produce UNKNOWN. For room status, D3 §11 adds `UNKNOWN` and D2 §9 does not. **For
reservation status, neither document provides it.**

That matters here more than it sounds, because we counted: **44 of the 217 distinct reservations this
project has ever seen — one in five — carry a status code (`OK4`, `WL`) documented nowhere at all.**
They resolve to UNKNOWN, because a status nobody can name must not decide whether a control applies.
The documents' reservation-status enum cannot represent one in five of the reservations in the only
live system anyone has looked at.

**Recommendation: add `UNKNOWN` to every canonical enumeration, including reservation status.** And
note the cheapest fix available anywhere in this project: one sentence from MiniHotel explaining
`OK4` and `WL` resolves all 44.

### 5.6 Eleven controls, and two rule shapes no template in the documents covers

Four of the manager's five hotel controls exist (one split into two), and **seven further controls
exist that he did not ask for** — checkout with money owed, checkout with unrefunded credit,
duplicate channel reservations, resource occupancy consistency, rate/room-category consistency,
room-type validity and OOO room protection.

Two of those need machinery no template in D2 or D3 describes:

- **Cross-record assertions.** *"Two active reservations must not share the same channel confirmation
  number"* is not a question about one record. It needs group-by, count and attribution of a group
  verdict back to each contributing record with the group's evidence attached.
- **Interval arithmetic.** *"A room must not be occupied by two overlapping reservations"* needs
  overlap operators over date ranges.

Every template in D2 §28–32 and D3 §28–32 is a single-record predicate. **A StayOps built exactly to
those templates could not express either control** — and duplicate-booking detection is the sort of
thing a hotel notices immediately.

The split of one control into two is worth its own line, because it is a product judgement rather than
a technical one. A checked-out folio can be **negative**: reservation `007004348` left with
**−490.75 ILS** — the guest overpaid. Money owed is a collections problem and a probable loss; an
unrefunded credit is a liability with a different urgency and usually a different team. One queue
makes severity meaningless for both.

### 5.7 The canonical boundary is a test, not a discipline

D3 §87 calls it *"the most important rule in the project"*: nothing above normalisation may know which
PMS the hotel uses.

Here it is a grep test over the source tree, checking 28 identifiers — endpoint names, wire-format
field paths and vendor spellings — **from both providers**, with the allowed directories *discovered*
rather than listed, so a third adapter is policed from the moment it is added. It is deliberately
strict enough to catch prose, and it has caught comments: a comment explaining what a vendor field
maps to is evidence the knowledge has leaked upward even when the code has not.

The one deliberate exception is documented: a value's `source` carries a string like
`pms:minihotel/GetReservationBalance`, because an auditor must know which system and which call
produced a number. It crosses as data, contains no field path, and no layer above ever parses it.

### 5.8 The model boundary is stricter than the documents require

D3 §41 says *"never trust the LLM output directly"* and validates it. D1 §23 lists what the LLM must
not do. We agree with all of it and go one step further: **the model may not emit a rule at all.**

```
prose → [model] → restricted English → [deterministic grammar] → IR → [validator] → run
                   ↑ shown, editable    ↑ exact parse, confidence 1.0
```

The model drafts a **sentence** a person reads and corrects; the deterministic grammar builds the
rule. Three consequences the documents do not get:

- The intermediate is **reviewable in practice**, not merely in principle. Raw IR JSON is reviewable
  in principle and unreviewed in fact.
- A wrong field name is not bad IR that slipped through a schema — it is a sentence **the grammar
  refuses by name**, which is D3 §41's gate doing its job at the earliest possible point.
- It makes a free local model adequate, because rewriting a sentence into a template is a task a
  small model can do reliably where emitting valid nested IR is not.

And the placement is enforced structurally: **every model backend lives outside the engine and is
injected**, asserted over the AST; a live backend refuses to arm unless its environment variable is
set **and** no test runner is loaded in the process, so the test that sets the variable is refused
anyway; and a composed control is filed as a **draft**, badged unreviewed, and **excluded from the
headline controls-that-conclude figure** — a machine-drafted rule does not get to move the most
carefully-kept number in the repository.

### 5.9 Evidence cost is asserted, and a budget raises rather than truncating

D1 §29 asks for efficient execution and D3 §48 for a population resolver. Neither asks anyone to
prove it. Here the cost is **`1 + R + N`** — one population call, one per reference set, one follow-up
per record — **asserted by counting invocations** at the evidence layer and again end to end. A
run-scoped cache means one response is never fetched twice. And when a run would exceed its budget it
**raises** rather than silently truncating the population, because a control that quietly examined the
first hundred records and reported compliance is the same failure as turning UNKNOWN into PASS.

This exists because a folio takes one call per reservation, there is no bulk journal endpoint, and the
vendor has asked integrators not to query wide ranges without agreement.

### 5.10 Two more, briefly

- **Readiness is finer than the specification.** D3 §14's `ProviderCapabilities` is a boolean map per
  endpoint. Readiness here is per control × provider at **field** level — *"MiniHotel 4/5 fields ·
  DemoPMS 5/5"* — grouped by evidence source. That is what turns *"your PMS can't answer this"* into
  *"connect this one thing and it starts working."*
- **Freshness and `as_of` are computed, not declared.** D3 §22 lets a template declare
  `freshnessMinutes`. Here a run records when its evidence was *obtained*, as distinct from what date
  it describes and when the run happened; evidence whose age cannot be established is **stale, never
  assumed current**; and `as_of` defaults to the instant the evidence actually describes, so a capture
  of July answers questions about July instead of producing a page of refusals about today.

### 5.11 Zero runtime dependencies

Standard library only, enforced by a test that walks the tree. The engine installs nothing and runs
offline. Not required by any of the three documents, and worth keeping: it is why the demo has no
install step and why CI cannot accidentally reach the network.

---

## 6. Nine internal inconsistencies in the three documents

These are three drafts at versions 1.0, 1.1 and 1.0, and **they disagree with each other in nine
places.** Each needs an owner's ruling before it is built, because a developer resolving them
silently will resolve some of them wrongly.

| | Where they disagree | Why it matters |
| --- | --- | --- |
| **1** | **The guest decision set.** D2 §1 lists four outcomes and calls one `NEEDS_STAFF_REVIEW`; D2 §25, D1 §33 and D3 §51 list five and call it `STAFF_REVIEW`. D2 contradicts itself **inside one document** | It is a stored enum on every decision. Fix the set and the spelling before anything writes it |
| **2** | **`LATE_CHECKOUT`'s parameter names — four different sets.** D2 §19: `default_checkout`, `maximum_checkout`, `charge_after`, `staff_approval_after`. D2 §31: `free_until`, `charge_from`, `maximum_time`, `approval_required_after`. D3 §33: `normalCheckout`, `freeUntil`, `maximumTime`, `chargeFrom`. D3 §65 adds `staffApprovalAfter`. Also snake_case in D2, camelCase in D3 | This is the flagship template and half the Definition of Done. The names go in a tenant's stored parameters and in a compiler prompt |
| **3** | **The late-checkout example itself.** D2 §1 says *"late checkout up to 3 PM; after noon charge $25/hour"*; every other mention says *free until 2 PM, $25/hour until 4 PM, approval after 4* | The worked example appears in the compiler test corpus (D3 §81). Two versions means two expected answers |
| **4** | **Enumerations versus the never-guess rule.** D2 §38 and D3 §18 both require an unmapped provider value to produce UNKNOWN. But `ReservationStatus` has **no UNKNOWN member** in either D2 §9 or D3 §11, and `RoomStatus` gains one in D3 §11 while D2 §9 lacks it | The rule cannot be implemented in the type the documents specify. See §5.5: one in five real reservations needs it |
| **5** | **Payment-guarantee parameters.** D2 §10: `exceptions: ["COMPLIMENTARY"]`, an open array. D3 §28: `complimentaryException: boolean`, a flag | An array is extensible and a boolean is not. Decide before a parameter schema is written |
| **6** | **Room-capacity parameters.** D2 §12 gives the template no parameters at all; D3 §30 gives it `{"maximumGuests": "ROOM_CAPACITY"}` — a parameter whose value is the template's own name | Probably an editing artefact, but it is the only guidance a developer has for that template's schema |
| **7** | **Is `INACTIVE_ROOM_ASSIGNMENT` its own template?** D2 §14 says `ROOM_ASSIGNMENT_STATUS` *"or a specialized INACTIVE_ROOM_ASSIGNMENT"*; D1 §8 and D3 §26 register it as one of the five | Changes the count of templates and the shape of one parameter schema |
| **8** | **Money's type.** D2 §6 models `rate` as a bare `250.00` and `balance` as a bare `0` with `currency` alongside; D3 §8 upgrades both to a `Money` type | D2's shape reintroduces a bug found in live data — see §5.2. **D3 is right** |
| **9** | **Build order, and this is the sharpest one.** D2 §48 is a seven-day plan that builds all five control templates on day 3, the compiler *and* all five guest templates on day 4, and **never mentions multi-tenancy at all**. D3 §84 makes multi-tenancy Phase 1 and says of the controls *"do not build all five simultaneously"*. D3 §5 says multi-tenancy *"should be implemented before building the policy engine"*, while D3 §88 says *"resist the temptation to build a platform before proving the product — 1 hotel, 1 PMS, 1 control, 1 violation"*, and D3 §85 says the first week's deliverable must already work for Hotel A **and** Hotel B | These cannot all be true, and they prescribe opposite first moves. §7's roadmap takes a position and states it |

One thing that is **not** an inconsistency, and should not be reported as a gap: D3 §2's suggested
directory layout (`stayops/apps/`, `services/policy/`, `packages/evaluator/`). D3 §2 says explicitly
that the architectural requirement matters more than the language or the layout, and that an existing
codebase organised differently should not be restructured to match. This report therefore compares
**responsibilities**, not folder names.

---

## 7. Roadmap

Phased, each with a stated prerequisite and an **exit test** — in the style `docs/plan.md` already
uses, because that file's habit of writing the gate before the code is why its one unmet criterion is
recorded honestly rather than quietly rounded up.

### 7.1 Exposure-sorted, so the ranking is visible

| Rank | Gap | Impact | Effort | Blast | Evid | **Exp** | Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | G2(b) acting — if chosen | 5 | 4 | 5 | 3 | **25** | A (decide) |
| 1 | G3 five guest templates, as a set | 5 | 4 | 2 | 5 | **25** | D, E |
| 3 | G4 payment guarantee **as specified** | 4 | 2 | 1 | 5 | **20** | B (narrowed) |
| 3 | G5 multi-tenant isolation | 5 | 5 | 4 | 1 | **20** | F |
| 3 | G9 Mews | 4 | 3 | 1 | 5 | **20** | J |
| 6 | G1 guest-service machinery | 5 | 5 | 3 | 1 | **15** | D |
| 6 | G3d `ROOM_UPGRADE` | 3 | 3 | 2 | 5 | **15** | E |
| 6 | G12a availability entity | 3 | 3 | 2 | 5 | **15** | E |
| 6 | G12b `vip_status` | 3 | 4 | 3 | 5 | **15** | — (needs a decision) |
| 10 | G6a template + parameters | 4 | 3 | 3 | 1 | **12** | C |
| 10 | G11 onboarding + connections | 4 | 3 | 3 | 1 | **12** | I |
| 12 | G12c `company_id` | 2 | — | 1 | 5 | **10** | — (not buildable) |
| 12 | G3a `LATE_CHECKOUT` alone | 5 | 2 | 2 | 2 | **10** | D |
| 14 | G2(a) advisory actions | 4 | 2 | 2 | 1 | **8** | G |
| 14 | G6b policy versioning | 4 | 2 | 2 | 1 | **8** | C |
| 14 | G8 advisory notifications | 4 | 2 | 2 | 1 | **8** | G |
| 14 | G10c idempotency | 4 | 2 | 2 | 1 | **8** | H |
| 18 | G3c `EARLY_CHECKIN` | 3 | 2 | 2 | 3 | **9** | E |
| 18 | G10d event ingestion | 3 | 3 | 3 | 3 | **9** | H |
| 20 | G3b towels + maintenance | 3 | 2 | 2 | 1 | **6** | E |
| 20 | G4 narrowed (card-present) | 3 | 1 | 1 | 2 | **6** | B |
| 20 | G6c lifecycle + activation gate | 3 | 2 | 2 | 1 | **6** | C |
| 20 | G10a scheduler daemon | 3 | 2 | 2 | 1 | **6** | H |
| 20 | G10b queue + workers | 2 | 3 | 3 | 1 | **6** | — (defer) |
| 20 | G12d stable ids | 2 | 2 | 3 | 1 | **6** | — (revisit on need) |
| 20 | G13 management API + admin UI | 3 | 3 | 2 | 1 | **6** | C, F |
| 20 | G14 observability | 3 | 2 | 2 | 1 | **6** | G |
| 28 | G15 per-tenant rate limiting | 2 | 2 | 2 | 1 | **4** | I |
| 29 | G7 adapter interface shape | 1 | 2 | 2 | 1 | **2** | — (no action) |

### 7.2 Why the sequence is not the exposure order

**Stated openly because it looks like an inconsistency and is not.** Three of the top five rows cannot
be started first:

- **G2(b)** is a question, not work. Nobody should build toward it or away from it until it is
  answered.
- **G9 (Mews)** is blocked on credentials nobody has, and no amount of sequencing produces them.
- **G4 as specified** is blocked on evidence that does not exist; only the narrowed version is
  buildable, and that is cheap.

Exposure ranks *danger*. Sequence has to respect prerequisites. Both are shown so the difference is
auditable rather than hidden in a judgement call.

---

### Phase A · Decide, before building anything

Two decisions, no code. **This phase exists because getting either wrong is more expensive than
everything in phases B through E combined.**

**Prerequisite:** None

1. **G2 — advisory or acting?** Does StayOps hand staff a task, or post the charge and create the
   request itself? Recommendation in G2: ship advisory, model every action as a record with a state so
   acting stays available behind one indirection.
2. **The nine inconsistencies in §6** — at minimum #1 (the decision set), #2 (`LATE_CHECKOUT`'s
   parameter names) and #9 (build order), because Phase D writes all three into stored data.

**Exit test.** Both decisions written into `docs/open-questions.md` in its existing decided-with-reasons
form, each with the alternative that was rejected and why. That file's own standard: *"reversing one
of these is cheap now and expensive later."*

---

### Phase B · Complete the manager's five hotel controls

Add `PAYMENT_GUARANTEE_BEFORE_ARRIVAL`, narrowed to what captured evidence can honestly support:
*every reservation arriving within N hours must have a payment card on file.*

**Prerequisite:** None. This is a `spec/` data change — the cheapest item in the roadmap

**Exit test.**
- The control runs end to end on **both** providers with identical verdicts per record id and
  identical call counts.
- A reservation with a masked card present reaches PASS; one with no card reaches FAIL; and the
  *guarantee requirement itself* returns **UNKNOWN naming the missing field** rather than being
  inferred from card presence.
- `tools.validate_spec` passes, including the new mapping's regex against its probe file.
- **The criterion-1 figure in `docs/plan.md` is re-measured and restated** — 12 controls now, and the
  number that reach a conclusion is whatever it is. This is the test that matters most: the figure is
  the most carefully-kept number in the repository, and adding a control must move it honestly or not
  at all.

---

### Phase C · Templates, parameters, versions, lifecycle

The platform's missing spine, and the reason it comes before guest services: **guest-service policies
are the purest example of one template with per-hotel parameters** (D1 §36 — Hotel A $25/hour, Hotel B
$50/hour, Hotel C everything to staff review). Build that mechanism against the eleven controls that
already exist and are already tested, then guest services gets it for free instead of inventing a
second version of it.

**Prerequisite:** Phase A decision #2 (parameter naming)

Work: a template object with a typed parameter schema; tenant-supplied parameters validated against
it; a `version` that is read rather than decorative; `policy_version` on every stored result; the
`DRAFT → VALIDATING → READY → ACTIVE → PAUSED → ARCHIVED` lifecycle; and an activation gate that
consults readiness. Plus the write half of the management API (`POST /api/controls`, validate,
activate, pause) which has nothing to manage until now.

**Exit test.**
- **Two tenants run the same template with different parameters and get correctly different verdicts,
  with no second IR file anywhere.** This is D1 §74's criterion — no customer-specific branches — made
  mechanical, and a test should assert that the number of template files does not grow with the number
  of tenants.
- A stored run names the exact policy version that produced it; editing a policy makes v2 and leaves
  v1's stored runs pointing at v1.
- **Activating a control whose readiness is short of its required evidence is refused, naming the
  missing fields** (D3 §46). The existing readiness computation supplies the answer; this asserts that
  something finally acts on it.
- All 1610 existing tests still pass — this phase reshapes how controls are stored and must not
  change a single verdict.

---

### Phase D · Guest services, one vertical slice: `LATE_CHECKOUT`

D3 §84 Phase 8 and D1 §61 both say build this one end to end first, and they are right.

**Prerequisite:** Phase A (both decisions), Phase C (parameters and versions)

Work: a guest request object; intent extraction behind the **same** injected-proposer discipline the
sentence compiler uses — the model identifies the intent and the requested time and **decides
nothing**; a decision type; fee arithmetic in `Money`; and one new canonical field,
`hotel.checkout_time`, tenant-supplied.

**Exit test — D2 §49's own Definition of Done, made executable.**
- Policy: *free until 2 PM, $25/hour until 4 PM, manager approval after.* Guest asks for 3 PM.
  Decision: `APPROVED_WITH_FEE`, fee **$25 as `Money` carrying its currency** — a bare `25` fails this
  test.
- **Boundary conditions on both sides of both thresholds**: exactly 14:00, one minute after, exactly
  16:00, one minute after. D3 §79 asks for boundary tests; off-by-one on a fee the guest is charged is
  the likeliest real defect in the whole feature.
- A request whose evidence cannot be established returns **`STAFF_REVIEW` naming what was missing** —
  guest services' UNKNOWN, per G1. Never a guess, never a default approval.
- An unsupported intent returns `UNSUPPORTED_REQUEST` with `requires_staff` (D2 §23); an ambiguous one
  asks a question rather than inferring (D3 §82).
- **The same policy produces the same decision through both providers**, which is criterion 7 applied
  to a shape it has never been applied to.
- The same request delivered twice produces one decision and one action (D1 §65) — even before
  Phase H, because a guest double-tapping a button is not a retry edge case, it is Tuesday.

---

### Phase E · The remaining four guest templates

**Prerequisite:** Phase D

**Ordered by evidence risk, not by the documents' list order** (G3): `EXTRA_TOWELS` and
`MAINTENANCE_REQUEST` need no PMS evidence at all; `EARLY_CHECKIN` needs room-readiness semantics
this property has not established; `ROOM_UPGRADE` needs an availability entity that does not exist and
a rate mapping that R13 says no endpoint resolves.

**Exit test.**
- Towels: quantity within the maximum → `APPROVED` + a service-request action; over the maximum →
  `DENIED` naming the limit.
- Maintenance: classified into a **small controlled list** of categories and priorities (D3 §37),
  routed, acknowledged — and an unrecognised complaint goes to staff rather than being forced into the
  nearest category.
- Early check-in: reaches a real decision where room readiness is established, and `STAFF_REVIEW`
  naming the missing evidence where it is not.
- **Room upgrade: either it reaches a real decision from real captured availability evidence, or it is
  reported as blocked by name.** A room upgrade approved from inferred availability is the guest-side
  equivalent of turning UNKNOWN into PASS, and the rule that outranks everything else in `CLAUDE.md`
  applies here unchanged.

---

### Phase F · Multi-tenant isolation

**Prerequisite:** Phase C (there must be tenant-owned objects worth isolating)

Work: authentication; a tenant context established from it and never from a request parameter;
tenant-aware repositories; roles (`HOTEL_ADMIN` / `HOTEL_MANAGER` / `HOTEL_STAFF`); and every
tenant-owned query scoped.

**Exit test — D3 §80 calls these mandatory, and they are the ones to write first.**
- Hotel A's credentials **cannot** read Hotel B's controls, results, guest requests or PMS connection,
  **attempted directly against the API rather than through the UI** (D3 §80 is explicit about that).
- A repository call made without a tenant context **fails loudly** rather than returning everything.
- **A structural test — in the style of the existing canonical-boundary grep — asserting that no query
  against a tenant-owned table lacks a tenant predicate.** This is the one that survives contact with
  a growing team, and it is the direct analogue of the test that already keeps PMS names above the
  provider layer. Note where it has to start: today `store/sqlite.py` contains **no** `tenant_id`
  predicate at all.
- `?property=` no longer selects a property.

---

### Phase G · Actions, notifications, observability

**Prerequisite:** Phase A decision #1, Phase F (an alert must know whose it is)

Work: an action interface whose advisory members (`SEND_EMAIL`, `STAFF_REVIEW`, `GUEST_RESPONSE`)
execute and whose PMS-writing members exist only if Phase A chose (b); email; a staff-review queue;
and structured logging carrying tenant, execution, policy version and provider.

**Exit test.**
- A control reaching FAIL emails the audience its IR has declared since slice 1 — `severity: high`,
  `audience: finance` — with no new configuration invented for it.
- **A run that concluded nothing sends nothing**, and a run that is blocked sends a different message
  from a run that passed. The coverage verdict already distinguishes them; this asserts the notifier
  respects it instead of treating "no failures" as good news.
- No log line contains a credential, a guest email, a phone number or a card token — asserted by a
  test over emitted log records, not by review.
- One trace answers D1 §66's six questions: what policy, what version, what evidence, what the PMS
  returned, what we normalised it to, why the evaluator concluded what it did.

---

### Phase H · Scheduling, events, idempotency

**Prerequisite:** Phase G (a scheduler whose results nobody is told about is not worth running)

Work: the loop around the existing `next_evaluation`; `HOURLY` and `DAILY`; idempotency keys on
executions and actions; webhook ingestion if and only if MiniHotel's payloads have been observed.

**Exit test.**
- A control with an hourly plan runs hourly against an injected clock, unattended, and a control the
  scheduler reports as `unschedulable` is **never given a plausible interval** — the existing pure
  function already refuses to invent one; this asserts the daemon honours the refusal.
- **The same job delivered twice produces one run and one notification** (D1 §65). Assert it by
  delivering it twice, not by inspecting the key.
- `make_run_id` stops hashing `created_at` into an identity that is supposed to be idempotent, and a
  test names the difference between a content hash and an idempotency key.

---

### Phase I · Onboarding and per-tenant connections

**Prerequisite:** Phase F

Work: the create-hotel → connect → **test** → discover → configure → validate → activate flow;
credentials keyed by **tenant and provider** rather than provider alone; encrypted credential storage;
per-tenant-per-provider rate limiting.

**Exit test.**
- **Two properties on the same PMS hold distinct credentials and both work.** Today the second
  overwrites the first (open question 1.9), so this test fails before the fix, which is the right
  starting condition.
- A connection test reports success or a specific named failure — auth, timeout, unreachable —
  distinguishing a wrong password from a down server (D3 §76).
- The discover step reports, per control, which evidence this connection can supply. Readiness already
  computes exactly this against a fixture; this wires it to a live connection.
- One tenant exhausting its budget against a shared provider does not degrade another's (D1 §64).

---

### Phase J · Mews

**Prerequisite:** **Credentials.** Nothing else, and nothing substitutes

**Exit test — D3 §78's own acceptance test, which DemoPMS already passes.**
- The existing contract suite runs against the third adapter **unchanged**, and no control is
  rewritten.
- Every control produces equivalent canonical behaviour on the same logical hotel through MiniHotel
  and Mews.
- **The diff contains no change above the provider layer.** That is the whole architectural thesis,
  and the slice-7 diff that added DemoPMS is the precedent to match.
- The canonical-boundary grep covers the new adapter's identifiers **automatically**, because the
  allowed directories are discovered rather than listed — no test edit required. If one is required,
  the boundary leaked.

---

## 8. Open questions for the owner and the manager

Things needing a **decision** rather than work. The first three are new to this report; the rest are
already recorded in `docs/open-questions.md` and are repeated only where these documents change them.

### New, arising from these three documents

| | Question | What it decides | Recommendation |
| --- | --- | --- | --- |
| **N1** | **Does StayOps act, or advise?** (G2) | Whether a founding constraint is reversed. Changes the blast radius of half the roadmap from 2 to 5 | **Advise first**, with actions modelled as records that a human performs, so acting stays one indirection away |
| **N2** | **The nine internal inconsistencies** (§6) — especially the decision set, `LATE_CHECKOUT`'s parameter names, and the build order | Stored enums, a parameter schema, a compiler test corpus, and what gets built first | Rule on #1, #2 and #9 before Phase C. The rest can wait for the template that needs them |
| **N3** | **Do our four outcomes and our coverage verdict become part of the specification?** (§5.1) | Whether the next developer reproduces D2 §45's four-tile dashboard, which would report a clean bill of health for a run that concluded nothing | **Yes.** Add EXCLUDED, add a coverage line, and add `UNKNOWN` to every canonical enumeration including reservation status (§5.5) |

### Existing questions these documents make more urgent

| | Question | What changed |
| --- | --- | --- |
| **1.1** | Does an unverifiable exception count as a pass? | Unchanged and still the biggest product question. Roughly nine of the original twenty controls turn on it. Guest services adds a second instance: is a `STAFF_REVIEW` a product, or a failure to decide? Both are defensible; they are different products |
| **1.4** | Which rate codes has the property nominated? | Still the cheapest movement available on the controls-that-conclude figure — one sentence from a property. And Phase C's parameter mechanism makes it a *setting* a hotel can supply rather than a gap |
| **1.5** | Is unstructured free text evidence? | **These documents raise the stakes.** `guest.vip_status` is required by D2 §33 and D3 §9, and in live data it exists **only** as Hebrew free text in a remarks field — alongside the manager's approval: *"VIP policy is met. Approved by the manager on Telegram."* `ROOM_UPGRADE` (D3 §35) wants VIP status too. Answering yes puts the natural-language problem in the **evidence** path as well as the rule path, and the second is much the riskier |
| **1.7** | Mews | Promoted from *"the most valuable thing that could be added"* to **a named product requirement on the front page of all three documents**, and still blocked on credentials nobody has |
| **1.9** | Production PMS access, and whose credentials | D1 §14 and §43 require per-tenant encrypted credentials. Today credentials are keyed by provider, so **two properties on one PMS cannot coexist** — Phase I, and it is the second customer, not a scaling concern |
| **2.1** | Ask MiniHotel what `OK4` and `WL` mean | One in five reservations. Still one sentence. §5.5 shows the documents' own enums cannot represent those records at all |

### One question for the manager, specifically

**Is the five-control list a requirement or an illustration?** D1 §56 and D3 §26 say *"register
exactly these five."* This repository ships eleven, four of which match the five (one split in two),
and seven of which he did not ask for — including duplicate-booking detection and occupancy overlap,
which need cross-record machinery **no template in D2 or D3 describes** (§5.6). Nothing needs
correcting in either direction; the two lists were chosen for different reasons. What needs deciding is
whether the seven extras are kept, which is a product judgement about what hotels actually want.

---

## 9. What this report does not claim

Kept short, because a gap analysis that overstates its own confidence would be the wrong artifact for
this codebase.

- **Effort scores are relative, not estimates.** A `5` means "architectural reversal", not a number of
  weeks. Nothing here has been planned in detail.
- **`UNVERIFIED` rows are marked as such** and not silently averaged into the ranking: Mews's real
  behaviour (G9), MiniHotel's webhook payloads (G10d), whether any PMS write endpoint exists or what
  it would cost (G2b), and room-readiness semantics per property (G3c).
- **Four load-bearing evidence facts rest on a 2024 capture of a system known to have moved on** —
  the 23 rooms with unconfigured capacity, three rooms carrying an undefined room type, the
  never-populated closed-date window, and the rate-versus-price-list key mismatch. Three read-only
  calls would settle all four; the probe is written, prints its exact request bodies with placeholders
  where the credentials go, makes no calls without approval, and **is waiting on one word** (open
  question 1.2). Several evidence-risk scores above would change if it ran.
- **No gap in this report has been implemented**, and nothing has been committed or pushed.
