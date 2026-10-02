# Q&A Log

A running transcript of questions from the project owner and the answers given, newest at the
bottom. Appended to by the `/qa-log` skill; **append only, never rewritten.**

Three conventions make this useful rather than merely long:

- The question is recorded **verbatim**. A paraphrase quietly changes what was asked.
- Every answer states **what was actually checked** — files read, commands run, fixtures inspected —
  or says plainly that it was reasoning only. Documentation review got 4 of 12 risks wrong on this
  project; that is why the field exists.
- A wrong answer is **corrected by a new entry, not by an edit**. The old entry gets one added line
  (`Status: superseded by Q<n>`) and otherwise stands. Being wrong on the 4th is part of the record.

The v1 transcript — twelve entries covering the feasibility analysis, the sandbox probing and the
architecture dry run — is preserved at `miniHotelLegacy/QA.md`. This file starts fresh at Q1 for v2.

---

## Q1 — 2026-09-08

**Q:** There is already a folder named "miniHotelLegacy". It is old codebase containing all
important docs explaining the requirements of this project like claude.md, context.md, prd.md, etc.
It also contains two very important initial requirement docs Hotel Controls.docx and
control_rule_architecture.docx. MiniHotel_Controls_API_Feasibility.xlsx was created after verifying
with miniHotel docs API. Please first analyze this codebase deeply with all important aspects
covered, so that you understand the requirement thoroughly and have accurate context. After that in
this root directory, re-implement this requirement step by step with proper claude workflow like
freshly creating and implementing everything from scratch like plan.md, prd, context etc.

**A:**

Reviewed the whole of `miniHotelLegacy/` in four passes: the two requirement `.docx` files, the nine
markdown documents, all 4,286 lines of `engine/` and `tests/`, the `spec/` layer (52 canonical
fields, 10 IRs, 880 validation checks) and the 14 frozen `probe/` responses — then **ran** the code
rather than only reading it.

**What v1 is.** A PMS-agnostic control engine in four silos: evidence (the only layer that knows
MiniHotel exists), population (bounded queries, call budget), evaluator (pure, four outcomes) and
runner/UI. 152 tests, all offline, all green. The design is right and the engineering discipline is
unusually good — `old-codebase-improve.md` lists twelve things (K1–K12) carried into v2 unchanged.

**What running it revealed.** Executing all 10 controls against all 3 evidence sets:

| | |
| --- | --- |
| Controls that ever produce a PASS or FAIL | **1 of 10** |
| Blocked against every evidence set | 2 |
| 100% EXCLUDED (looks identical to a clean bill of health) | 1 |
| 100% UNKNOWN | 6 |

Three missing capabilities explain all nine failures: no **reference stage** (a record can never be
joined to property-wide data — three controls return 111 UNKNOWN out of 111 records), no
**cross-record evaluation** (duplicate detection returns zero answers despite the fixtures containing
a known real duplicate pair), and no **record projection** for composite entities.

Two further defects were reproduced directly against the v1 resolver rather than inferred:
reordering two XML attributes in a semantically identical document silently turns a known arrival
date into UNKNOWN, and XML entities are never decoded, so a guest named `O'Brien` resolves as
`O&apos;Brien`.

**What v2 is.** Eight layers instead of four, adding the reference stage, population-level
evaluation, a coverage verdict, a readiness report, a second provider, the natural-language
compiler, scheduling, and SQLite run history — built as twelve TDD slices, each gated by CI and
merged through a PR. Full detail in `prd.md`, `architecture.md` and `plan.md`.

**Evidence:** read every file in `miniHotelLegacy/`; extracted both `.docx` files; ran
`python3 -m unittest discover -s tests` (152 pass) and `validate_spec.py` (880 checks pass); ran all
10 controls × 3 evidence sets and tabulated the outcomes; wrote throwaway probes that reproduced the
attribute-order and XML-entity failures against the live v1 resolver.

**Status:** answered

---

## Q2 — 2026-09-08

**Q:** Do not guess, ask questions in case of any concerns or needed clarification first before
implementing/writing plan, prd, etc.

**A:**

Eight decisions were put to the project owner before any v2 document was written, because each would
have changed the plan materially. All eight are recorded in `open-questions.md` §0 as D1–D8:

| | Decided |
| --- | --- |
| Scope | All 10 dry-run controls made genuinely executable (11 IRs after splitting control 6) |
| Dependencies | Stdlib-only runtime; `pytest` + coverage as dev dependencies |
| Live API | Allowed, with per-call approval |
| Second provider | A fictional `DemoPMS` speaking JSON, offline |
| NL compiler | Deterministic grammar core, LLM adapter behind the same validation gate |
| Repository | Public, fixtures pseudonymised, credentials from environment only |
| Git workflow | Branch per slice → PR → CI gate → squash-merge |
| Overpaid folio | Split control 6 into two controls — money owed, and unrefunded credit |

Four further decisions were deliberately **not** taken unilaterally and are carried as checkpoints
in `plan.md`: approval for three read-only calls to refresh the stale 2024 room findings (before
slice 3); whether a cancel-and-recreate pair sharing one portal id is a duplicate (before slice 5);
which rate codes a property has nominated (before slice 6); and whether the LLM adapter should be
wired to a real model (before slice 9).

**Evidence:** decisions collected directly from the project owner on 2026-09-08.

**Status:** answered

---

## Q3 — 2026-09-09

**Q:** Pls check  and verify  with intial req doc (inside miniHotelLegacy) Hotel Controls.docx / MiniHotel_Controls_API…xls out of 20+ controls given, how much we have implemented and verified so far in our current codebase?

**A:**

Three different numbers, and they are worth keeping apart.

| | count |
| --- | --- |
| Controls in `Hotel Controls.docx` | **20** |
| Rows in the feasibility workbook | **21** (control 1 splits into 1a–1c and 1d) |
| Feasibility verdict: Yes / Partial / No | **9 / 10 / 2** |
| **Built as an executable IR** | **10 of 21 rows → 11 IRs** (control 6 splits in two) |
| **Reaching a real PASS or FAIL on captured evidence** | **6 IRs — 5 source controls** |
| **Re-verified against the live API by v2** | **0 calls** |

### What was built, and what it answers

