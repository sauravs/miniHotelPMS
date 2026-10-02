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
