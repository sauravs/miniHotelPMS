# Old-Codebase Review — `miniHotelLegacy` → v2

**Reviewer:** engineering review of the v1 codebase, prior to re-implementation.
**Date:** 2026-09-08
**Subject:** `miniHotelLegacy/` — PMS-agnostic hotel control rule engine, four silos, 152 tests.
**Purpose:** decide what v2 keeps, what it fixes, and what it adds. Nothing here is a criticism of
a demo that met its own stated goals; it is a list of what stops that demo becoming a product.

---

## How this review was done

Four passes, deliberately in this order — the same method v1 itself used, and for the same reason.

| Pass | What it looked at |
| --- | --- |
| 1 · Requirements | `Hotel Controls.docx` (20 controls), `control_rule_architecture.docx` (25 sections), `initial_requirement.md` |
| 2 · Documents | `CLAUDE.md`, `prd.md`, `context.md`, `architecture.md`, `plan.md`, `open-ques.md`, `QA.md`, `CONTROL_DRY_RUN.md`, the feasibility workbook |
| 3 · Code | all 4,286 lines of `engine/` and `tests/`, plus `spec/` (52 fields, 10 IRs, 880 validation checks) and the 14 frozen `probe/` responses |
| 4 · **Execution** | ran the suite (152 pass), ran `validate_spec.py` (880 pass), **ran all 10 controls against all 3 evidence sets**, and wrote throwaway probes to try to break the resolver |

Pass 4 is where the important findings came from. Every claim below that says "measured" was
produced by running the v1 code, not by reading it — which is v1's own house rule, applied to v1.

---

## Verdict in one paragraph

**The architecture is right and the engineering discipline is unusually good.** The canonical
boundary, the three-valued verdict, `Value` refusing to compare across currencies, `EXCLUDED` as a
fourth outcome, the call budget that raises rather than truncates, evidence-carrying verdicts, and
"if the docs and a frozen response disagree, the response wins" are all correct and all worth
keeping verbatim. **What v1 does not have is reach.** Measured across every control it ships and
every body of evidence it has, **exactly one of ten controls ever produces a PASS or a FAIL.** The
other nine are blocked, universally excluded, or universally unknown — not because the hotel data
is missing, but because three capabilities were scoped out of the demo and every remaining control
needs at least one of them. v2's job is to keep the design and close that gap.

---

## Measured baseline — every control, every evidence set

Produced by running v1 itself. `P/F/U/X` = PASS / FAIL / UNKNOWN / EXCLUDED.

| Control | 2026 capture | 2024 capture | synthetic | Actionable? |
| --- | --- | --- | --- | --- |
| `open_balance_at_checkout` | P1 F1 U0 X0 (n=2) | n=0 | P1 F1 U1 | **YES** |
| `duplicate_channel_reservation` | P0 F0 **U14** X26 | U1 X6 | X3 | no — `count_lte` unimplemented |
| `ooo_room_protection` | P0 F0 U0 **X28** | X28 | blocked | no — 100% excluded |
| `rate_room_category_consistency` | P0 F0 **U111** X0 | n=0 | n=0 | no — no rate-plan join (R13) |
| `required_reservation_fields` | P0 F0 **U37** X71 | n=0 | n=0 | no — no rate codes nominated |
| `room_assignment_active_room` | P0 F0 **U111** X0 | n=0 | n=0 | no — `within` unimplemented |
| `room_assignment_type_validity` | P0 F0 **U111** X0 | n=0 | n=0 | no — no room-master join |
| `room_capacity_compliance` | P0 F0 **U111** X0 | n=0 | n=0 | no — no room-master join |
| `inactive_room_future_stay` | **blocked** | blocked | blocked | no — record boundary |
| `resource_occupancy_consistency` | **blocked** | blocked | blocked | no — record boundary |

**1 of 10 controls answers. 0 of 20 source controls beyond that one.** Every failure traces to one
of exactly three missing capabilities — F1, F2 and F3 below — which is good news: three pieces of
work unlock nine controls.

---

## What v1 got right — carry these into v2 unchanged

These are not up for redesign. They are the reason v2 is a re-implementation rather than a rewrite
from the requirements.