| row | feasibility | our control | answers? |
| --- | --- | --- | --- |
| 1a–1c | Yes | `room_assignment_type_validity` | **yes** — 27 PASS |
| 1d | Yes | `room_assignment_active_room` | no — 111 excluded |
| 2 | Yes | `ooo_room_protection` | no — 28 excluded |
| 4 | Yes | `room_capacity_compliance` | no — 40 UNKNOWN |
| 6 | Yes | `checkout_money_owed` | **yes** |
| 6 | Yes | `checkout_unrefunded_credit` | **yes** — the −490.75 ILS overpayment |
| 9 | Partial | `rate_room_category_consistency` | no — 40 UNKNOWN |
| 13 | Yes | `inactive_room_future_stay` | **yes** — 27 PASS |
| 14 | Yes | `duplicate_channel_reservation` | **yes** |
| 15 | Yes | `required_reservation_fields` | no — 37 UNKNOWN |
| 20 | Yes | `resource_occupancy_consistency` | **yes**, but only over the one week its capture covers |

**Every row the feasibility study rated "Yes" was built** — all nine — plus one "Partial" (control
9). No scope drift: that is exactly the list `prd.md` §6 committed to.

### The eleven not built, and why

Two are **structurally blocked** — the entities do not exist in the API:

- **8** rate-plan eligibility — no rate-plan master, nothing to validate a rate against
- **17** company/corporate rate control — no company or account object anywhere

Nine need something the PMS does not record:

| row | what is missing |
| --- | --- |
| 3 | only one room type per stay — no booked-vs-assigned distinction, so an upgrade cannot be told from an error |
| 5 | no endpoint exposes the *configured* payment/guarantee requirement |
| 7 | no cancellation-policy endpoint — penalty window and charge must come from outside |
| 10 | no field-level change log, no acting user, no reason code |
| 11 | no price history or versioning — needs our own snapshots |
| 12 | `createDateTime` is date-only (R3), so same-day backdating is undetectable |
| 16 | no package or product entity |
| 18 | detection is solid; the *approved reason* half does not exist |
| 19 | no chart-of-accounts or department master |

Row 3 is partly covered already — clause 1c of `room_assignment_type_validity` compares the stay's
type against the room's actual type — but it cannot distinguish an approved upgrade, so it is not
claimed as control 3.

### On the word "verified"

- **Feasibility-verified against live responses: 20 of 20.** v1 made 14 read-only calls in 2024 and
  September 2026, which is where R9 (a reservation in USD against its own folio in ILS), R11 and
  R12 came from. Documentation review had 4 of 12 risks wrong.
- **Verified as executable and validated: 11 IRs**, each schema-valid, referencing only declared
  vocabulary, running on both providers with identical verdicts.
- **Verified as producing an answer: 5 source controls.** Not 8, which is what criterion 1 asks for.
- **Re-verified against the live API by v2: none.** Every verdict this engine has produced comes
  from captures — real responses, but taken in 2024 and September 2026.

**Headline: 10 of 21 rows implemented (100% of what was rated buildable), 5 reaching real verdicts,
0 re-verified live.**

**Evidence:** `miniHotelLegacy/Hotel Controls.docx` (extracted with `zipfile` + regex over
`word/document.xml`, 20 controls); `miniHotelLegacy/MiniHotel_Controls_API_Feasibility.csv`
(21 rows, `Verifiable` and `What's missing` columns read in full); `source_control` read from all
11 files in `spec/ir/`; and every control RUN against `sandbox2026`, `sandbox2024` and the
2024-08-14 instant through `hotelcontrols.runner.run` to measure which reach `coverage.concluded`.
The mapping table above is generated, not asserted.

**Status:** answered

**Correction:** three numbers in this entry are wrong — 6 IRs should be 5, "5 source controls" is
compared against a target counted in IRs, and the 14 calls were all made in 2026. See Q5.
(2026-09-10)

---

## Q4 — 2026-09-09

**Q:** "│ Re-verified against the live API by v2" 0 calls,is this mean we currently verfired by their test api provided, I think demo.... and not via their mainnet(production API)? And is their mainnet production API free? How to get the crednetial(u can search their website)

**A:**

### Yes — sandbox only, never production

Every byte of evidence in this repository came from `sandbox.minihotel.cloud`. v1's probe script
says so on the line that sets the host, and names the other one:

```python
BASE = "https://sandbox.minihotel.cloud"   # production would be api2.minihotel.cloud
```

Production has never been touched, by v1 or v2.

### Three things could be called "the test API" and only one of them is MiniHotel's

| | what it is | have we called it? |
| --- | --- | --- |
| **MiniHotel sandbox** (`sandbox.minihotel.cloud`) | A real server of theirs, the real API, with credentials MiniHotel publishes openly in its own documentation examples | **Yes** — 14 read-only calls, by v1, in 2024 and September 2026. Every fixture is one of those responses, pseudonymised |
| **MiniHotel production** (`api2.minihotel.cloud`) | Real hotels' live data | **Never** |
| **DemoPMS** | *Ours.* A fictional second PMS with no server at all, generated by transcoding the MiniHotel captures field by field, gaps included | Nothing to call. It exists to prove the boundary is real |

So DemoPMS is not MiniHotel's demo — it is our own invention, and it is offline by construction.

### What "0 calls by v2" means precisely

Narrower than it sounds, and worth being exact about. It means **the v2 engine's own transport has
never made a call at all** — not to production, and not to the sandbox either. The 14 captures were
made by v1's `curl`-based scripts. The transport built in slice 11 has been exercised only against
injected dialers, and it refuses to arm inside a test process by design.

That is the gap the pending three-call probe closes, and it is why the probe matters: it verifies
*the transport* as much as it refreshes the findings.

### Is production free?

**MiniHotel publishes no pricing for API access, and I could not verify cost.** What their
documentation does say, quoted exactly:

> "Production credentials will be provided upon completion of the staging and testing phase. Until
> then, please use the sandbox credentials specified on each API page"

> "Before moving to production, it's essential to ensure your IPs are whitelisted with us"

Three APIs are documented — ARI API, Content & Data API, Reverse API. No rate limits, no fees and
no partner-certification process are stated anywhere I could reach. Their developer and FAQ pages
return HTTP 403 to an automated fetch, so this is what the public documentation portal says and
nothing more. **Treat "is it free" as unanswered:** the absence of a published price usually means
it is a commercial conversation rather than a self-serve signup, but that is an inference and not a
fact.

### How credentials are obtained — and the part that matters more

**Sandbox:** nothing to request. The credentials are printed on MiniHotel's own API reference pages,
which is where v1's came from.

