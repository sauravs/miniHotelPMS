# 5 · StayOps, the POC, and this engine: a three-way comparison

> **What this is.** Three readings of the same requirements, compared one feature at a time:
>
> - **StayOps**: the three requirement documents the project owner's manager supplied.
> - **The POC**: a second, independent implementation of those same documents, kept in
>   `ruleEngineAnishLegacy/`.
> - **Ours**: this repository's `main`.
>
> For every StayOps feature it says what StayOps asks for, whether the POC covers it, whether we
> do, and, where either does not, the reason, if a reason was ever written down.
>
> **What this is not.** It is not a plan. It recommends nothing to build, port or drop. What happens
> next is the owner's call (the owner's answer of 2026-10-21).
>
> Sources were read on 2026-10-21. Repository figures come from
> [the README's table](README.md#what-is-true-as-of-this-writing) and were re-checked by running
> the suite before this document merged.

---

## 1. The three sources, and how each was read

**Both outside sources are git-ignored, so no reader of this repository can open them.** That is
why this document quotes rather than points.

| | Source | How it was read |
| --- | --- | --- |
| **StayOps** | `miniHotelLegacy/StayOps Controls Rule Engine/`, three `.docx`: **01** *Product, Architecture & Implementation Design* v1.0 (~4,360 words) · **02** *Technical Design & Coding Specification* v1.1 (~2,940) · **03** *Developer Implementation Package* v1.0 (~3,670) | Read in full, directly, after extracting each file with `pandoc -t gfm` into a scratch directory outside the repository. md5-identical to `ruleEngineAnishLegacy/initial-req/*.docx`, so **both builds started from the same requirements**. `docs/stayops-gap-analysis.md` calls them D1, D2 and D3 and was used only as a cross-check: its "what we have" side was measured on 2026-09-28, before v3 |
| **The POC** | `ruleEngineAnishLegacy/`: `backend/src/index.js` (413 lines, the whole backend: Express 5, SQLite, a WebSocket), `frontend/src/main.jsx` (216, the whole React UI), CSS, HTML, two READMEs, two `package.json`, and `backend/poc.db` (11 tables) | **Read only.** No `npm install`, nothing executed, no port, no network. `poc.db` was opened with `sqlite3.connect("file:…/poc.db?mode=ro", uri=True)`. A behaviour that reading cannot establish is marked **UNVERIFIED**. The author is not available, so where neither the code nor the README gives a reason, the row says **"reason not stated - UNVERIFIED"** and never guesses at intent |
| **Ours** | `main` | Every "Covered" names the file or test that proves it. Every reason for something we did not build is quoted from a **written** decision: `docs/plan-v3.md` §4 (each StayOps gap's disposition) and §8, D1-D16 in [`open-questions.md`](../open-questions.md), `prd.md` §6. Where no document gives one, the row says so |

Section references are written `01 §45`: document 01, its own section 45. Where a row matches a gap
in `docs/stayops-gap-analysis.md` and `docs/plan-v3.md` §4, it carries that gap's **G-id**, so the
three documents line up.

### What the POC is, in four sentences

An Express + SQLite backend and a React dashboard. Its README says: *"It uses only mock
MiniHotel-style data; no production PMS data or credentials are involved."* It implements all five
hotel-control templates and all five guest-service templates from a single catalogue
(`POLICY_CATALOG`), with two tenants (`Hotel A Group`, `Hotel B Group`), event-triggered runs and a
live activity feed. A search of the tree for test or spec files finds none, and it calls no model.

**Mock data has a cost, and it is not negligence.** The seven facts in `CLAUDE.md` were found by
calling the real API: a folio in another currency, a `0` that means "unconfigured", status codes
documented nowhere. A mock PMS returns whatever the seed typed, so the POC never met any of them.
§5 shows what each would have done to it. Equally, line counts and file layouts are not compared
here. A POC on mock data and an engine on real captures made different bets, so this document
compares **responsibilities and guarantees**.

---

## 2. The coverage words

Used exactly, in every cell.

| Word | Means |
| --- | --- |
| **Covered** | Built. *Ours:* a named file or test proves it. A hotel control that runs also gives **what it answers on real captures** in the same cell, because built is not the same as concluding (owner, 2026-10-21). *POC:* the function, route or table is named or quoted. The POC was built on mock data only, so its "Covered" never means it has met a real PMS |
| **Partial** | Part of it is built. The cell says **what is missing** |
| **Not covered** | Absent, and no decision about it is recorded |
| **Rejected on purpose** | A written decision says no, and the cell cites it |
| **Blocked (on X)** | Cannot be built honestly until X exists |
| **Deferred (by whom)** | A written decision postpones it |
| **UNVERIFIED** | Cannot be settled by reading |

---

## 3. The comparison

One table with a row per StayOps feature, grouped by area. *Why not* is filled in only where a column
is not **Covered**. "Not stated" always means **reason not stated - UNVERIFIED**.

| StayOps feature (doc §, a short quote) | StayOps requires | POC | Ours | Why not, where not |
| --- | --- | --- | --- | --- |
| **A · The two capabilities** | | | | |
| **01 §2.1 Hotel Controls** - *"Is the hotel operating according to its own rules?"* | A hotel states a rule; StayOps checks the data and reports violations | **Covered.** `evaluateControl` runs a template over the hotel's rows; `POST /api/hotels/:hotelId/controls/:controlId/execute` | **Covered.** 11 controls in `spec/ir/`; `tests/e2e/test_runs.py`. On real captures: **2 of 11 conclude** on `sandbox2026`, 1 on the refresh, 5 on `sandbox2026cover`. `prd.md` criterion 1 asks for 8, so it is **NOT MET** | - |
| **01 §2.2 Guest Service Rules** - *"Given this guest request and the hotel's rules, what should happen?"* · **G1** | A guest asks, and StayOps decides | **Covered.** `POST /api/hotels/:hotelId/guest-requests`, five templates | **Partial.** One template, `LATE_CHECKOUT`, taking a structured request. `POST /api/guest/requests`; `tests/integration/test_guest_requests.py`. Missing: four templates, and prose intake | **Ours:** G1 *TAKE, NARROWED* (plan-v3 §4): prose intent extraction and "every template but one" cut. D12 |
| **02 §27 Common Policy Engine** - *"The same deterministic condition evaluator can be used by both product areas"*, ten operators | One `evaluateCondition(operator, actual, expected)` under controls and guest services | **Not covered.** No shared condition function: each template's test is written inline, in `evaluateControl` or in the guest-request route | **Partial.** Controls use one evaluator with all ten operators (`equals` … `not_exists`) plus `matches_ignore_case`, aggregates and intervals (`hotelcontrols/evaluator/predicates.py`). Guest decisions share the evidence layer and the kernel (`guest/evidence.py` imports `evidence.gather`), but decide by their own rule table in `guest/decision.py`, which imports nothing from `evaluator/` | **POC:** not stated. **Ours:** plan-v3 slice 22 allowed `evaluator/`'s predicates to be "reused by import"; as built they are not, and no document says why |
| **B · Templates, policies, natural language** | | | | |
| **01 §8 Templates vs Customer Policies** - *"The underlying template is shared. The parameters are tenant-specific."* · 03 §25 `parameterSchema` · **G6a** | A global template library, with per-tenant parameters validated against a schema | **Partial.** The library is `POLICY_CATALOG`, served by `GET /api/policy-catalog`; parameters are stored per hotel in `controls.parameters_json` and `service_policies.parameters_json`. Missing: a schema. `validateGuestParameters` checks a few fields of four guest templates, and control parameters are not validated | **Partial.** Typed parameters with a distinct *not decided* state (`spec/parameters.json`; `tests/integration/test_typed_parameters.py`), so one IR serves two hotels with different verdicts. Missing: a template library | **POC:** not stated. **Ours:** G6a *TAKE, NARROWED*: "Cut: reshaping IR storage into a template library" |
| **02 §31** - *"Validator checks: time ordering, fee type, required parameters"* | A hotel's late-checkout policy is validated before use | **Partial.** `validateGuestParameters` requires `normalCheckoutTime` and `maximumAutomaticTime`, but `{ ...template.defaults, ...parameters }` fills any parameter a hotel did not give from the catalogue, so a hotel that set nothing gets 12:00, 16:00 and `chargeAmount: 25`. No time-ordering check | **Covered.** Parameters are typed and validated, and an undecided one is `null`: every request is `STAFF_REVIEW` naming it, never a default (V8, V10; `spec/tenants/sandbox.json` `"free_until": null`; `tests/unit/test_guest_decide.py::TestNeverWidened`) | **POC:** not stated |
| **01 §22-23 Natural Language Policy Creation** - *"Natural Language ↓ LLM Compiler ↓ Supported Template ↓ Parameters"* | A model maps prose to a template and its parameters | **Partial.** `interpretPolicy(sourceText, kind)` is regular-expression matching and calls no model. Parameters are fixed per template, except the late-checkout fee, read from a `$NN`. The UI never sends prose: it creates controls from a dropdown | **Partial.** Compose: a model drafts a **restricted sentence**, which a deterministic grammar compiles into a full IR, not template-plus-parameters (`tests/unit/test_web_compose.py`, `test_compiler_grammar.py`). Off unless `HOTELCONTROLS_COMPOSE=1`. What it files is a draft, never counted | **POC:** not stated. **Ours:** D10: a model drafts a sentence and never a rule |
| **03 §40 Compiler Output** - `COMPILED` / `NEEDS_CLARIFICATION` / `UNSUPPORTED`; 03 §82 *"Do not silently infer."* | Three explicit outcomes; an ambiguous request gets a question back | **Partial.** Unmatched text → 422 *"Unsupported or ambiguous control text. Supply a supported templateId."* There is no clarifying question, and the first pattern that matches wins: any text containing "required" becomes the guest-phone template | **Covered, under other names:** compiled, a question, or a refusal naming the missing vocabulary (`test_web_compose.py::TestATurn`, e.g. `test_a_question_is_rendered_as_a_question_not_an_error`) | **POC:** not stated |
| **01 §23 · 03 §41** - the LLM must not *"decide PASS/FAIL"* or *"generate executable code"* | No model in the decision path | **Covered.** No model anywhere in the tree | **Covered.** `tests/unit/test_proposers_refuse_in_tests.py`, `test_stdlib_only.py`, `test_guest_no_model.py` (D10, D12) | - |
| **03 §81 LLM Tests** - *"Maintain a test corpus"*, five phrasings that must compile | A corpus test | **Not covered.** No tests | **Partial.** The compiler is tested over our own grammar (`test_compiler_grammar.py`, `tests/integration/test_compiler_roundtrip.py`), but none of the five StayOps phrasings appears in `tests/` | **POC:** not stated. **Ours:** no document gives a reason |
| **03 §68 Never Hide the Compiled Policy** - *"The customer confirms before activation."* | The interpreted policy is shown, and confirmed | **Partial.** The guest-policy form shows its parameters before the button. Creating a control is one click: the UI posts it with default parameters, then calls `/activate` at once | **Partial.** The restricted sentence is shown in an editable box before anything is filed (`test_the_sentence_arrives_in_an_editable_box`). There is no activation step to confirm | **POC:** not stated. **Ours:** activation is G6c, below |
| **01 §25 Hotel Control Lifecycle** - DRAFT → VALIDATING → READY → ACTIVE → PAUSED → ARCHIVED, *"Only validated policies can become ACTIVE."* · **G6c** | Six states, gated | **Partial.** `controls.status`: create → `READY`, `/activate` → `ACTIVE`, with no check. No VALIDATING, PAUSED or ARCHIVED. Guest policies are inserted `ACTIVE` | **Deferred** (owner-approved plan-v3 §4). Two states, as directories: `spec/drafts/` and `spec/ir/` | **POC:** not stated. **Ours:** G6c: *"with no scheduler, active means nothing operational. Gated on readiness today, it would hide the five controls that correctly report their blockers"* |
| **03 §45-46 Policy Validation** - *"The hotel should not be allowed to activate the policy."* · 01 §54 *"The hotel should be told why."* | Syntax, template, evidence and provider checks before activation | **Not covered.** Activation checks nothing | **Partial.** Readiness per control × provider, per field, naming what is missing (`hotelcontrols/runner/readiness.py`; `tests/unit/test_runner_readiness.py`). It blocks nothing, because nothing activates | **POC:** not stated. **Ours:** G6c, above |
| **01 §38 · 03 §44 Policy Versioning** - *"Historical guest decisions remain associated with version 1."* · **G6b** | Every result names the version that produced it | **Not covered.** No version column on `controls`, `service_policies` or any result | **Covered.** A spec lock; every run stores `policy_version` and `policy_digest`, every guest decision `template_version` and `template_digest` (V3; `tests/unit/test_policy_versioning.py`, `tests/integration/test_policy_version_runs.py`) | **POC:** not stated |
| **01 §37 Tenant-Specific Exceptions** - *"VIP: No charge"* | Bounded exceptions inside a template | **Not covered.** No guest template has an exception parameter | **Blocked** on `vip_status`, which exists only as Hebrew free text (G12b, question 1.5) | **POC:** not stated |
| **C · The canonical model** | | | | |
| **01 §18 Canonical Data Model** - Hotel, Guest, Reservation, Room, Room Category, Payment, Availability, Rate | A small model of eight objects | **Partial.** Tables `hotels`, `rooms`, `reservations`, with the guest's name and phone inline on the reservation. No guest, payment, availability or rate entity; `rate REAL` is a column | **Partial.** 53 canonical fields (`spec/canonical_fields.json`). The guest is inline (`reservation.guest.phone`), payment is `folio.*`, there is no availability entity, and `rate_plan.*` is unresolvable (R13) | **POC:** not stated. **Ours:** availability is G12a, *BLOCKED* (no availability entity). For the rest, no document gives a reason |
| **03 §8 `rate?: Money; balance?: Money`** (02 §6 has a bare `250.00` beside `"currency"`) | Money carries its currency | **Not covered.** `rate REAL`, `fee REAL`. There is no currency anywhere, and `$` is hard-coded in explanations and the UI | **Covered.** `Decimal` plus currency, and comparing two currencies raises (`hotelcontrols/kernel/money.py`; `tests/unit/test_kernel_money.py`; R9) | **POC:** not stated |
| **02 §9 · 03 §11 Canonical Enumerations** | Closed enums; 03 gives `RoomStatus` an `UNKNOWN` | **Partial.** `normaliseRoomStatus` maps five raw strings, anything else to `"UNKNOWN"`. Reservation status is stored already canonical by the seed, and `payment_guarantee_status` defaults to `'UNKNOWN'` | **Partial.** Statuses come from each property's tenant file. No `TENTATIVE`, an added `waitlist`, and any status nobody named (`OK4`, `WL`: 77 of 526 reservations ever seen) is UNKNOWN (`tests/unit/test_spec_tenant.py::test_an_undocumented_code_is_unmapped_rather_than_guessed`) | **POC:** not stated. **Ours:** no document rules on `TENTATIVE`; question 1.12 asks for `UNKNOWN` in every enum |
| **02 §6 · 03 §21** `payment_guarantee_status`, `complimentary` · **G4** | Two reservation fields | **Covered** on mock data: two columns on `reservations`, set by the seed | **Blocked.** Neither exists in any captured response | **Ours:** G4 *BLOCKED* (plan-v3 §4) |
| **02 §7 · 03 §9** `guest.vip_status`; 03 §8 `companyId` · **G12b, G12c** | Two more fields | **Not covered** | **Blocked.** VIP exists only as Hebrew free text (1.5); no company entity anywhere in the API | **POC:** not stated. **Ours:** G12b, G12c *BLOCKED* |
| **02 §35 · 03 §19 PMS ID Mapping** - *"Do not assume room numbers can be used as cross-system identifiers."* · **G12d** | StayOps' own stable ids, mapped to provider ids | **Not covered.** Ids are seed strings (`room_a_101`) | **Deferred** | **POC:** not stated. **Ours:** G12d: *"a second source of truth that can disagree with the provider"* |
| **D · Evidence** | | | | |
| **01 §20 Evidence Requirement** - *"Each policy template declares the evidence it needs."* · 03 §20 registry | A registry of requestable fields; each template declares its own | **Not covered.** No registry. Each branch of `evaluateControl` reads the columns it needs | **Covered.** `spec/canonical_fields.json`, and every IR's `required_evidence`, checked by `tools.validate_spec` (1,098 checks) | **POC:** not stated |
| **01 §21 · 02 §39 Evidence Provenance** - provider, endpoint, `provider_path`, `retrieved_at` | Every value keeps its origin | **Partial.** `evidence(field, raw, value)` records `canonicalField`, `rawValue`, `normalizedValue`, `provider: "MOCK_MINIHOTEL"`, `endpoint: "mock://pms"`, `providerPath: field` (the canonical name, not a provider path), and `retrievedAt: now()`, the time of evaluation | **Partial.** A verdict cannot be built without evidence, and each value names its system and call (`pms:minihotel/GetReservationBalance`), raw and canonical values, and when it was obtained (`tests/unit/test_kernel_verdict.py`). Missing: the provider field path, withheld on purpose | **POC:** placeholders, because there is no PMS. **Ours:** `open-questions.md` §3: *"No PMS field path ever crosses"* the canonical boundary |
| **02 §38 Unknown Provider Values** - *"The system must not guess. The control becomes: UNKNOWN and the unmapped value is logged"* | UNKNOWN, and a log line | **Partial.** An unmapped room status becomes `"UNKNOWN"`, and nothing records it. The OOO check then compares `"UNKNOWN"` with `"OUT_OF_ORDER"`, finds them unequal, and the reservation is **PASS** | **Partial.** UNKNOWN naming the value, never a guess (`test_spec_tenant.py`; `tests/unit/test_demopms_transforms.py::test_an_unmapped_code_is_unknown_and_never_a_guess`). Missing: the log line | **POC:** not stated. **Ours:** G14 *TAKE, NARROWED* cut *"anything logged from inside a provider (it would name endpoints above the boundary)"* |
| **03 §22** `freshnessMinutes` | A freshness limit per field | **Not covered.** `retrievedAt` is the moment of evaluation | **Covered.** Freshness is declared per IR and computed per run, and evidence whose age cannot be established is stale (`hotelcontrols/runner/run.py`; `tests/unit/test_store_sqlite.py::test_a_run_that_never_knew_when_its_evidence_came_from_reads_back_stale`) | **POC:** not stated |
| **01 §29 Efficient Execution** - *"should not execute every control against every reservation on every cycle"* · 03 §48 | A bounded population | **Not covered.** Every template selects every reservation of the hotel (`WHERE r.tenant_id = ? AND r.hotel_id = ?`), then filters | **Covered.** A population query and a call budget that **raises** rather than truncating (`tests/unit/test_evidence_budget.py`; R1) | **POC:** not stated |
| **E · Providers** | | | | |
| **03 §12 Provider Adapter Interface** - `getReservations()`, `getRooms()`, `getPayments()` … · **G7** | One entity-method interface per PMS | **Not covered.** No adapter. The mock PMS is the POC's own `reservations` and `rooms` tables, read with SQL from inside the evaluator | **Covered, in another shape.** A field-resolution protocol (`hotelcontrols/providers/base.py`) with one contract suite over both providers (`tests/contract/test_provider_contract.py`). The entity-method shape is **Rejected on purpose** | **POC:** not stated. **Ours:** G7 *REJECT*: entity methods *"would hide the per-record call (R1) and force a value onto fields that are unknown with a reason"* |
| **03 §87 Architectural Rule to Protect** - *"Nothing above the normalization boundary should know whether the hotel uses MiniHotel, Mews, or another PMS."* | A hard boundary | **Partial.** Normalisation sits in the same file as the evaluator, and the room-upgrade query reads a raw provider value directly: `raw_status = 'Available'` | **Covered.** A grep test over the tree (`tests/unit/test_canonical_boundary.py`) | **POC:** not stated |
| **01 §16-17 · 03 §16-17 Normalization** | Provider values become canonical ones | **Partial.** Room status only, five values (`normaliseRoomStatus`) | **Covered.** Both adapters, their transform tests, and the shared contract suite | **POC:** not stated |
| **01 §56 · 03 §84 Phase 3 MiniHotel Adapter** | A real MiniHotel integration | **Not covered.** `provider: "MOCK_MINIHOTEL"` | **Covered.** Four capture labels, 20 real responses, pseudonymised (`tests/integration/test_minihotel_adapter.py`) | **POC:** its README says only that it *"uses only mock MiniHotel-style data"*; why, not stated |
| **03 §78 Mews Adapter** - *"Same policy + MiniHotel evidence and Same policy + Mews evidence produce equivalent canonical behavior."* · **G9** | A second, real PMS | **Not covered** | **Blocked.** No credentials. The fictional DemoPMS proves the seam instead (`tests/e2e/test_two_providers.py`) | **POC:** not stated. **Ours:** G9 *BLOCKED, out of v3* (owner; no credentials) |
| **03 §14 Provider Capabilities** | A boolean map per provider | **Not covered** | **Covered, finer.** Readiness per control × provider, per field (`test_runner_readiness.py`) | **POC:** not stated |
| **01 §64 Rate Limiting and PMS Protection** - *"limits should be applied per: tenant + provider"* · **G15** | Rate limits, retries, backoff and timeouts, per tenant and provider | **Not covered.** It calls no PMS | **Partial.** An opt-in transport with a token-bucket limiter and bounded retry (`tests/unit/test_transport.py`). Missing: per tenant and provider | **Ours:** G15 *DEFER*: *"nothing live to share yet"* |
| **01 §51 Provider Evolution** - *"mappings must be versioned"* | Versioned mappings | **Not covered** | **Partial.** Each provider map carries a `version` and a `verified_against` (`spec/providers/*.json`). Missing: choosing a mapping version at run time | **POC:** not stated. **Ours:** no document gives a reason |
| **03 §77 Provider Mapping Management** - *"developer-managed configuration. Do NOT build a customer-facing mapping UI."* | Mappings as configuration | **Partial.** The one map is a constant in code | **Covered.** `spec/providers/*.json`, every mapping checked against its capture by `tools.validate_spec` | **POC:** not stated |
| **01 §50 Error Handling** - *"Policy violation and: System failure … must not be presented as the same thing."* · 03 §76 | FAIL, UNKNOWN and execution errors kept apart | **Partial.** Missing data → UNKNOWN `MISSING_EVIDENCE`. Any thrown error → HTTP 500 *"Internal server error"*, and nothing is stored | **Covered.** FAIL, UNKNOWN and a *blocked* run are kept apart, stored and rendered differently (`test_store_sqlite.py::test_a_blocked_run_round_trips_with_its_reason_and_no_verdicts`; `tests/unit/test_web_routing.py::test_a_blocked_run_shows_no_tiles_and_says_why`) | **POC:** not stated |
| **F · Evaluation** | | | | |
| **01 §24 Deterministic Evaluation** | Same policy and evidence, same result | **Covered.** Plain conditions, no model | **Covered.** A pure evaluator with an injected clock (`tests/unit/test_evaluator_record.py`, `test_clock_is_always_injected.py`) | - |
| **01 §27 PASS / FAIL / UNKNOWN** - *"UNKNOWN must never automatically become FAIL."* | Three outcomes, and UNKNOWN never hardened | **Partial.** The three outcomes exist (no EXCLUDED), but: a guarantee status left at its default `'UNKNOWN'` is **FAIL**; an unmapped room status is **PASS** (row above); a record outside a control's scope is **PASS** (*"Reservation is outside the arriving scope."*). All 21 results in `poc.db` are PASS or FAIL | **Covered, and a fourth outcome.** EXCLUDED is separate from PASS, and every run carries a coverage verdict (`tests/unit/test_runner_coverage.py`, `test_kernel_verdict.py`) | **POC:** not stated. **Ours:** EXCLUDED goes beyond the documents; question 1.12 asks the manager to adopt it |
| **03 §50 Control Result** - `result`, `entityId`, `reasonCode`, `explanation`, `evidence` | A per-record result | **Covered.** `result(reservation, status, reasonCode, explanation, evidenceItems)`, stored in `execution_results`. A room is reported with `entityType: "RESERVATION"` | **Covered.** One verdict per record, with its reason and evidence | - |
| **01 §33 · 03 §51 Guest Service Decisions** - `APPROVED`, `APPROVED_WITH_FEE`, `DENIED`, `STAFF_REVIEW`, `UNAVAILABLE` | Five decisions | **Covered.** `POLICY_CATALOG.decisions` | **Covered.** The same five (D15), enforced by a `CHECK` on the `decisions` table | - |
| **03 §51** `fee?: Money` · 03 §33 hourly fee | The fee is money | **Partial.** The fee is a JS number stored `REAL`, computed as `Math.max(1, Number(requested.slice(0, 2)) - Number((p.chargeFrom \|\| freeUntil).slice(0, 2))) * amount`: whole hours from the hour digits only, so 15:30 counts as one hour | **Covered.** `fee_per_hour` × hours rounded by the hotel's stated `hour_rounding`, as Money (`hotelcontrols/guest/fee.py`; `test_guest_decide.py::TestTheDefinitionOfDone`) | **POC:** not stated |
| **03 §79 Testing Matrix** - *"Missing evidence → STAFF_REVIEW / UNAVAILABLE"* | A guest decision never rests on missing evidence | **Not covered.** Late checkout reads no reservation: `reservationId` is checked for access and then unused. A request with no time in it is read as 15:00 (`Number(time[1] \|\| 15)`) | **Covered.** Blanking any one evidence field or parameter yields `STAFF_REVIEW` naming it (V10; `TestNeverWidened`, `tests/unit/test_guest_evidence.py`) | **POC:** not stated |
| **G · The guest templates** | | | | |
| **03 §33 LATE_CHECKOUT** · 02 §30 evidence `reservation.departure_date`, `reservation.status` · **G3a** | Time rules and a fee, checked against the reservation | **Partial.** Time rules and a fee. Missing: the reservation evidence 02 §30 names | **Covered.** Eleven rules, approved by the owner before any code (`spec/guest/late_checkout.json`; V9). On the shipped properties the policy is undecided, so every request is `STAFF_REVIEW` and says so | **POC:** not stated |
| **03 §34 EARLY_CHECKIN** - 02 §20: *"if room is ready → free"* · **G3c** | Time rules plus room readiness | **Partial.** Time rules only; room readiness is not read | **Deferred** | **POC:** not stated. **Ours:** G3c: *"which code means ready is per property and unestablished … Built today, every request would be STAFF_REVIEW"* |
| **03 §35 ROOM_UPGRADE** - evidence *"availability, rate"* · **G3d** | Availability and a rate difference | **Partial.** "Available" means a room of that category with `active = 1 AND raw_status = 'Available'`, for no date range. The fee is a fixed amount, not a rate difference | **Blocked** | **POC:** not stated. **Ours:** G3d: *"no availability entity; the ARI key space is not the rate-code key space (R13)"* |
| **03 §36 EXTRA_TOWELS** · **G3b** | Quantity limit, charge, a service request | **Covered, generalised.** `EXTRA_ITEM_REQUEST`, with `itemName`, `freeQuantity`, `maximumQuantity` and `chargeType`. `EXTRA_TOWELS` is accepted as an alias | **Deferred** | **Ours:** G3b: *"not before one template has proved the path"* |
| **03 §37 MAINTENANCE_REQUEST** - *"a small controlled list of categories and priorities"* · **G3b** | Classify and route | **Covered.** A category → priority → department table; the decision is always `APPROVED` | **Deferred** | **Ours:** G3b, and the classification *"must be a pick-list or staff-confirmed, never a model's choice (D10)"* |
| **02 §22-23 · 03 §42 Guest intent** - *"The LLM identifies intent; the policy engine makes the decision."* Unknown intent → `UNSUPPORTED_REQUEST`, `requires_staff` | Prose → registered intent; anything else goes to staff | **Partial.** `extractGuestIntent` is keyword matching, with no model. An unmatched request becomes `UNAVAILABLE`, with actions that escalate to staff. In the UI, the template picked in the form overrides whatever was extracted. One stored row, consistent with the code as read: *"Can I request 2 additional soap?"* → *"1 Soap approved."* (no item keyword matched, so the quantity defaulted to 1) | **Rejected on purpose.** The request arrives structured, as a reservation and an HH:MM | **POC:** not stated. **Ours:** D12: *"a model extracting the requested time from prose would put natural language in the decision path, where a misread '3' prices a fee"* |
| **H · Execution** | | | | |
| **01 §28 · 03 §55 Execution modes** - `EVENT`, `HOURLY`, `DAILY`, `MANUAL` · **G10a, G10d** | Run on events and on a schedule | **Partial.** Manual `/execute`, and a simulated PMS event (`POST /api/hotels/:hotelId/pms-events`) that runs every `ACTIVE` control. A `schedule` column is stored, and nothing reads it | **Partial.** Manual runs (`/run/<control_id>`, `GET /api/run/<control_id>`; the React UI runs one only from a button, D11). `next_evaluation()` computes when each control would run (`tests/unit/test_runner_scheduling.py`, `/api/plan`), and nothing runs it | **POC:** not stated. **Ours:** scheduler G10a *DEFER* (live evidence and MiniHotel's agreed limits, 2.6); webhooks G10d *BLOCKED* (no webhook payload ever observed) |
| **01 §42 · 03 §58 Queue Architecture** · 01 §63 · **G10b** | A job queue and workers | **Not covered** | **Deferred** | **POC:** not stated. **Ours:** G10b: *"unneeded below a few hundred properties"* |
| **01 §65 · 03 §57 Idempotency** - *"should not result in two service requests because the API call was retried"* · **G10c** | Idempotency keys on executions and actions | **Partial.** Creating a control identical to an `ACTIVE` or `READY` one returns the existing one (`deduplicated: true`). A guest request posted twice is stored twice, with two action lists | **Partial.** A task's natural key makes a FAIL raise one task however often it re-runs (V5), and a double submission makes one decision (`TestOneDecisionPerDoubleSubmission`). Missing: job-level keys | **POC:** not stated. **Ours:** G10c *TAKE, NARROWED*: job-level keys *"belong with G10a"*; `run_id` unchanged (plan-v3 §6.6) |
| **03 §59 Result Storage** - `tenant_id`, `execution_id`, `policy_id`, `policy_version`, `provider` … | Results that name tenant, version and provider | **Partial.** `execution_results` carries tenant, hotel, execution, control, entity, result, reason and explanation. Missing: version and provider | **Covered.** Runs store property, provider, version and digest (`tests/unit/test_store_sqlite.py`) | **POC:** not stated |
| **03 §60 Evidence Storage** | Provenance stored per result | **Covered.** `execution_results.evidence_json`, holding the placeholders noted under *Evidence Provenance* | **Covered.** Evidence round-trips through the store (`test_store_sqlite.py`) | - |
| **01 §66-67 Auditability** - *"What policy was used? What version? … Why did the evaluator produce this result?"* | A retrievable trace | **Partial.** Explanation and evidence are kept per result, with no version | **Covered.** Rule, version, evidence and the reason for each verdict, per stored run | **POC:** not stated |
| **I · Multi-tenancy and security** | | | | |
| **01 §46 · 03 §5** - *"All tenant-owned tables contain: tenant_id"* · **G5** | `tenant_id` on every tenant-owned record | **Covered.** Every table except `tenants` itself has `tenant_id NOT NULL` (`initialiseDatabase`) | **Covered.** Slice 17 (`tests/unit/test_tenant_scoped_store.py`) | - |
| **01 §44 Security Boundary** - *"A developer should not be able to accidentally write: SELECT * FROM controls"* · 03 §7 tenant-aware repositories | Scoping that cannot be forgotten | **Partial.** 20 lines of SQL carry `tenant_id = ?`, written by hand, and nothing checks them. One write filters by id alone (`UPDATE controls SET status = 'ACTIVE', updated_at = ? WHERE id = ?`); it is safe only because the read before it is scoped | **Covered.** Store reads take `tenant_id` keyword-only, and a structural guard checks every SQL statement (V4; `test_tenant_scoped_store.py`) | **POC:** not stated |
| **01 §45 · 03 §6 Tenant Context** - *"Never accept an arbitrary tenant ID from the browser and trust it."* | The tenant comes from authentication | **Deferred by its author, in the code:** an `x-tenant-id` header, with the comment *"This POC deliberately uses an explicit tenant header rather than authentication. A production implementation replaces this with the authenticated tenant context."* | **Covered** when a secret is configured: the host signs an HMAC tenant context and `_authenticate` overwrites `property` before any route runs (V11; `tests/integration/test_host_auth.py`). With no secret the engine is the single-operator demo, and `?property=` selects | **Ours:** D14 |
| **01 §62 · 03 §80 Tenant Isolation Tests** - *"These are mandatory … directly through APIs, not only through the UI."* | Cross-tenant attacks, tested | **Not covered.** No tests. And by reading (not run): `broadcast()` sends every event to every connected socket (`for (const client of socketServer.clients) if (client.readyState === 1) client.send(message)`), and the `/ws` connection handler checks no tenant. Nothing in the code stops Hotel B's screen from receiving Hotel A's executions and guest requests | **Covered.** `tests/integration/test_tenant_isolation_api.py`, `test_host_auth.py::TestAsContextCannotReadBsAnything` | **POC:** not stated |
| **01 §56 · 03 §73** - *"secure API authentication"* | Users log in | **Not covered** (the header above) | **Partial.** The engine verifies; the host authenticates. `ui/`'s sign-in *"is a development stand-in, and says so on its page"* (`ui/README.md`) | **Ours:** D14: *"The host product authenticates; the engine verifies"* |
| **03 §74 Role Model** - `HOTEL_ADMIN`, `HOTEL_MANAGER`, `HOTEL_STAFF` | Three roles | **Not covered** | **Deferred** | **POC:** not stated. **Ours:** G5 *TAKE, NARROWED* cut *"roles beyond one signed context"*; plan-v3 §8 |
| **01 §14 · 03 §15 PMS Connection** - *"credentials = encrypted/securely stored"*, never shared between tenants | Per-tenant, encrypted credentials | **Not covered.** There is no PMS connection | **Partial.** Per property, from the environment, with no fallback (#22; `test_transport.py::TestCredentialsArePerProperty`). Missing: encryption | **Ours:** D14: *"Encrypted credential storage is deferred"* |
| **01 §13 Hotel Onboarding** · 03 §63 PMS Connection APIs · **G11** | Connect, test and discover a PMS | **Not covered** | **Deferred** | **POC:** not stated. **Ours:** G11 *TAKE, NARROWED*: connect, test and discover are each a live call (D3); the rest *"returns with a pilot property (1.9)"* |
| **01 §48 Hotel Groups** - *"this is not required for the first release"* | An organisation over hotels, later | **Covered in shape.** `tenants` own `hotels`, and every route is `/api/hotels/:hotelId/…`, checked by `scopedHotel` | **Deferred** | **Ours:** deferred by 01 §48 itself; G5 cut *"the Organisation→Hotel hierarchy"* |
| **03 §85 First Week Deliverable** - *"these must work for: Hotel A, Hotel B"* · 01 §74 | Two hotels, one codebase, isolated | **Covered** on mock data: two tenants with different policies in `poc.db` | **Covered.** Two shipped properties plus test properties; one IR, two hotels, different verdicts (V8). 01 §74's *"Hotel B, Mews"* is **Blocked** (G9) | **Ours:** G9 |
| **J · Actions and notifications** | | | | |
| **01 §34 · 03 §71 Action Architecture** - `SEND_EMAIL`, `CREATE_SERVICE_REQUEST`, `CREATE_MAINTENANCE_REQUEST` … | A decision produces actions | **Partial.** `actionsForDecision` returns action *names*, stored in `guest_requests.actions_json`. Nothing performs them, and they have no state | **Partial.** An action is an advisory **record with a state** (`pending`, `done`, `dismissed`) that a person performs: one per failed record, one per guest decision except `DENIED` (`tests/integration/test_findings_queue.py`, `tests/unit/test_actions_records.py`). Writing to a PMS is **Rejected on purpose** | **POC:** not stated. **Ours:** G2(b) *REJECT*, question 1.10 (a), `prd.md` §6 *"Read-only, permanently"* |
| **02 §44 · 03 §72 Notifications** - *"First implementation: Email"* · **G8** | Email on FAIL | **Not covered.** Events go to an `event_stream` table and a WebSocket broadcast | **Covered.** Opt-in behind two locks: one email per record, none for a run that concluded nothing (V6; `tests/integration/test_email_dispatch.py`). A guest task is not emailed (1.10) | **POC:** not stated |
| **02 §44** `STAFF_REVIEW → Staff queue` · 03 §70 Guest Request UI, *"For staff"* | A staff queue | **Partial.** The UI lists the hotel's three latest guest requests, with decision, escalation and actions. The requests have no queue state | **Covered.** `/queue` for violations and `/guest` for guest tasks, each task movable by a person (slices 18, 22). The React guest view is deferred (1.10) | **POC:** not stated |
| **01 §34** *"Respond to guest"* · 02 §47 *"Would you like me to arrange this?"* · 03 §62 `/confirm` | A response to the guest, and a confirm step | **Partial.** An `explanation` sentence and a `RESPOND_TO_GUEST` action name. No confirm route, and nothing reaches a guest | **Rejected on purpose** | **Ours:** plan-v3 slice 22, *Not*: *"a guest-facing screen (staff see decisions; how a guest is answered is the host product's)"* |
| **K · API and screens** | | | | |
| **01 §45 · 03 §61 Controls API** - create, get, validate, activate, pause, execute, results | Eight routes | **Partial.** List, create, activate, execute and results. Missing: get by id, validate, pause | **Partial.** Run, stored run, readiness, history, list, plan and compose. Missing: create, validate, activate, pause | **POC:** not stated. **Ours:** G13 *DEFER*: *"the write half manages objects that do not exist yet (lifecycle, G6c) and needs an authorised caller"* |
| **03 §62 Guest Service APIs** | Policy CRUD with validate and activate, and requests with confirm | **Partial.** List and create policies; create and list requests | **Partial.** `POST /api/guest/requests`, `GET /api/guest/decisions` and one decision by id. Policies are files (`spec/guest/`, `spec/tenants/`), with no API | **Ours:** G13, above |
| **01 §49 · 03 §75 Observability** - logs carrying `tenant_id`, `execution_id`, `policy_version`, `provider` … | Structured logs | **Not covered.** `console.error(error)` in the error handler. The `event_stream` table feeds the on-screen activity list; whether it was meant as a log is not stated - UNVERIFIED | **Partial.** A JSON operational log, one record per request, run and dispatch (`tests/integration/test_operational_log.py`) | **Ours:** G14 *TAKE, NARROWED*: *"Cut: metrics, external sinks, and anything logged from inside a provider"* |
| **01 §49** *"Do not log: PMS credentials, unnecessary guest PII"* · 03 §73 | A rule about what may be recorded | **Not covered.** There is no such rule. `event_stream.payload_json` keeps each guest request whole, guest text included, and `broadcast` sends it out. There are no credentials to leak | **Covered.** No log record contains a credential or guest PII, checked over every record of a full run (V7). The same holds for email (V6) | **POC:** not stated |
| **02 §45 · 03 §69 Control Results UI** - *"Clicking a failure displays the evidence."* | Results with evidence | **Covered.** The *Audit evidence* panel shows each result with its evidence (`main.jsx`) | **Covered.** Both screens; every verdict traces to its fields (`tests/integration/test_web_pages.py`; the UI's own suite) | - |
| **02 §45 MVP UI** - *"8 Active · 1,284 Passed · 17 Failed · 6 Unknown"* | A four-tile dashboard | **Partial.** Tiles for active controls, guest policies and guest requests, plus *Connection: Live*, a hard-coded string. No pass or fail counts | **Rejected on purpose, as drawn.** Count tiles include EXCLUDED and a coverage line, and a run that concluded nothing shows no tiles | **Ours:** question 1.12: drawn faithfully, a run where every record was out of scope reads as a clean bill of health |
| **02 §45 · 03 §66 Create Control UI** - *"What should StayOps check?"*, then *Data required*, *Frequency*, *[Activate]* | Prose in, understanding shown, activate | **Partial.** Pick one of five templates, then *Activate control*. No text box, no data-required list, no frequency | **Partial.** The compose window takes prose and shows the sentence it understood (D10). No template form, no activate button | **POC:** not stated. **Ours:** D10; G6c |
| **02 §46 · 03 §67 Guest Policy UI** | A form per template | **Covered.** `PolicyBuilder`: one form per template, with its parameters and *Activate … policy* | **Not covered.** Policies are files | **Ours:** G13 (admin UI) *DEFER* |
| **01 §62 Testing Strategy** - unit, provider contract, tenant isolation, end-to-end | Four levels of tests | **Not covered.** No test file anywhere in the tree | **Covered.** 3,378 passing across unit, integration, contract and end-to-end, plus the React UI's 249 component and 26 browser tests | **POC:** not stated |
| **L · The definitions of done** | | | | |
| **02 §49 Definition of Done, control** - *"MiniHotel: Out Of Order ↓ StayOps: OUT_OF_ORDER ↓ Control: FAIL"* · 02 §11 | An OOO room with an arrival fails | **Covered** on mock data: the seeded room `"Out Of Order"` → `FAIL`, `OOO_ROOM_ASSIGNED` (three such rows in `poc.db`) | **Covered** as `ooo_room_protection`. The FAIL is proven offline on both providers against a stand-in room master (`tests/integration/test_closed_room_never_passes.py`). **On every real capture: 28 EXCLUDED, no conclusion**, because no room has ever had a closed-date window (2.4). It reads MiniHotel's closed-date window rather than a status string; no document records why that field was chosen. `room_assignment_active_room` sees the same window from the reservation side, and is 372 EXCLUDED on the covering capture | - |
| **02 §49 Definition of Done, guest** - *"Requested: 15:00 … Decision: APPROVED_WITH_FEE, Fee: $25"* | 15:00 → `APPROVED_WITH_FEE`, $25 | **Covered** on mock data: `poc.db` holds *"Can I check out at 3 PM?"* → `APPROVED_WITH_FEE`, fee `25.0`. No currency, no reservation read | **Covered** (V9): 15:00 → `APPROVED_WITH_FEE`, `25.00 USD` as Money, both sides of both thresholds (`TestTheDefinitionOfDone`, unit and integration). The request is structured, not *"Can I check out at 3?"* (D12) | - |
| **03 §86 Definition of Done** - *"A hotel administrator can connect a PMS, express a supported hotel control or guest-service policy in natural language, review what StayOps understood, activate it, and have StayOps automatically obtain normalized PMS evidence and deterministically evaluate the policy within that hotel's isolated SaaS tenant."* | The whole path | **Partial.** Isolated by header, deterministic, on mock evidence. No PMS connection, no prose in the UI, no automatic runs | **Partial.** Real normalised evidence, deterministic, isolated in auth mode, prose via compose drafts. No connection, no activation, no automatic runs | Rows G11, G6c and G10a above |
| **03 §86, second half** - *"Adding another PMS requires implementing the provider adapter and mappings, not rewriting the controls or guest-service policies."* | Portability | **Not covered.** No adapter exists to add another beside | **Covered.** DemoPMS was added as one adapter and one map; one contract suite runs against both providers (`tests/contract/`) | **POC:** not stated |

The constraints StayOps puts on the team (01 §55 *"not an integration platform"*, 01 §57 *"What
Should Not Be Built Initially"*, 01 §58 *"work vertically"*) describe how to build rather than
features to build, so they have no rows. Neither build crosses any of them: no customer scripting, no
model-decided verdict, no integration catalogue.

---

## 4. Where the POC goes further than we do

Everything below is on mock data. That limits it as evidence, but the shape is real.

- **Guest-services breadth.** Five templates, each end to end: catalogue, parameters, decision,
  escalation, action names. We have one (G1 narrowed; the other four are G3b, G3c and G3d).
- **Item requests generalised.** `EXTRA_TOWELS` became `EXTRA_ITEM_REQUEST`, configured by
  `itemName`, `freeQuantity`, `maximumQuantity` and a `chargeType` of `NONE`, `FIXED` or `PER_ITEM`.
  It is wider than the documents ask, and the code keeps `EXTRA_TOWELS` as an alias.
- **Escalation as a parameter.** A hotel picks what happens past a limit: `DENY`, `STAFF_REVIEW`,
  `MANAGER_REVIEW`, `FRONT_DESK_REVIEW` and others. The documents have no such parameter. In code,
  every escalation except `DENY` (→ `DENIED`) and `NONE` (→ `UNAVAILABLE`) becomes `STAFF_REVIEW`.
- **A catalogue as the product contract.** `GET /api/policy-catalog` serves every template, its
  parameters and defaults, the decisions and the action types. A comment above it says *"UI clients
  render these supported choices; they never construct their own conditions, actions, or escalation
  flows."*
- **A guest-policy form** (`PolicyBuilder`) and a **create-control button**. We have neither (G13).
- **A lifecycle, even a thin one**: `READY` → `ACTIVE` through `/activate`. Ours is deferred (G6c).
- **Event-triggered runs and a live feed.** `POST …/pms-events` simulates a room-status change,
  creates the room if it is new, re-runs every active control, and pushes the result to the screen
  over a WebSocket. We compute when a control *would* run and never run it unattended (G10a); the
  POC's feed is also where its isolation leaks (§3, group I).
- **Hotels grouped under a tenant**, the shape 01 §48 says not to build yet. We defer it.

## 5. Where we go further than the POC

- **Real evidence, and the seven facts it taught us.** None of them reached the POC, and how its
  code would meet each one is established here by reading:

  | Fact (`CLAUDE.md`) | What the POC's code would do with it |
  | --- | --- |
  | R9 · a reservation and its folio in different currencies | Money has no currency, so the mismatch cannot even be seen |
  | R10/R12 · capacity `0` means unconfigured | `count > room_capacity`: every occupied room with capacity `0` is **FAIL** |
  | R3 · `createDateTime` is date-only | Not used; dates are compared as `YYYY-MM-DD` strings |
  | R13 · room-type codes differ in case | Category lookup is an exact `category = ?`, and the status map is case-sensitive |
  | R7 · an OTA modification is cancel plus recreate | There is no duplicate-reservation control |
  | R1 · one balance call per reservation | No folio, no balance, no call cost |
  | Negative checked-out folio | No folio |
  | `OK4` / `WL`, documented nowhere | A reservation is "arriving" unless its status is `CANCELLED` or `CHECKED_OUT`, so either code would be treated as a live arrival |

- **EXCLUDED and the coverage verdict.** The POC reports an out-of-scope record as PASS. We report it
  as EXCLUDED, and a run that concluded nothing shows no count tiles (question 1.12).
- **UNKNOWN is never hardened.** In the POC an unknown guarantee status FAILs and an unmapped room
  status PASSes. Ours stays UNKNOWN with its reason; for guest services, `STAFF_REVIEW` names
  what was missing (V10).
- **The hotel's own calendar.** The POC stores each hotel's time zone (`Asia/Kolkata`,
  `Europe/London`) and never reads it. "Today" is the server's UTC date
  (`new Date().toISOString().slice(0, 10)`). Ours resolves every date through the property clock,
  enforced by a test over the engine.
- **Money, a bounded population, a call budget that raises**, provenance kept per value, freshness
  that is computed, and a canonical boundary held by a test (§3, groups C to E).
- **Rule versions** on every run and every guest decision (G6b).
- **Isolation that is verified.** A signed tenant context, a structural guard on every query, and
  the mandatory isolation tests through the API (G5).
- **Eleven controls**, seven of them beyond StayOps' five, including two shapes no StayOps template
  can express: a check across records (duplicate channel reservations) and interval overlap (two
  reservations in one room). `docs/stayops-gap-analysis.md` §5.6 explains why.
- **Email, an operational log and an action queue with state**, each with its locks and tests
  (G8, G14, G2(a)).
- **Tests.** The POC has none, so none of its behaviours is pinned down; every claim about it here
  comes from reading.

## 6. What neither covers

Each item below is a StayOps requirement that **neither** build meets. That says something about the
specification as well as the builds: much of it needs data no captured MiniHotel response holds, or a
live system neither build was allowed or able to use.

| StayOps requirement | Why it is open, on both sides |
| --- | --- |
| Payment guarantee on real evidence (02 §10) | The POC typed the field into its mock. We have never seen it in a capture (G4; and the card on file is a placeholder, #48 / 2.8) |
| Room upgrade on real availability (03 §35) | The POC uses its own `rooms` table for no date range. We have no availability entity (G3d, G12a) |
| VIP status and company id (02 §6-7) | Neither has them; for us they are blocked on the evidence (G12b, G12c) |
| A full lifecycle, with activation gated on validation (01 §25, 03 §46) | The POC activates without checks; ours is deferred (G6c) |
| A scheduler, a queue and workers (01 §41-42) | Neither runs anything unattended (G10a, G10b) |
| Roles (03 §74) | Neither has users with roles |
| Encrypted per-tenant PMS credentials, and connection and onboarding APIs (03 §15, §63; 01 §13) | The POC connects to nothing; ours are environment-only and deferred (D14, G11) |
| Mews (03 §78) | Neither has credentials or an adapter (G9) |
| Stable StayOps ids (03 §19) | Neither has them (G12d) |
| Mapping versions chosen at run time (01 §51) | Neither has it |
| A response that reaches the guest, and a confirm step (02 §47; 03 §62) | The POC writes a sentence; we leave it to the host product |
| 03 §86's Definition of Done as one path | Connect → prose → review → activate → automatic evaluation is not complete in either |

## 7. Where the three documents disagree, and how each build chose

`docs/stayops-gap-analysis.md` §6 lists nine places where the documents contradict each other.
Open question 1.11 records which ones the owner has ruled on. Re-checked against the documents
themselves:

| # | The disagreement | The POC chose | We chose |
| --- | --- | --- | --- |
| 1 | Guest decisions: four, with `NEEDS_STAFF_REVIEW` (02 §1), or five, with `STAFF_REVIEW` (01 §33, 02 §25, 03 §51) | Five, `STAFF_REVIEW` (`POLICY_CATALOG.decisions`) | The same five (D15) |
| 2 | Late-checkout parameter names: 02 §19, 02 §31 and 03 §33 each give a different set, and 03 §65 adds `staffApprovalAfter` | Two sets at once. The seeded policy uses 03 §33's (`normalCheckout`, `freeUntil`, `maximumTime`, `chargeFrom`, `hourlyFee`), and the catalogue's defaults use a fifth set found in no document (`normalCheckoutTime`, `chargeType`, `chargeAmount`, `maximumAutomaticTime`, `escalationAfterMaximum`). The evaluator reads either: `p.maximumAutomaticTime \|\| p.maximumTime`, `p.chargeAmount ?? p.hourlyFee` | 02 §31's names in snake_case, plus `fee_per_hour` as Money and `hour_rounding` with no default (D15) |
| 3 | The worked example: *"up to 3 PM; after noon charge $25"* (02 §1) against *free until 2 PM, $25/hour to 4 PM* (everywhere else) | Only the second, as seeded data and catalogue defaults | Both, as two properties' parameters with their own expected answers (dissolved, not ruled) |
| 4 | Enums have no `UNKNOWN` member against the never-guess rule (02 §9 and 03 §11 against 02 §38) | 03 §11's: room status falls back to `"UNKNOWN"`; reservation status has no such member | `UNKNOWN` for any status nobody named (1.12, carried to the manager) |
| 5 | The guarantee exception: an array `["COMPLIMENTARY"]` (02 §10) or a boolean `complimentaryException` (03 §28) | 03 §28's boolean, although the evaluator never reads it: `if (!due \|\| reservation.complimentary)` | Not ruled; the control is blocked (G4) |
| 6 | Room capacity: no parameters (02 §12) or `{"maximumGuests": "ROOM_CAPACITY"}` (03 §30) | 02 §12's: `fields: []` | No parameter. Per-guest-type maxima, because that is all MiniHotel exposes |
| 7 | Is `INACTIVE_ROOM_ASSIGNMENT` its own template (01 §8, 03 §26) or a case of `ROOM_ASSIGNMENT_STATUS` (02 §14)? | Its own, and it also treats an *out-of-order* room as unavailable, so OOO rooms fail it too (seven `INACTIVE_ROOM_ASSIGNED` FAILs in `poc.db`) | Separate controls (`inactive_room_future_stay`, `ooo_room_protection`) |
| 8 | Money: a bare number (02 §6) or `Money` (03 §8) | 02 §6's bare number | 03 §8's `Money` |
| 9 | Build order: 02 §48 never mentions tenancy; 03 §5 puts it before the policy engine; 03 §88 says *"resist the temptation to build a platform before proving the product"* | UNVERIFIED. The tree has no history to read an order from | Data isolation early, authentication last (D13) |

---

*Not a plan.* What, if anything, to take from either build is the owner's decision, and
nothing here pre-empts it.