| # | Kept | Why it must survive |
| --- | --- | --- |
| K1 | **The canonical boundary** — no PMS identifier above Silo 1 | The entire PMS-agnostic thesis. Enforced by a grep test that has already caught prose twice |
| K2 | **UNKNOWN as a first-class outcome, with a reason** | The product's differentiator. "Never widen a verdict" is the single most important rule in the repo |
| K3 | **`EXCLUDED` as a fourth outcome** | Folding it into PASS inflates every compliance number with records nobody checked |
| K4 | **`Value` = `known(v, unit) \| unknown(reason, risk)`**, money carrying its currency, comparison across currencies *raising* | R9 is real: reservation `007003199` is 870 USD, its own folio is 3262.5 ILS, no FX anywhere |
| K5 | **`spec/` is data the engine reads at runtime** | An eleventh control is a file, not a branch. This claim is proven in v1 and must stay proven |
| K6 | **The call budget raises, never truncates** | A truncated population silently answers a different question (R1/R8) |
| K7 | **A `Verdict` cannot be constructed without evidence or a reason** | Audit is the product; this makes it structural rather than a convention |
| K8 | **Frozen fixtures are the test set; no test touches the network** | Deterministic, free, and honours R8 |
| K9 | **Kleene three-valued logic in `all`/`any`/`none`** | Correct, and correctly tested in both directions |
| K10 | **High comment density citing risk ids** | This codebase explains *why*. Rare and valuable — v2 raises the bar, not lowers it |
| K11 | **`validate_spec.py` — 880 checks over spec + fixtures** | It has already caught two claims that were wrong about the data |
| K12 | **Honest documentation** — `open-ques.md` records what is unverified as unverified | The Pass-3 correction ("the sandbox had moved on") is a model of how to be wrong well |

---

## Findings

Ranked by impact on the product, not by effort. Severity: **S1** blocks the product ·
**S2** blocks a control or a claim · **S3** correctness or maintainability risk · **S4** polish.

---

### F1 · S1 — No reference stage: a record can never be joined to property-wide data

**What.** Silo 2 fetches the population, then one follow-up call *keyed by the record*. Any field
whose evidence lives in a property-wide response (the room master, the room-type master, ARI)
returns UNKNOWN with the reason *"its source answers for the whole property and this population
plan performs no join"* (`population.py:_fetch_follow_up`).

**Evidence (measured).** `room_assignment_type_validity`, `room_capacity_compliance` and
`room_assignment_active_room` each return **111 UNKNOWN out of 111 records** against the 2026
capture. Not one answer. The evidence they need — `room.type`, `room.max_guests.adults`,
`room.closed_from` — sits in `getRooms`, which was already fetched or could be fetched **once** for
the whole property.

**Impact.** Controls 1a–1c, 1d, 2, 4, 9 and 13 — six of the twenty source controls, and the largest
single block of "Yes"-rated feasibility in the workbook — cannot answer. The cost of fixing it is
**one extra call per run**, not per record.

**v2 action.** A first-class **reference stage**: the IR declares reference sets it needs
(`{entity: room, key: room.number}`); the engine fetches each once per run, indexes it by canonical
key, and exposes it to the evaluator as a resolvable set. Joins become declarative and testable,
and a *missing* key still resolves to UNKNOWN — the join must never invent a match.

---

### F2 · S1 — No cross-record evaluation: set and aggregate operators are all UNKNOWN

**What.** `within`, `not_within`, `overlaps`, `count_lte` and `assertion.mode: "aggregate"` are
declared in the IR schema, used by four shipped controls, and implemented by none. They resolve to
UNKNOWN "saying exactly that".

**Evidence (measured).** `duplicate_channel_reservation` — the whole point of which is to find two
records sharing one confirmation number — returns **14 UNKNOWN, 26 EXCLUDED, 0 answers**, despite
the sandbox containing a *confirmed live example* of the pattern (portal id `test0000000N1` shared
by `007003206` and `007003207`, documented in `transforms.py`). The engine holds the evidence of a
real duplicate and cannot say so.

**Impact.** Controls 14 and 20 cannot answer at all; 1d and 2 lose their date-window operator.