**Production:** complete the staging and testing phase, get your IPs whitelisted, and MiniHotel
issues them. That is a conversation with their technical support, not a form.

**But the important point is that we probably should not want production access, and certainly not
yet.** Three reasons:

1. **Production is a real hotel's live guest data.** This engine is read-only, permanently, but the
   correct target for *verifying controls* is the sandbox — refreshed. Nothing about a control's
   logic is better tested against real guests.
2. **Production credentials are per-property, and they are the property's to give.** When a real
   customer is onboarded, that hotel authorises access to its own data. It is not a key we obtain
   once and reuse — which is also why `TenantConfig` is per-property data and credentials come from
   the environment keyed by provider (F15).
3. **The exposure changes.** Real guest PII is a GDPR question rather than a style one (D6), R8
   applies to a live property rather than a shared sandbox, and IP whitelisting means the machine
   that runs it matters.

**The right sequence:** refresh the sandbox with the three calls already planned → build a pilot
with a real property → that property authorises production access. Step one is waiting on approval
today; step two is a commercial conversation, not an engineering one.

What production *would* eventually add for verification is worth naming, because it is not nothing:
real data volumes, real status codes in the wild — which would settle `OK4` and `WL` empirically
rather than by asking — and real error behaviour, which is still unobserved (issue #16 classified
failures by status code, which needed no observation; what their error *bodies* look like stays
unguessed until one is seen).

**Evidence:** `miniHotelLegacy/verify_api.py:37,59` and `probe_checkouts.py:37` for the hostnames;
`fixtures/minihotel/index.json` and `spec/providers/minihotel.json` for what the captures were taken
against. The quotations are from `minihotel.readme.io` fetched 2026-09-09. `minihotel.io/developers/`
and `minihotel.io/faq/` both returned HTTP 403 to an automated fetch and were **not** read — so the
pricing question is unanswered rather than answered "free". Nothing here was verified by making a
call.

**Status:** answered in part — `open — see docs/open-questions.md §1.9` for whether this should ever
touch a production PMS, and whose credentials those would be

**Correction:** the phrase "in 2024 and September 2026" is wrong — all 14 calls were made in 2026.
See Q5. (2026-09-10)

---

## Q5 — 2026-09-10

**Q:** *Not an owner question.* This entry corrects Q3 and Q4 after a code review of commit
b557685 on 2026-09-10. It is recorded as a new entry because this file is append-only: a wrong
answer is corrected by an entry, never by an edit.

**A:**

Three numbers in Q3 are wrong, and one date phrase is wrong in both Q3 and Q4. Everything else in
both entries reproduces exactly and stands.

### 1. "6 IRs — 5 source controls" should be **5 IRs — 4 source controls**

Q3's summary table claims six IRs reach a real PASS or FAIL. The repository's own measurement says
five: `docs/plan.md` §"Criterion 1, assessed" and `tests/e2e/test_runs.py`, which pins the set by
name (`CONCLUDING`) and asserts `len(concluding) == 5` so that a change turns a test red.

The sixth was `resource_occupancy_consistency`. It is `BLOCKED` on both standard evidence sets —
its only occupancy capture covers 2024-08-14..2024-08-21, and a run asking about any other week is
refused rather than answered from the wrong one. It concludes only at the extra 2024-08-14 instant.
That is precisely the control **issue #9 removed from this count**, because it had been reaching two
PASSes about July 2026 from segments captured in August 2024. Q3's table did carry the qualifier —
*"only over the one week its capture covers"* — but the qualifier does not travel with the headline
number, and the number is what a reader takes away. Counting it re-widens a verdict the guard was
built to narrow.

The five that do conclude are `checkout_money_owed`, `checkout_unrefunded_credit`,
`duplicate_channel_reservation`, `inactive_room_future_stay` and `room_assignment_type_validity` —
which map to **four** source controls, not five: 1 (rows 1a–1c), 6 (twice), 13, 14.

### 2. "5 source controls. Not 8" compares two different units

`docs/prd.md` §7 criterion 1 asks for *"at least 8 of the **11 controls**"* — 8 IRs. Q3 answers in
source controls and sets the result against a target counted in IRs. The two units happen to print
the same digit here, which is what made the mismatch invisible: Q3's headline "5 reaching real
verdicts" looks like it agrees with plan.md's "5 of 11" while actually counting something else, and
the same entry's table two screens earlier said 6.

Stated once, in each unit:

| unit | conclude | target |
| --- | --- | --- |
| **IRs** (criterion 1's unit) | **5 of 11** | 8 of 11 — **not met** |
| source controls | 4 of the 10 built | criterion 1 does not measure this |

### 3. The 14 sandbox calls were all made in **2026**, not "in 2024 and September 2026"

The phrase appears three times — Q3 twice ("v1 made 14 read-only calls in 2024 and September 2026";
"real responses, but taken in 2024 and September 2026") and Q4 once ("14 read-only calls, by v1, in
2024 and September 2026"). No call was ever made in 2024. All 14 entries under `responses` in
`fixtures/minihotel/index.json` carry a 2026 `captured_at`: six on 2026-09-01, one on 2026-09-04,
seven on 2026-09-08 — matching the timeline in `docs/context.md`, which dates every live probe to
2026.

**2024 is the vintage of the data the sandbox was holding, not the date of the call.** The
distinction matters and is the reason open question [1.2](open-questions.md) exists: the sandbox had
moved on to 2026 data between the September 1 and September 8 probes, which is how the 2024-era room
findings became stale without any of them being re-tested. Collapsing "called in 2026, saw 2024
data" into "called in 2024" loses exactly that.

The count of **14** is correct.

### What is unchanged

Every other figure in Q3 and Q4 was re-checked and reproduces: 20 controls in the docx; 21 rows in
the feasibility workbook at 9 Yes / 10 Partial / 2 No; 10 rows built as 11 IRs, matching `prd.md` §6
with no scope drift; all 11 `source_control` values; the per-control results (27 PASS, 111 excluded,
28 excluded, 40 UNKNOWN, 37 UNKNOWN, the −490.75 ILS FAIL); the eleven not built and their reasons;
and all of Q4 — sandbox-only, production never touched, `0` calls by the v2 transport, DemoPMS being
ours and offline by construction.

**Corrected headline for Q3:** 10 of 21 rows implemented (100% of what was rated buildable),
**5 of 11 IRs** reaching real verdicts against a target of 8, 0 re-verified live.

**Evidence:** `tests/e2e/test_runs.py:24-40,111-119` (the `CONCLUDING` and `BLOCKED` sets and the
assertions over them); `docs/plan.md:260,289,297,632,645-679`; `docs/prd.md:138`; `source_control`
read from all 11 files in `spec/ir/`; `fixtures/minihotel/index.json` parsed with `json` and its
`responses` entries counted by `captured_at`; `docs/context.md:12-19`. No call was made.

**Status:** answered

---

## Q6 — 2026-10-02

**Q:** how this The compose window — http://127.0.0.1:8766/compose is working behind the scene? Are we using any llm here?which model is produing the result?

**A:**

### For the server that was running at the time: no LLM at all

That server was started with `--llm stub`. `StubProposer` is a **hardcoded lookup table** — nine
`(fragment, reply)` pairs in `tools/proposers/stub.py:22`. It lowercases the prose, returns the
reply for the first fragment found in it, and falls back to a fixed refusal. No model, no network,
no configuration.

Demonstrated live rather than asserted: a `POST /compose` carrying
*"find me guests who left owing money"* matched the fragment `owing` and returned

```
every reservation where reservation.status is "checked_out" must have folio.balance_due at most 0
```

which is why it is instant and why it always answers. It exists for two reasons, both on the
record in D9: the compose UI is demonstrable with **nothing installed**, and *a stub tests the §17
gate harder than a real model does* — it emits exactly the proposals that exercise the validator
(an undeclared field, a population word, an ambiguous operand, a bare question, a crash), where a
real model mostly emits plausible sentences.

### The pipeline, and where a model sits if one is wired

```
prose
  ↓
[proposer]   ← the ONLY place a model appears. Lives in tools/, outside the engine, INJECTED
  ↓
restricted-English SENTENCE   ← shown and editable. Never IR, never executable
  ↓
GrammarCompiler  ← deterministic. confidence 1.0, source "grammar"
  ↓
spec.validate    ← the same validator a hand-written IR file goes through, unchanged
  ↓
a draft in spec/drafts/, badged `draft · unreviewed` → runs
```

The load-bearing choice is D10's: **the model may not emit a rule.** It drafts a sentence a person
reads; the deterministic grammar builds the rule. A wrong field name is therefore not bad IR that
slipped past a schema — it is a sentence the grammar refuses **by name**. No verdict depends on a
model call, and the evidence layer and evaluator never learn one exists.

### The four backends

| `--llm` | What produces the sentence | Cost | Default |
| --- | --- | --- | --- |
| `local` | **Ollama on this machine**, default `qwen2.5:7b`, over stdlib `urllib` | free, offline | **yes** |
| `claude` | **`claude-haiku-4-5`** via the optional `anthropic` SDK, `max_tokens=512` | ~¼¢/attempt | no |
| `stub` | a dict of fixed strings | free | no — but it is what was running |
| `off` | nothing | — | no |

`local` is the default because *free to run* was a stated requirement from the project owner, not a
preference. Both live backends set `temperature: 0`: the same prose must give the same sentence
twice, and a sampling proposer in front of a stateless compiler would reintroduce nondeterminism
into the thing a person approves.

The `claude` backend marks the vocabulary `cache_control: ephemeral` and places it first, because
it is byte-identical on every turn of a session. `anthropic` is declared in
`requirements-llm.txt` and imported **inside `__init__`** rather than at module scope, so every
backend stays importable with nothing installed.

### Two things worth recording

**The prompt is generated, never written.** Regenerated during this answer: **7,925 characters,
~1,981 tokens**, assembled at startup from `spec/canonical_fields.json`, the grammar's own
`OPERATOR_PHRASES` and keyword tables, and six shipped `restricted_language` sentences. It
therefore cannot drift from the language the compiler actually speaks — a hand-written prompt
listing operators would be a second copy of `OPERATOR_PHRASES`, and the day somebody added one the
model would be told about a language the compiler no longer accepts, **silently**.

**Two locks, and the local backend is held to both.** `base.assert_armed` refuses unless
`HOTELCONTROLS_COMPOSE=1` **and** no test runner is loaded in the process. Its own reasoning:
*"`localhost` is still a socket, and a rule with one exception is a rule somebody will find a
second exception to."* The test that sets the variable is refused anyway. This is why
`hotelcontrols/compiler/sentences.py` imports only `re`, `dataclasses` and `typing` — it holds a
`SentenceProposer` **protocol** and takes one as a parameter; it cannot acquire one. And
`normalise()` catches every exception a proposer raises and turns it into a **stated reason**,
because a traceback out of a compose step reads as an engine defect when the honest report is
*"the thing we asked could not answer"*.

**To see a real model do it:**

```bash
brew install ollama && ollama pull qwen2.5:7b && ollama serve
HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm local --port 8767
```

**Evidence:** read in full — `tools/proposers/stub.py`, `tools/proposers/local.py`,
`tools/proposers/anthropic_api.py:1-70` and its `messages.create` call, `requirements-llm.txt`,
`tools/proposers/base.py` (`assert_armed`, `vocabulary`, `system_prompt`),
`hotelcontrols/compiler/sentences.py` (`normalise`, `split_reply`, and its import list),
`tools/serve.py:5-8,36-78`. Run: `python3 -m tools.serve --help`; `system_prompt()` generated and
measured at 7,925 chars; a live `POST /compose` against the stub server on port 8766; a
cross-provider grep (`openai|langchain_openai|google.generativeai|mistralai|cohere|ollama`)
confirming Ollama is the only non-Anthropic backend referenced anywhere. **No model was called and
no network request left this machine** — the stub needs neither.

**Status:** answered. The *current* behaviour is fully verified above; whether a model should be
wired by default remains open question 1.8 in `docs/open-questions.md`, unchanged by this answer.

---

## Q7 — 2026-10-02

> **Ordering note.** This question was asked *before* Q6 in the same session and logged after it.
> Numbering is sequential by logging order and never renumbered, so the two entries sit in reverse
> order of asking. Recorded here so the transcript is not read as a chronology.

**Q:** how can i run the ui ? I want to see visually how this app is working end to end in ui

**A:**

### Two commands

```bash
python3 -m hotelcontrols.web.server                        # the demo → http://127.0.0.1:8765/
HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub   # + the compose chat box
```

No install step, no dependencies, no network. Both were started and every route below returned
HTTP 200 before being written down.

### A guided tour — seven stops, each demonstrating one thing the architecture exists to do

Every number below was read from the running app via `/api/run/<control_id>`, on property
`sandbox` (MiniHotel captures), at the default `as_of` of **2026-07-08**.

| # | URL | What it shows |
| --- | --- | --- |
| 1 | `/` | Eleven controls with per-provider readiness; two properties in the selector — `sandbox` (minihotel) and `demo` (demopms); four captures — `sandbox2024/2026`, `demo2024/2026` |
| 2 | `/run/checkout_unrefunded_credit` | **A real FAIL with its evidence.** `1 PASS, 1 FAIL`, 3 calls |
| 3 | `/run/inactive_room_future_stay` | **Three outcomes on one page.** `27 PASS · 13 UNKNOWN · 71 EXCLUDED` of 111, 2 calls |
| 4 | `/run/ooo_room_protection` | **The thing v1 got wrong.** `28 EXCLUDED`, `concluded=False` |
| 5 | `/run/room_capacity_compliance` | **A wall of UNKNOWN that is correct.** `40 UNKNOWN · 71 EXCLUDED`, `concluded=False` |
| 6 | `/run/resource_occupancy_consistency` | **A control that refuses to answer.** Blocked. Add `?as_of=2024-08-14` → `2 PASS` |
| 7 | both `?property=` values | **The whole thesis.** Identical verdicts, identical call counts, two wire formats |

**Stop 2, exactly as the app reports it.** The FAIL is reservation `007004348`:

```
FAIL   record=007004348   folio.balance_due is -490.75 ILS, which does not satisfy `gte 0`
PASS   record=007004351   folio.balance_due is 0 ILS, which satisfies `gte 0`
```

The guest overpaid and was never refunded. Note the evidence line carries the **currency**, which
is why this control asserts against literal zero rather than against the reservation total (R9).

**Stop 3** is the page to study: UNKNOWN is distinguished from FAIL by hue, border style **and**
wording, so the distinction survives a monochrome screen. EXCLUDED has its own tile — those 71
records were never checked, and folding them into PASS would report "98 passed".

**Stop 4 — and this is stronger than "no tiles are shown".** A blocked run's JSON has **no
`counts` key at all**, verified by comparing key sets: `resource_occupancy_consistency` →
`counts present=False`, `checkout_money_owed` → `counts present=True`. And the rendered page
contains **zero** occurrences of `PASS`, `FAIL` or a tile class. So four reassuring zeroes are not
merely hidden by the template — they are structurally unavailable to it. v1 rendered this exact
case (28 EXCLUDED / 0 FAIL) indistinguishably from a clean bill of health.

**Stop 5.** 23 of 28 rooms report adult capacity `0`, meaning *unconfigured* (R12). Reading those
as real zeroes would produce 40 false accusations.

**Stop 7, measured both ways:**

```
/run/inactive_room_future_stay?property=sandbox  → minihotel  sandbox2026 (synthetic=False)  2 calls  27 PASS · 13 UNKNOWN · 71 EXCLUDED
/run/inactive_room_future_stay?property=demo     → demopms    demo2026    (synthetic=True)   2 calls  27 PASS · 13 UNKNOWN · 71 EXCLUDED
```

One rule, two PMSs — one XML with three date formats, one JSON carrying month names. Identical
verdicts **and** identical call counts. That is success criterion 7, and it is why adding Mews is
an adapter rather than a rewrite.

Also worth opening: `/history/<control_id>` (past runs, re-read with **zero** provider calls, R1),
`/api/readiness/<control_id>`, and `/api/run/<control_id>` for the structure behind any page.

### The compose window — `:8766/compose`

The `stub` backend needs no model and always answers. Fragments that reach a specific outcome:
`owing`/`balance` → compiles and runs · `inspect` → refused by name, `room.inspection_status` is
undeclared · `tomorrow` → refused, a sentence may not choose its own population · `corporate` →
comes back as a **question** with no button to run anything. On `:8765` the same URL says compose
is switched off. Full mechanics in **Q6**.

### Stopping, and one caveat

```bash
pkill -f hotelcontrols.web.server; pkill -f tools.serve
```

`as_of` defaults to **2026-07-08**, the instant the captured evidence describes — **not today**. A
July capture answers questions about July; asking it about today would produce a page of refusals
for reasons that have nothing to do with the controls. Every page states which instant it asked
about, and `?as_of=` overrides it.

**Evidence:** both servers started (`python3 -m hotelcontrols.web.server` on 8765;
`HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub --port 8766`) and left running. Every
route in the tour confirmed HTTP 200 by `curl`. All eleven controls' outcomes, call counts, `as_of`
and coverage read from `/api/run/<control_id>` and **re-read a second time before being recorded**.
The `007004348 / −490.75 ILS` detail was asserted in conversation from `CLAUDE.md` and then
**verified against the live verdict and its evidence line**, which is the only reason it appears
here as fact. The blocked-run claim was tightened on verification: the JSON omits `counts`
entirely, which is a stronger statement than the "no count tiles" originally given.
`python3 -m tools.serve --help` for the backend list. **No PMS call was made** — every run replays
captured fixtures.

**Status:** answered

---

## Q8 — 2026-10-02

**Q:** related to stayops-gap-analysis.md ,what does multi-tenant means? Pls explain by giving simple analogy ,and did our current codebase implemented that?if not is it possible to implement in our current project structure?if not,pls also provide reasons

**A:**

### 1 · What multi-tenant means — an apartment building, not a row of houses

Build each customer their own house and you maintain fifty roofs, fifty boilers, fifty sets of
plumbing; fix a leak and you fix it fifty times. That is custom-deployment-per-customer, and it is
why selling to the next hotel would mean a rebuild.

Multi-tenant is **one building, many flats**. One roof, one boiler, one lift — shared and maintained
once. But every flat has its own front door with its own key, and **no tenant can ever get into
another's flat**.

In StayOps terms: the code, the evaluator, the adapters and the templates are the building. Each
hotel's rules, credentials, results and users are a flat.

**The word means two different things in this project, and that is the trap this answer exists to
prevent.** `spec/tenants/*.json` already exists — but those files are a hotel's *vocabulary and
policy*: status-code map, timezone, call budget, nominated rate codes. That is the **furniture in
the flat**. The documents mean the **locks on the doors**. We have the furniture and none of the
locks. Finding the word "tenant" here and concluding multi-tenancy is half-done is like finding a
`users.json` that holds font preferences and concluding the app has accounts.

### 2 · Did we implement it? No — verified two ways

**The front door has no lock.** `App._selection(query)` reads `?property=` straight from the URL and
falls back to the first configured property if it names nothing. There is no authentication
anywhere; `web/server.py` says so in its own module docstring: *"This demo has no authentication —
that is scoped out in `prd.md`."*

**The flats have doors and nobody checks the keys.** `runs.tenant_id` exists and every run records
it. Every query in `store/sqlite.py` was listed, and **not one filters on it**:

```
SELECT * FROM runs     WHERE run_id     = ?      <- not tenant
SELECT * FROM verdicts WHERE run_id     = ?      <- not tenant
SELECT ... FROM runs   WHERE control_id = ?      <- not tenant
```

The column D1 §46 requires is present; the enforcement D1 §44 requires is absent. `history()` asked
by one hotel would return every hotel's runs.

### 3 · Is it possible in the current structure? Yes, and the structure helps

Three things are already true, which is better than expected:

**`tenant` is already a first-class parameter, not an afterthought.** It is required positionally in
the deepest call in the system, and threaded onward through providers, evidence and the evaluator:

```python
def run(control_id: str, tenant: TenantConfig, adapter, clock: Clock, ...)
    budget   = budget or CallBudget(tenant.call_budget)
    evidence = gather(ir, adapter, tenant, clock, budget)
    verdicts = evaluate_population(ir, evidence.bundles, tenant.settings)
```

**A property is already data, loaded by id.** `TenantConfig.load(tenant_id)` reads a file and
`available_tenants()` discovers them from the directory — adding a hotel is already a file rather
than a code change (review finding F12, fixed in slice 1).

**Layers 1–5 need zero change.** Kernel, spec, providers, evidence and evaluator are pure or
data-driven; they do not know who is asking and do not need to. That is exactly why the gap report
scored this blast radius **4 rather than 5**: it adds a layer on top instead of reversing anything
underneath.

The work is bounded and almost entirely **additive**:

| What | Size |
| --- | --- |
| Auth layer + user/role model | **New** — does not exist at all |
| `_selection()` takes the tenant from the session, not the URL | one function |
| Tenant predicate on store reads — only `load` and `history`; `save` already carries it | **two methods** |
| Credentials keyed by tenant+provider rather than provider alone | one signature, but it changes the env contract |
| A structural test that no tenant-owned query lacks a tenant predicate | one test, in the style of the existing canonical-boundary grep |

### 4 · The honest caveats — "possible" is not "small"

**One change is genuinely code rather than configuration.**
`Credentials.from_environment(cls, provider: str)` keys on the provider alone
(`HOTELCONTROLS_<PROVIDER>_{USER,PASSWORD,HOTEL,BASE_URL}`), so two properties on the same PMS
cannot hold distinct credentials — the second overwrites the first. Already filed as **issue #22**
and open question 1.9. That is the second customer, not a scaling worry.

**The serial server is load-bearing, and the ordering matters.** `server.py` is explicit that this
is *"a correctness decision rather than a simplification"*: the store is one `sqlite3` connection, a
threading server answered its first run page with `500 ProgrammingError` **with the entire suite
green**, and *"`check_same_thread=False` would have turned an exception into a data race."* Its own
conclusion is the sequencing rule — *"if this is ever made threaded, the store has to become
thread-safe first."* For a pilot of a few properties, serial is fine, and the documents themselves
prescribe a shared database with tenant-scoped rows as the right initial choice.

**It is the largest single item in the roadmap** (effort 5, exposure 20) — but nothing gets undone.
Contrast guest-service *actions* (question 1.10), which would reverse a founding constraint.
Multi-tenancy reverses nothing.

**Why it was not built:** the PRD scopes out *"Authentication and multi-user access. Single-operator
demo."* The engine existed to prove a PMS-agnostic control can be evaluated honestly, and a login
screen proves nothing about that. It is a bank vault with excellent locks on the deposit boxes and
no front door on the building. Both matter, the order they were built in was not wrong, and the
building cannot open for business.

**Evidence:** read — `hotelcontrols/web/app.py` (`_selection`, `_tenant`, `_execute`),
`hotelcontrols/store/sqlite.py` (every `SELECT`/`WHERE`/`INSERT` enumerated by grep; public method
list: `close`, `save`, `load`, `history`), `hotelcontrols/store/schema.sql`,
`hotelcontrols/runner/run.py:111-123` (the `run()` signature), `hotelcontrols/spec/tenant.py` in
full, `hotelcontrols/providers/transport/http.py:146-157`
(`Credentials.from_environment(provider)`), `hotelcontrols/web/server.py:12-20,30-40` (the no-auth
and serial-server rationale, quoted verbatim above), `spec/tenants/sandbox.json`. Counted which
engine subdirectories already mention `tenant` (all nine). `docs/stayops-gap-analysis.md` §G5 and
`docs/prd.md` §6 for the scope decision. Issue #22 confirmed open via `gh issue list`. **Nothing was
run against a PMS and no code was changed** — this is an assessment of the existing tree.

**Status:** answered. The gap itself is tracked as **G5** in `docs/stayops-gap-analysis.md` with
Phase F of its roadmap; the credential half is **issue #22** and open question 1.9. No new open
question raised — the *decision* to build it is a scope call for the project owner, not an unknown.

---

## Q9 — 2026-10-02

**Q:** another followup on my above  multi-tenant question....with respect to PMS(for eg minihotel here) and hotels ,suppose I have hotel brand name "Raymond Hotels" which have 4 properties , Raymond Hotel-1 ,  Raymond Hotel-2 ,  Raymond Hotel-3,  Raymond Hotel-4...and suppose all using miniHotel PMS,then will it call as multi-teanant because I have more than one hotel properties listed? And what if  Raymond Hotel-1 use different PMS for eg MEWS  than other three properties ( Raymond Hotel-2 ,  Raymond Hotel-3,  Raymond
  Hotel-4 using miniHotel) ,how this will affect multi-tenanty? I am confueed about multiteancy

**A:**

Follow-up to **Q8**. The confusion is natural, because three independent things all get called
"multi-something".

### The short answer: no. Four properties is not multi-tenancy

| Axis | The question it answers | Raymond Hotels | State here |
| --- | --- | --- | --- |
| **Multi-property** | How many *buildings* does one customer have? | 4 | **works today** |
| **Multi-provider** | How many *different PMSs* are in play? | 2 | **works today** |
| **Multi-tenancy** | How many *mutually-untrusting parties* share the deployment? | **1 — just Raymond** | absent |

**The one-line test: count the parties who would sue each other, not the buildings.** Raymond
Hotel-2 and Raymond Hotel-3 are the same company, the same staff, the same accounts department.
Nobody needs walling off from anybody — that is **one tenant with four properties**. Multi-tenancy
appears only when Raymond Hotels *and* Hilton *and* an independent B&B share one deployment and
Raymond must never see Hilton's reservations. It is about **who is asking**, never about how many
buildings or how many PMSs.

### The four properties already work — run, not reasoned

The exact scenario was built as four tenant files in a scratch spec directory (three on MiniHotel,
one on a different PMS) and the same control run against all four:

```
raymond1  Raymond Hotel-1 (different PMS)  provider=demopms    calls=2  PASS=27 UNKNOWN=13 EXCLUDED=71
raymond2  Raymond Hotel-2                  provider=minihotel  calls=2  PASS=27 UNKNOWN=13 EXCLUDED=71
raymond3  Raymond Hotel-3                  provider=minihotel  calls=2  PASS=27 UNKNOWN=13 EXCLUDED=71
raymond4  Raymond Hotel-4                  provider=minihotel  calls=2  PASS=27 UNKNOWN=13 EXCLUDED=71
```

**Zero code changed — four JSON files**, each run carrying its own `tenant_id`. So multi-property
and mixed-PMS are both already solved, which is what the canonical boundary was built for:
`provider` is a field on a property's config and nothing above the adapter layer knows or cares.

**Therefore the PMS half of the question has a clean answer: mixing PMSs affects multi-tenancy not
at all.** Moving Raymond-1 to Mews is one line in one file.

### The counterintuitive part: mixing PMSs does not hurt, SHARING one does

Raymond-2, -3 and -4 are all on MiniHotel, and each property authorises its own API access, so they
need three different credential sets. Credentials are keyed by **provider only**. With one MiniHotel
credential set in the environment, all three were asked for theirs:

```
raymond2  provider=minihotel  ->  user=shared_user  hotel=H1
raymond3  provider=minihotel  ->  user=shared_user  hotel=H1
raymond4  provider=minihotel  ->  user=shared_user  hotel=H1
```

Identical. `Credentials.from_environment(provider)` **never consults `tenant_id`**. Three properties
on one PMS collide on one credential set — while Raymond-1, the odd one out on another PMS, is fine,
because its variables do not clash. That is **issue #22** and open question 1.9, and this group is
its perfect illustration: it bites on the *second property on the same PMS*, which is the common
case rather than an edge case.

This affects **live** calls only. Replaying captured fixtures needs no credentials, which is why all
four ran above.

### The isolation gap, in Raymond's own terms

All four runs were saved to one store and history requested:

```
history('inactive_room_future_stay')        ->  4 runs
history(self, control_id=None, limit=50)        <- no tenant parameter exists
```

There is no way to *ask* for one property's runs. If Hilton were also on this deployment, Raymond's
front desk would receive Hilton's runs. `tenant_id` is faithfully stored on every row and never
filtered — Q8's finding, now shown against a four-property group.

### The sharpest thing to take away

**What is currently called `TenantConfig` is really a `PropertyConfig`.** Its contents —
`provider`, `timezone`, `call_budget`, `status_map` — are all attributes of one building. One file =
one property = one PMS.

So **Raymond's four properties cannot be modelled as one customer today, because the only container
that exists IS the property.** The isolation boundary has to sit *above* today's `TenantConfig`:

```
TODAY                      WHAT THE DOCUMENTS WANT
TenantConfig (=property)   Tenant/Organisation -- "Raymond Hotels"   <- the lock lives here
  provider, timezone,        +-- Property "Raymond Hotel-1"  provider=mews
  status_map, budget         +-- Property "Raymond Hotel-2"  provider=minihotel
                             +-- Property "Raymond Hotel-3"  provider=minihotel
                             +-- Property "Raymond Hotel-4"  provider=minihotel
```

The documents anticipate this group exactly. D1 §5: *"For the initial implementation: Tenant =
Hotel"*, but *"the data model should allow a future hotel group structure: Organization → Hotel
A/B/C."* D1 §48 adds that if a customer operates 50 hotels the architecture must not prevent it,
*"but this is not required for the first release."*

**One consequence of the v1 "Tenant = Hotel" shortcut, worth knowing before choosing it:** under it
Raymond is *four* tenants, so Raymond's group finance director needs four separate grants and gets
**no consolidated view across their own four hotels**. For a four-property brand that is probably
the wrong model, and it is exactly why D1 §5 wants Organization in the data model from the start
even if the UI ignores it.

**Evidence:** **run, not reasoned.** A scratch copy of `spec/` was made outside the repository with
four added tenant files (`raymond1`–`raymond4`); `available_tenants()` discovered all six
properties; `run("inactive_room_future_stay", …)` executed against each via
`providers.registry.load(tenant.provider)` with a `FixedClock` at 2026-07-08, producing the table
above. `Credentials.from_environment` called for all three MiniHotel properties with one credential
set in the environment, returning identical values. Four runs saved to an in-memory `RunStore` and
`history()` called, returning 4; `inspect.signature(RunStore.history)` confirms no tenant parameter.
Read: `hotelcontrols/spec/tenant.py`, `hotelcontrols/providers/transport/http.py:146-157`,
`hotelcontrols/store/sqlite.py`. **No repository file was modified and no PMS call was made** — the
scratch spec directory lives outside the tree and the credentials were fake. Issue #22 confirmed
open earlier in this session.

**Status:** answered. No new open question: the group/property hierarchy is D1 §5 and §48, deferred
by the documents themselves, and the credential half is already **issue #22** / open question 1.9.
The *modelling choice* — Raymond as one tenant with four properties, versus four tenants — is a
scope call for the project owner and is recommended above rather than decided here.

---

## Q10 — 2026-10-02

**Q:** another followup on multi-tenant ,if every new customer(hotel/property) on minihotel pms will receive its own crredential,t then how rules from Hilton hotel would collide raymond hotel? I am still confused here.Also does miniHotel sotware support multi-tenant? What would be advantage of making this software multi-tenant?

**A:**

Follow-up to **Q8** and **Q9**.

### 1 · The collision is not in the data we read — it is in the data we produce

The intuition is right about one thing, and that is what hides the problem. MiniHotel **does** issue
each property its own credential, and that credential **does** correctly fence off their data. But
three different things are in play and credentials touch only one:

| Thing | Where it lives | Protected by a per-hotel MiniHotel credential? |
| --- | --- | --- |
| Reservations, rooms, folios — **data we read** | MiniHotel's servers | **Yes.** Working as intended |
| **The rules themselves** | **our** `spec/ir/` | **No.** MiniHotel has never heard of them |
| Run results, verdicts, evidence, history | **our** SQLite | **No.** Same |

**Credentials protect the data we READ. Nothing protects the data we PRODUCE.** Three concrete
collisions follow.

**Collision A — rules have no owner, so they are *shared* rather than colliding.** The IR schema has
18 keys and **not one** is `tenant`, `owner`, `customer` or `property`; checked by listing them. And
the control index is literally the directory:

```python
return tuple(sorted(p.stem for p in directory.glob("*.json")))
```

So Hilton's rules would not collide with Raymond's — **Raymond would see them**, on their own index
page. That is arguably worse than a collision: a hotel's control set is commercially sensitive. It
says which properties the chain does not trust on payment guarantees, and where it suspects staff of
overriding policy.

(Six IRs do contain the word "tenant", but only as `"tenant_setting": "nominated_rate_codes"` — a
rule *consuming* this hotel's configuration, not a rule *having an owner*.)

**Collision A2 — the id namespace is flat, so the same name overwrites.** The draft write is
unconditional:

```python
path = self.draft_dir / "ir" / ("%s.json" % control_id)
path.write_text(json.dumps(compilation.ir, indent=2) + "\n")
```

Hilton creates `late_checkout_policy`; Raymond creates `late_checkout_policy`; the second **silently
replaces** the first. The code already knows why that is dangerous — the existing guard stopping a
draft from shadowing a reviewed control says *"two rules under one id would make a stored run
ambiguous about which rule produced it."* Exactly right, one namespace up: today two **customers**
can do to each other what that guard prevents one operator doing to themselves.

**Collision B — results are pooled.** Per Q9, `history()` takes no tenant parameter.

**And the credential problem (issue #22) is a third, separate thing** — where the blame inverts.
MiniHotel separates Hilton's and Raymond's credentials perfectly. The failure is **ours**: we have
one drawer per PMS.

> The bank gives each property its own safe-deposit key. Our office has **one hook by the door
> labelled "MINIHOTEL"**. Hang Raymond's key on it and Hilton's is gone.

`HOTELCONTROLS_MINIHOTEL_USER` is a single global slot, so the vendor's separation is irrelevant if
we can hold only one key at a time.

### 2 · Does MiniHotel support multi-tenancy? Two senses, one of them unknown

**Is MiniHotel itself multi-tenant — yes, evidently.** It serves many hotels; `Credentials` carries
a `hotel` field, so one credential set is scoped to one property; and each property customises its
own status codes and posting categories (risk **A5**, which is the entire reason tenant *config*
exists in this repository).

**Does it offer a PARTNER model — one integration identity acting for many properties? Unknown.
UNVERIFIED.** Everything seen is per-property. The vendor's own words are that production
credentials arrive *"upon completion of the staging and testing phase"* and that IPs must be
whitelisted, with **no partner-certification process published anywhere reachable**. Whether forty
properties means forty credential sets and forty whitelisted IPs is genuinely open. **Added as
question 2.7** to the MiniHotel list: it is the first thing a group of any size will ask, and it
decides how issue #22 and open question 1.9 get built.

**Does MiniHotel's tenancy help ours? Barely, and this is the part to take away.** Even a perfect
partner model would only tidy the credential drawer. It would do **nothing** for rules, results,
verdicts or history, because none of those ever go near MiniHotel. **The vendor's multi-tenancy is
not a substitute for ours.**

### 3 · What multi-tenancy buys

**Commercially**

- **Customer N+1 is configuration, not a deployment** — no install inside the sales cycle.
- **One deployment to patch and monitor.** Fix a control bug once and every customer has it. The
  alternative is version skew across fifty installs, and bugs that exist only at customer 12 because
  nobody upgraded them.
- **One database, one process** rather than fifty of each.
- A **precondition for consolidated group reporting** across a brand's properties (Q9).
- Without it **D3 §86's Definition of Done cannot be met** — it names an isolated SaaS tenant
  explicitly.

**For correctness, which is underrated here**

- **The isolation tests become possible.** D3 §80 calls them mandatory; today there is no boundary
  to attack, so there is nothing to test.
- **"Whose is this?" becomes answerable.** An auditor asking *who ran this control, under whose
  authority, against whose property* has no answer today beyond a `tenant_id` nobody checked.

**The honest counterpoint, because it is not free**

- Single-tenant-per-customer has real advantages — smaller blast radius, data residency, and some
  enterprise procurement teams simply require it. The documents allow for it: a shared database with
  tenant-scoped rows *"unless specific customer/security requirements justify a separate database"*
  (D1 §46).
- It levies a **permanent tax**: every query must be tenant-scoped forever, and one missed `WHERE`
  clause is a data breach rather than a bug. That is why Phase F's exit test includes a **structural
  test**, in the style of the existing canonical-boundary grep, asserting that no tenant-owned query
  lacks a tenant predicate. Discipline will not hold; a test will.

**Evidence:** read and enumerated — `spec/ir_schema.json` (all 18 top-level properties listed, none
of them an owner), `spec/ir/*.json` (the eight `tenant` occurrences shown to be `tenant_setting`
references, not ownership), `hotelcontrols/spec/ir.py:144-151` and `tenant.py:146-152` (both
`available()` functions are a directory glob with no tenant filter),
`hotelcontrols/web/app.py:262-296` (the unconditional draft write and the shadow guard whose own
wording is quoted), `hotelcontrols/providers/transport/http.py:142-157` (`Credentials` carries
`hotel`; `from_environment` takes only the provider), `hotelcontrols/store/sqlite.py`. For the vendor
half: `docs/open-questions.md` §1.9 and `docs/QA.md` Q4, which hold the only statements we have from
MiniHotel — **both are quotations of vendor prose, not behaviour we observed**, and the partner-model
answer is therefore recorded as UNVERIFIED rather than inferred. **No PMS call was made and no code
was changed.**

**Status:** answered, with one part open. The partner/multi-property credential model is now
**question 2.7 for MiniHotel** in `docs/open-questions.md` — unknown, and not answerable from
anything in this repository. Everything about *our* isolation is answered: G5 in
`docs/stayops-gap-analysis.md`, Phase F of its roadmap, and issue #22 for the credential half.