**v2 action.** Split evaluation into two shapes rather than forcing one:
`evaluate_record(ir, bundle)` (today's pure function, unchanged) and
`evaluate_population(ir, bundles)` for group assertions, which returns per-record verdicts derived
from a group computation. `within`/`overlaps` become **interval predicates** over a declared date
range — pure, cheap, and the same code serves 1d, 2 and 13.

---

### F3 · S1 — Two controls are permanently blocked by a record-boundary gap

**What.** `Document.records(entity)` looks up a regex in `RECORD_SELECTORS`; a missing entry raises
`RecordBoundaryUnknown`, which the runner turns into a whole-run `blocked`.

**Evidence (measured).** `inactive_room_future_stay` and `resource_occupancy_consistency` are
**blocked against all three evidence sets** — 6 of the 30 control × evidence combinations. The
stated reason for `occupancy` is honest and correct: in `RoomStatusInquiry` rooms and reservations
are siblings, and one reservation appears as several date segments, so no single block carries a
whole record.

**Impact.** Control 20 is unreachable. Control 13 is unreachable for a second reason on top of F1.

**v2 action.** The honest refusal is right; the *mechanism* is wrong. With a real XML tree (F4) an
occupancy record is a **projection** — `(room, reservation, from, to)` tuples assembled from two
sibling lists by an explicitly declared join, with each segment its own record. Where a projection
genuinely cannot be defined, the control stays blocked — but it should be blocked *per control with
a named reason on screen*, which v1 already does well.

---

### F4 · S2 — Provider mapping is regex-over-raw-XML, and it is silently fragile

**What.** All 52 field mappings are regexes applied with `re.findall` to the raw response text
(`resolver._extract`), and record boundaries are non-greedy regexes over the same text.

**Evidence (demonstrated, not inferred).** Two failures reproduced against the v1 resolver:

```
attrs as captured | arrival = known('2026-07-01' date)
attrs reordered   | arrival = unknown(reservation.arrival_date is absent from the provider response)
escaped surname   | known('O&apos;Brien &amp; Sons')
```

1. `reservation.arrival_date` maps to `<Timespan arrival="([^"]*)"` — which requires `arrival` to be
   the **first attribute**. Reordering two attributes in a semantically identical document turns a
   known date into UNKNOWN. XML attribute order is explicitly not significant, so this is a change
   the vendor is free to make without notice.
2. **XML entities are never decoded.** A guest named `O'Brien` resolves as `O&apos;Brien`. `exists`
   still passes, so nothing fails loudly — but the audit trail shows garbled evidence, and any
   equality or duplicate comparison on that field is wrong.

Note *how* failure 1 fails: not with an exception, but as UNKNOWN. In a scope predicate that is
worse than a crash — the control silently stops applying to records it should judge.

**Impact.** Every field. The mapping layer is the foundation the whole PMS-agnostic claim stands on.

**v2 action.** Parse with `xml.etree.ElementTree` (stdlib, zero new dependencies) and express
mappings as **structured paths** — `Booking/ResGlobalInfo/Timespan@arrival` — which the provider map
*already documents in its `path` field* but does not execute. The regex becomes a fallback for
genuinely unstructured cases, declared as such. Attribute order stops mattering, entities decode,
namespaces are handled, and record boundaries become element selections instead of `.*?`.

---

### F5 · S2 — A control that excludes or unknowns 100% of records looks identical to a clean bill of health

**What.** A run reports four counts. Nothing distinguishes *"28 rooms checked, all compliant"* from
*"28 rooms, the control never applied to any of them"*.

**Evidence (measured).** `ooo_room_protection` returns **28 EXCLUDED, 0 FAIL** on both real
captures — because all 28 sandbox rooms have empty closed-date fields, so the scope predicate never
matches. `context.md` names this exact danger for controls 1d/2/13 — *"they would return False and
silently pass everything — reporting a clean bill of health while checking nothing"* — and then the
engine ships without a guard against it.

**Impact.** The failure mode this product exists to prevent, one level up: not a wrong verdict, but
a wrong impression from correct verdicts.

**v2 action.** Every run carries a **coverage verdict** alongside its counts:
`evaluated = PASS + FAIL`, and a run with `evaluated == 0` is rendered as
*"this control reached no conclusion about any record"* with the dominant reason — never as four
tiles containing a reassuring zero. This is cheap, and it is the highest-value UI change available.

---

### F6 · S2 — Stage 1 of the six-stage pipeline does not exist

**What.** `control_rule_architecture.docx` §17 specifies Natural Language → IR → Validation →
Evidence Requirements → Provider Mapping → Executable Rule. **Five exist; the first does not.** IRs
are hand-written. `open-ques.md` 1.7 states this openly and argues, correctly, that the validation
gate underneath is the part that matters.

**Impact.** The customer experience the requirements doc describes in §2 — *type a sentence, see
"Control created / 4 of 4 fields available" / press Activate* — is the product. Without stage 1
there is an engine but no product surface.

**v2 action.** Build the compiler as its own vertical slice, with a **deterministic core**: a
controlled-grammar parser that maps a restricted English sentence to IR, testable offline with zero
network. An LLM front-end is then an optional *adapter behind the same interface* that must emit IR
passing `validate_spec` unchanged — never executable anything. Both paths tested; the offline path
is the one CI runs.

---

### F7 · S2 — Nothing reads `execution` or `freshness_requirement`

**What.** Every IR declares a trigger mode, events, minimum interval and a maximum evidence age.
The runner ignores all of it and runs on demand. `architecture.md` scopes this out, correctly, for
a demo.

**Impact.** Sections 4–12 and 22–23 of the requirements doc — arguably a third of it — are
specified, encoded in data, and dead. "Check every 30 minutes" is in the customer-facing mock-up.

**v2 action.** A scheduling slice whose core is a **pure function**:
`next_evaluation(ir, last_run_at, now, provider_capabilities) -> datetime | EventSubscription`.
That is fully testable with an injected clock and no daemon, closes the doc's execution model, and
a real scheduler later is a thin loop around it. Freshness becomes a property of stored evidence:
a run reusing evidence older than `maximum_age` must say so.

---

### F8 · S2 — No control-readiness report, though every ingredient exists

**What.** `required_evidence[].resolvable` and provider-map coverage are both present.
`validate_spec.py` prints evidence gaps once, globally. Nothing surfaces *per control, per
provider*: "MiniHotel 4/5 fields · Mews 5/5 · connect your housekeeping system to enable this".

**Impact.** `open-ques.md` calls this *"probably the most commercially useful thing in that part of
the doc"*, and the requirements doc builds its whole integration strategy on it (§15, §16).

**v2 action.** A `readiness(control, provider) -> Readiness` function over the registry and the
provider map, surfaced in the API and on the control index page. Pure, cheap, and it is what turns
UNKNOWN from a limitation into a sales path.

---

### F9 · S2 — One provider, so the central architectural claim is untested

**What.** The canonical boundary is enforced by a **grep over `engine/`** for PMS identifiers. That
is a good test of hygiene and not a test of portability: it proves no MiniHotel *name* leaks, not
that a second provider fits the seams. Mews is blocked on credentials that do not exist.

**Impact.** "One control → many PMS implementations" is the thesis of the entire product, and it
has never been executed once.

**v2 action.** Ship a **second provider adapter offline**: a small fictional `DemoPMS` speaking
**JSON** (not XML — the difference is the point) with its own provider map, its own quirks
deliberately different from MiniHotel's, and its own fixtures. Then assert the real claim in a test:
*the same IR, over the same logical hotel, through two providers, yields the same verdicts.* Zero
credentials, zero cost, and it makes Mews a mapping file when the credentials arrive.

---

### F10 · S3 — Money is `float`

**What.** `to_money` returns `Value.known(float(raw), currency)`.

**Impact.** Latent rather than observed: control 6 compares against literal `0`, where float is
safe. But control 19 (*financial posting integrity*) reconciles `Debit`, `Credit`, `TotalDebit` and
per-transaction amounts, and summing money in binary floating point is how an audit engine produces
a 0.01 discrepancy it cannot explain. In a product whose output is an accusation with a receipt,
that is not acceptable.

**v2 action.** `decimal.Decimal` (stdlib) for all money, parsed from the raw string so no float ever
exists in the path. `Value` keeps refusing cross-currency comparison exactly as it does today.

---

### F11 · S3 — No timezone model; dates come from the process's local clock

**What.** `date.today()` and `datetime.now()`, naive throughout. `today-1d` resolves against the
machine's calendar.

**Impact.** Every control in this product is temporal and property-local. "Arriving within 24
hours", "checked out in the last 24 hours", "created after the scheduled arrival time" are all
questions about the *hotel's* clock. The requirements doc says so explicitly:
`"time": "08:00", "timezone": "property"`. A run executed from a different timezone silently
evaluates a different population — and R3 (`createDateTime` is date-only) means some of these
questions cannot be answered at hour precision at all, which the engine should state rather than
imply.

**v2 action.** A `PropertyClock` in tenant configuration: IANA timezone, and every relative date in
a population query resolved through it. Injected, never global — so tests set the clock rather than
depending on the machine.

---

### F12 · S3 — Per-tenant configuration lives in module constants

**What.** `MINIHOTEL_STATUS_MAP` and `MINIHOTEL_DEPARTMENT_MAP` are dicts in
`silo1_evidence/transforms.py`, injectable per `Resolver`. `open-ques.md` 1.4 flags this as an open
question and the reasoning for the current placement is sound.

**Impact (measured, and larger than it looks).** Across all captures, **44 of 217 distinct
reservations — one in five — carry a status code the engine refuses to name** (`OK4` 32, `WL` 12).
Refusing to guess is right. But onboarding a second property means editing Python, and a
per-property fact in code is a per-property fact that gets deployed.

**v2 action.** A `tenants/<tenant_id>.json` configuration object: status map, department map,
timezone, currency, call budget, nominated rate codes. Loaded as data, validated by the spec
validator, injected into the resolver. This answers open question 1.4 with the option that keeps
provider knowledge (the API surface) separate from tenant knowledge (this hotel's vocabulary).

---

### F13 · S3 — No transport, so there is no path from demo to production

**What.** `engine/` contains no HTTP client, by design (R8). `LiveSource` takes an injected
transport that nothing implements; `verify_api.py` and `probe_checkouts.py` shell out to `curl`.

**Impact.** The safety property is excellent and must survive. But `open-ques.md` records the
consequence honestly: *"production needs a transport written and a retry/rate-limit policy agreed"*
— i.e. the most operationally risky component is entirely unbuilt and untested.

**v2 action.** A transport slice that is **off by default and cannot be switched on by a test**:
explicit opt-in via environment, a token-bucket rate limiter, bounded retry with backoff, a hard
per-run call ceiling reusing the existing budget, and — the valuable part — a **record mode** that
writes every live response into the fixture set with its request fingerprint. Probing stops being a
hand-run script and starts being reproducible.

---

### F14 · S3 — Runs are unindexed JSON files

**What.** One file per run in `runs/`; `/api/runs/<id>` re-reads one. Nothing lists them.

**Impact.** No history, no trend, no "has this control been failing all week", no
compliance-over-time — which is what "continuous assurance" in the PRD means.

**v2 action.** `sqlite3` — **stdlib, so the zero-dependency rule holds** — with runs, verdicts and
evidence rows. Enables history, a per-control trend, and re-reading a verdict without spending a
provider call (R1), which is the reason the store exists at all.

---

### F15 · S3 — Sandbox credentials and guest PII are about to land in a **public** repository

**What.** `github.com/sauravs/miniHotelPMS` is public and currently empty.
`verify_api.py:60` hard-codes `USER, PWD, HOTEL = "Test", "3657488", "sandbox"` — documented, fairly,
as credentials MiniHotel publishes itself. Separately, the 2026 capture (`9_departures_2026-07.xml`,
138 reservations) contains **27 distinct email addresses and 30 phone numbers**, several of which
are not obviously test data (`yuval@minihotelpms.com`, `avi@singularitybridge.net`, a `gmail.com`
address, and Israeli mobile numbers in real format), plus free-text Hebrew remarks naming a guest
and describing an approval.

**Impact.** Two separate problems. Credentials in source is a habit that survives the move to
production credentials. Third-party personal data in a public repository is a GDPR question, not a
style question — and it is *someone else's* sandbox.

**v2 action.** Credentials from environment only, with `.env.example` and a `.gitignore` that
covers it — no fallback default, so a missing credential fails loudly. Fixtures **pseudonymised at
capture time** by a deterministic scrubber (stable fake names/emails/phones, so tests stay
deterministic and diffs stay readable), with the raw captures kept locally and git-ignored. Confirm
with the project owner before the first push. Flagged as a question, not decided unilaterally.

---

### F16 · S3 — The test suite has no CI, no coverage measurement, and a known cache hazard

**What.** 152 tests run only when someone types the command. `plan.md` documents a real trap: a
mutation that changes neither file size nor mtime-second leaves a stale `.pyc` valid, and *"the
suite silently runs the OLD code and reports a green that means nothing"* — two mutations looked
survivable for exactly this reason.

**Impact.** A green that means nothing is worse than a red. And the project's own TDD gate ("a
silo's tests must pass before the next opens") is enforced by discipline alone.

**v2 action.** GitHub Actions on every push and PR: `PYTHONDONTWRITEBYTECODE=1`, the full suite, the
spec validator, and a coverage floor. Branch protection so the gate is mechanical. The stale-cache
trap becomes structurally impossible rather than a documented warning.

---

### F17 · S4 — Python-2-era style in a Python 3.13 codebase

**What.** `class Foo(object)`, `%`-formatting, `__slots__` hand-rolled everywhere, zero type
annotations across 4,286 lines.

**Impact.** No runtime bug — but `Value`, `Verdict`, `EvidenceBundle` and `Run` are exactly the
data classes that `@dataclass(frozen=True, slots=True)` exists for, and typed signatures on the
four silo seams would document the interfaces the architecture doc draws in ASCII. Readability is
an explicit requirement for v2.

**v2 action.** `from __future__ import annotations`, frozen slotted dataclasses for value objects,
`Protocol` for the seams (`Source`, `Transport`, `Store`), full annotations. Keep the comment
density — it is the best thing about this codebase.

---

### F18 · S4 — Documentation is excellent and lives in the wrong place

**What.** Nine markdown documents plus two generated HTML pages in the repository root, alongside
seven executable scripts and four package directories. `architecture.html` is explicitly marked
superseded and still present.

**v2 action.** All prose in `/docs`, with `CLAUDE.md` and `README.md` at the root as the only
entry points. Generated artefacts in `/docs/generated`, git-ignored where they can be rebuilt.

---

### F19 · S4 — Minor correctness notes worth carrying

| | Note |
| --- | --- |
| a | `Value.__eq__` ignores `source` (deliberate, documented) but `__hash__` stringifies `value` — two Values equal under `__eq__` with different reprs would hash apart. No live impact; fix by construction with a frozen dataclass |
| b | `_fetch_follow_up` caches responses **per record**, so a property-wide response fetched for record A is fetched again for record B. Harmless today because such fields return UNKNOWN before a call is made — but it becomes a real cost the moment F1 lands. v2 needs a **run-scoped response cache** |
| c | `FrozenSource.replay_filters` re-implements the vendor's filter semantics in the fixture layer. Necessary and clever, but fixture behaviour can drift from live behaviour with nothing to detect it. v2: store the **request fingerprint alongside each fixture** so a replay can assert it is answering the question the capture actually asked |
| d | `reservation.id` has `absent_means: "false"` in the registry — an identifier whose absence yields `known(False)` rather than UNKNOWN. Defensible for `exists` tests; surprising for an identity field, and Silo 2 keys bundles on it |

---

### F20 · S4 — Open product questions inherited, not resolved

Carried into v2's `open-questions.md` rather than silently decided. The v1 answers are all
defensible; each needs the project owner, not an engineer.

| | Question | v1 behaviour today |
| --- | --- | --- |
| 1 | Does an overpaid folio (−490.75 ILS) deserve its own outcome, or is it a FAIL? | FAIL. Recommendation on file: split into two controls |
| 2 | Does an unverifiable exception count as a pass? Decides whether ~9 controls ship | UNKNOWN, always. Will not be changed without a decision |
| 3 | Is unstructured free text an evidence source? VIP status and an approval exist only in Hebrew remarks | Not read at all |
| 4 | Are the 2024-era room findings still true, now that the sandbox is known to have moved on? | Assumed true, marked unverified |
| 5 | Control 9: who supplies rate-plan → permitted room types? | UNKNOWN with that reason |

---

## What v2 does with this

Three findings unlock nine controls (F1, F2, F3). Two make the product a product (F6, F8). One
makes the central claim true rather than asserted (F9). The rest is correctness and hygiene.

Everything in **What v1 got right** is carried across unchanged, including the rule that outranks
all of the above: **never widen a verdict.** If evidence is missing, the answer is UNKNOWN — and no
finding in this document is worth breaking that for.
