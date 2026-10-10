# Open questions

Everything this project knows it does not know, in one place. Each entry says what the engine
**will do today**, so nothing is blocked waiting for an answer — the current behaviour is always
defensible, and a decision *changes* it rather than unblocks it.

Four sections: decided (kept for the record), open for the project owner, questions for MiniHotel,
and engineering gaps chosen deliberately.

**Last reviewed:** 2026-10-02, after reading the three StayOps documents the manager supplied
and comparing them against this engine. That comparison added
[1.10](#110-does-stayops-act-on-a-decision-or-advise-a-human),
[1.11](#111-which-of-the-nine-disagreements-between-the-three-stayops-documents-stand) and
[1.12](#112-do-our-four-outcomes-and-the-coverage-verdict-become-part-of-the-specification), and
changed what [1.5](#15-is-unstructured-free-text-an-evidence-source), [1.7](#17-mews) and
[1.9](#19-should-this-ever-touch-a-production-pms-and-whose-credentials-would-those-be) are worth.
Full report: `docs/stayops-gap-analysis.md`.

**Updated 2026-10-09** for slice 15: decision [D11](#d11--2026-10-09-slice-15-a-second-surface-in-react)
(a second, React surface) and three deliberate engineering gaps it made visible. No open question
changed.

**Updated 2026-10-09 again, for v3 planning** (`docs/plan-v3.md`). The owner decided D12–D16: guest
services in v3 as `LATE_CHECKOUT` only, the build order, where authentication lives, the guest
decision set and parameter names, and an evidence-refresh slice. That **closes 1.11 #1, #2 and #9**
and records the owner's position on **1.12**. Verification for the plan also found two claims that
did not survive a run: [1.4](#14-which-rate-codes-has-the-property-nominated) is **corrected**
(issue #49), and a new question for MiniHotel, [2.8](#2-questions-for-minihotel), comes from
issue #48.

---

## The two that are worth the most

Everything below is open. These two are different, and they are recorded here at the top because
the build being finished changes what is scarce: **there is more value in these two sentences than
in any code that could be written this week, and only the project owner can supply them.**

| | What is needed | What it changes |
| --- | --- | --- |
| **[1.4](#14-which-rate-codes-has-the-property-nominated)** | Which rate codes a **real** property has **nominated** | `required_reservation_fields` answers nobody. **Corrected 2026-10-09 (issue #49): one list is not enough.** `stay.rate_code` is absent from every captured reservation, so the control also needs a capture taken with room prices (v3 slice 23). And the sandbox is the vendor's test property: nobody can honestly nominate its codes |
| **[2.1](#2-questions-for-minihotel)** | Ask MiniHotel what **`OK4`** and **`WL`** mean | **44 of the 217 distinct reservations this project has ever seen — one in five — carry one of those two codes**, and neither is documented anywhere. Each resolves to UNKNOWN, because a status nobody can name must not decide whether a control applies (A5). One sentence from the vendor resolves all 44, and it also settles [1.3](#13-is-the-cancel-and-recreate-pair-a-duplicate-or-the-expected-pattern) |

Neither is a gap in the engine. Both are facts about a property and a vendor that the engine has
correctly refused to guess at — which is the whole design working, and also the reason it is stuck.

A third, the evidence refresh in [1.2](#12-are-the-2024-era-room-findings-still-true), is
**done** (v3 slice 23, 2026-10-10): three of its four findings are still true and the fourth was not
re-checked. It added 2026 occupancy and rate codes; criterion 1 on the new capture is reported
beside the old figure in `docs/plan.md`.

**And since 2026-10-02, one of a different kind, which outranks all three for *sequencing* while
being worth less than either of the two above for *unblocking*.**
[1.10](#110-does-stayops-act-on-a-decision-or-advise-a-human) asks whether StayOps carries out
what it decides or hands it to a person. The two questions above would each move a number this
week; 1.10 moves nothing today and decides what roughly half of the StayOps roadmap is allowed to
be. It is recorded down in section 1 rather than up here because the distinction this section draws
is *scarcity*, and 1.10 is not scarce — it needs a decision, not a fact somebody else holds.

---

## 0. Decided — 2026-09-08

Put to the project owner before any v2 document was written. Recorded here because the reasoning
matters as much as the answer, and because reversing one of these is cheap now and expensive later.

| | Question | Decision |
| --- | --- | --- |
| D1 | How far should v2 reach? | **All 10 dry-run controls genuinely executable** (11 IRs after the control-6 split). v1 measured 1 of 10 answering |
| D2 | Keep "zero dependencies"? | **Stdlib-only runtime; `pytest` + coverage as dev dependencies.** The demo keeps its no-install property. Still true of the engine since D11: the React UI's three runtime packages live in `ui/`, outside it |
| D3 | May we call the live sandbox? | **Yes, with per-call approval.** A specific bounded plan is proposed and approved before each probe (R8) |
| D4 | A second provider? | **Yes — a fictional `DemoPMS` speaking JSON**, offline. Mews when credentials exist |
| D5 | Build the NL compiler? | **Yes — deterministic grammar core, LLM adapter behind the same validation gate.** Never LLM → executable (§17) |
| D6 | Public repo with guest PII in fixtures? | **Pseudonymise fixtures, keep the repo public.** Credentials from environment only, no default |
| D7 | Git workflow? | **Branch per slice → PR → CI gate → squash-merge.** Bugs: Issue → `fix/` branch → PR closing it |
| D8 | Does an overpaid folio deserve its own outcome? | **Split control 6 into two controls** — money owed (`lte 0`) and unrefunded credit (`gte 0`). Different business events, different severities, different queues |

### D9 — 2026-09-09, before slice 9

**Should the `ModelCompiler` be wired to a real model, and to which?**

**Decision: no, not in slice 9. Build the seam; exercise it against a stub.** Four reasons, and the
second one is the structural one:

1. **A stub tests the gate harder than a real model does.** Slice 9's gate is that a sentence naming
   vocabulary nobody defined is rejected *by name*. A stub emits exactly the proposals that exercise
   it — an undeclared field, an unknown operator, an aggregate with no `group_by`, a predicate with
   two right-hand sides. A real model mostly emits plausible IR, which exercises the validator least.
   The thing under test is the gate, not the model.
2. **D2 forces a placement decision that slice 9 must not pre-empt.** `hotelcontrols/` may never
   import a third party, and reaching for `urllib` inside the engine to stay stdlib-pure would be
   worse code wearing a rule as a costume. So if it is ever wired, the model adapter belongs in
   `tools/` with the official SDK as a **dev dependency alongside pytest and coverage** — which is
   also what it honestly is: a drafting aid producing a spec artifact a human reviews and commits,
   never a runtime component. No verdict may ever depend on a model call.
3. **Sequencing.** Slice 11 already builds *opt-in, off by default, env-gated, credentials from the
   environment with no default, no test can enable it* for the PMS transport. Wiring a model in
   slice 9 builds that machinery a second time, three slices early.
4. **The seam is the irreversible part; the wiring is an afternoon.** What a real model buys is a
   *measurement* — how often a real proposal survives `ir.validate` — and that is a product
   experiment rather than a build gate. It is more interesting once there are more than eleven
   controls to compile, and no harder for waiting.

**If and when it is wired:** `claude-opus-5`, adaptive thinking, and **structured outputs**
(`output_config.format`) fed from `spec/ir_schema.json` — so the proposal arrives schema-shaped and
`ir.validate` is left testing *semantics* (does this field exist, does this join declare its key)
rather than JSON shape. Recorded here so the design stays available rather than rediscovered.

### D10 — 2026-09-16, slice 13. **Supersedes D9's placement clause.**

**Asked for:** both paths — controls filed as spec files *and* controls composed from prose in a
chat window in the UI, switchable. Constraint: **free to run.**

**Decision: build it, with the model producing a SENTENCE rather than an IR.**

```
prose → [model] → restricted English → [GrammarCompiler] → IR → [spec.validate] → run
                   ↑ shown, editable     ↑ deterministic, confidence 1.0
```

**What changed from D9, and what did not.**

D9 said the model adapter, if ever wired, is "a drafting aid producing a spec artifact a human
reviews and commits, never a runtime component. No verdict may ever depend on a model call."

The second sentence is **kept, in full**. A model drafts a *sentence*; the deterministic grammar
builds the rule; the validator accepts or refuses it; the evidence layer and evaluator never learn
that any of it happened. A composed control carries `confidence == 1.0` and `source == "grammar"`,
because the parse was exact whatever drafted the text. **No verdict depends on a model call.**

The first clause is what moved: the drafting aid is now reachable from the demo rather than only
from a script. D9's own reasoning survives the move intact — the client lives in `tools/`, the
engine imports nothing, and the proposer is *injected*:

- `hotelcontrols/compiler/sentences.py` holds a `SentenceProposer` **protocol** and takes one as a
  parameter. It cannot acquire one.
- Every backend lives in `tools/proposers/`. Nothing under `hotelcontrols/` imports it, asserted
  over the AST in `tests/unit/test_proposers_refuse_in_tests.py`.
- **Criterion 11 is unchanged and still met**, verbatim, for the engine. Both existing AST guards —
  `test_stdlib_only.py` and `test_compiler_grammar.py`'s network guard — pass **without being
  edited**, which was the design target rather than a happy accident.

**Why a sentence and not IR JSON.** Three reasons; the third decided it:

1. The intermediate is **readable and editable**. A person sees the restricted sentence and corrects
   it before anything compiles. Raw IR is reviewable in principle and unreviewed in practice.
2. **Nothing new decides anything.** A wrong field name is not bad IR that slipped through — it is a
   sentence the grammar refuses *by name*, which is §17's gate doing its job.
3. **It makes a free model adequate.** A 7B local model cannot reliably emit a valid six-key nested
   IR; it can reliably rewrite a sentence into a template. "Free to run" was a requirement, and
   asking for less is what satisfies it.

**Backends, pluggable behind one method.** `local` (Ollama on this machine, stdlib `urllib`, **zero
dependencies, zero cost** — the default) · `claude` (`claude-haiku-4-5`, ~¼¢ per attempt with the
vocabulary cached, optional `anthropic` extra) · `stub` (fixed replies, no model, what every test
wires) · `off`.

**Two locks, copied from the transport.** A live backend refuses unless `HOTELCONTROLS_COMPOSE=1`
**and** no test runner is loaded in the process. The local backend is held to this too: `localhost`
is still a socket, and a rule with one exception acquires a second. The test that sets the variable
is refused anyway.

**Drafts are not shipped controls.** A composed rule is filed in `spec/drafts/`, runnable
immediately, badged `draft · unreviewed`, and **excluded from the criterion-1 figure** — that number
is the most carefully-kept figure in this repository and a machine-drafted rule does not get to move
it. Promotion is a deliberate `git mv` plus `tools.validate_spec`.

**What is still not built:** no model is wired *by default* (the default backend is one you run
yourself), and the compose front end is off unless `tools/serve.py` starts it. `python3 -m
hotelcontrols.web.server` behaves exactly as it always has.

### D11 — 2026-10-09, slice 15. **A second surface, in React.**

**Asked for:** a React/Next.js UI. Two reasons, neither of them "React is better". The project owner
reads React more fluently than Python, and the engine will be patched into a JavaScript/Next.js
product. **Governing constraint, in the owner's words: "nothing may break; no core logic may
break."**

**Decision: an addition, not a rewrite.** `ui/` is a second *client* of the JSON API that already
existed. The server-rendered surface stays, working. It is the offline, printable, zero-dependency
audit surface, and retiring it would be a separate, later decision made on evidence. `prd.md` §6
now describes two surfaces, with the owner's sign-off.

**How "nothing may break" was made mechanical rather than promised:**

- On every `slice/15-*` branch a test failed if any engine file changed except `web/app.py`. The
  guard was seen failing on a planted kernel edit before it was relied on.
- The UI is tested from the engine's own answers (`fixtures/api/`, generated and byte-checked), so
  its suite needs no engine process and can never trigger a run.
- The UI re-proves criteria 2, 3, 8 and 10 on its own screen, including the four computed border
  styles in a real browser.
- The rules that matter most about `ui/` are enforced by the **required** Python suite: no parsed
  money, no PMS identifier, no injected HTML, one module that makes requests, exact pins.

**Three follow-on decisions, each put to the owner or taken against a written rule:**

1. **Compose writes, as JSON (option a, owner-approved).** Every other slice-15 route is read-only.
   Compose files drafts, so it needed `POST /api/compose` and `POST /api/compose/accept`. They share
   one core with the HTML window so the two cannot drift, write only `spec/drafts/` and the run
   store, and never touch a PMS. The alternatives were to link out to the engine's own window, or
   to defer compose.
2. **The plan line ("when this runs next", F7) comes from a new route, not a changed one.** A plan
   is a fact about the spec, like readiness. `GET /api/plan/<id>?property=&as_of=` serves it beside
   a stored run, so every existing route and golden stayed byte-identical.
3. **A run is a POST.** `GET /api/run/` spends provider calls and writes a row, and a React page
   can re-fire a GET for reasons nobody chose: a double render, a refetch on focus, a prefetch. The
   UI runs a control only from a button, then reads the stored run back for free.

### D12–D16 — 2026-10-09, planning v3

Put to the project owner in two batches while `docs/plan-v3.md` was written, after the gap report's
claims had been re-verified against `main`. Each has the alternative it beat. The governing
constraint is the owner's: **accuracy first, and it must not break.**

| | Question | Decision | Rejected, and why |
| --- | --- | --- | --- |
| **D12** | Is guest services (G1/G3) in v3? | **Yes: `LATE_CHECKOUT` only, and no model.** The request arrives structured (reservation, requested time). Every outcome is an advisory record (1.10) | *With model intake*: a model extracting the requested time from prose would put natural language in the **decision** path, where a misread "3" prices a fee. *Not in v3*: leaves half the StayOps Definition of Done unmet with the cheapest honest template available |
| **D13** | Build order (1.11 #9): isolation before or after the policy spine? | **Data isolation early, authentication last.** Slice 17 scopes every store query under a structural guard, so every table v3 adds is born scoped | *Spine first, isolation late* (the gap report's order): every new table retrofitted. *Full multi-tenancy first* (D3 §5): the largest, slowest start, and it needed D14 settled before anything else could move |
| **D14** | Where does authentication live, and how are per-property credentials held? | **The host product authenticates; the engine verifies a short-lived tenant context signed with HMAC** (stdlib `hmac`). The engine stores no passwords. PMS credentials stay in the environment, keyed per property (fixes #22). **Encrypted credential storage is deferred** with onboarding (G11), and if it is built, its dependency lives outside `hotelcontrols/` | *Engine owns auth* (stdlib `scrypt` + sessions): security-sensitive code in the one package whose job is honest verdicts. *No auth in v3*: leaves D3 §80's mandatory tests unwritable. A cryptography dependency in the engine would reverse D2 |
| **D15** | The guest decision set (1.11 #1), and `LATE_CHECKOUT`'s parameter names (1.11 #2) | **Five outcomes, spelled `STAFF_REVIEW`**: `APPROVED`, `APPROVED_WITH_FEE`, `DENIED`, `STAFF_REVIEW`, `UNAVAILABLE`. **Parameters from D2 §31, snake_case**: `free_until`, `charge_from`, `maximum_time`, `approval_required_after`, plus `fee_per_hour` (Money) and `hour_rounding`, **with no default**. Missing evidence is always `STAFF_REVIEW`; `UNAVAILABLE` and `DENIED` only from established evidence or stated policy | *Four, `NEEDS_STAFF_REVIEW`*: one mention of four. *D3 §33/§65 camelCase*: would be the only camelCase keys in `spec/`. *D2 §19*: less self-describing |
| **D16** | Should v3 include an evidence refresh (1.2, plus rate codes for #49)? | **Yes, as a planned slice whose first step is the owner's approval of each printed request at the time** (D3, R8). If approval never comes, the slice is skipped and nothing depends on it | *No live calls in v3*: several blocked items stay blocked for want of three read-only calls that are already planned and printed |

**Not ruled, because parameters dissolve it:** 1.11 #3, the two versions of the late-checkout
example. With per-hotel parameters they are simply two hotels' policies, and both go into the test
corpus with their own expected answers.

---

## 1. Open — for the project owner

### 1.1 Does an unverifiable exception count as a pass?

**The biggest product question, and it is unchanged from v1.** Most hotel controls read
*"X must not happen **unless approved**"*. MiniHotel exposes no acting user, no reason codes and no
audit trail, so the approval half is usually unanswerable.

**Today.** UNKNOWN, always. The engine will not turn a missing exception into a pass. Since
slice 18 a FAIL raises a task in the findings queue, and an UNKNOWN raises none, on purpose:
a queue that filled up with them would have answered this question by accident.

**What it decides.** Whether roughly nine of the twenty controls ship as review queues — *"here are
the twelve records that need a human to confirm an approval existed"* — or do not ship. Both are
defensible products; they are different products.

### 1.2 Are the 2024-era room findings still true?

The 2026 checkout probe found the sandbox has **moved on**. But only the reservation and balance
endpoints were re-probed. `getRooms`, `getRoomTypes`, `RoomStatusInquiry` and Bulk ARI were not, so
four load-bearing findings now rest on a 2024 snapshot of a system we know has changed:

- 23 of 28 rooms have adult capacity `0` (R12) — the entire argument for `zero_is_unknown`
- rooms `9900`/`9901`/`9902` carry a type `getRoomTypes` does not define (R11)
- all 28 rooms return an **empty closed-date window** — the reason controls 1d, 2 and 13 are rated
  Medium, and the reason control 2 excluded 100% of records in v1
- Bulk ARI is keyed by price-list code, not rate code (R13) — control 9 is unbuildable

**Answered 2026-10-10, by v3 slice 23 — capture `sandbox2026refresh`.** Four read-only calls,
each approved by the owner at the time it was made (D3, D16), each sent once, scrubbed before
staging. Each finding's verdict, naming the capture that gave it:

| finding | verdict on 2026-10-10 | evidence |
| --- | --- | --- |
| 23 of 28 rooms have no configured adult capacity (R12) | **Still true.** The same 23 rooms: 21 report `0`, and 808/809 carry no adult entry at all | `11_getRooms_2026-10.xml` |
| Rooms `9900`/`9901`/`9902` carry a type `getRoomTypes` does not define (R11) | **Still true.** Still `Double`; the room-type master still holds the same nine codes, none of them `Double` | `11_getRooms_2026-10.xml`, `12_getRoomTypes_2026-10.xml` |
| All 28 rooms return an empty closed-date window | **Still true.** None is set, so `ooo_room_protection` and `room_assignment_active_room` still apply to no record (2.4) | `11_getRooms_2026-10.xml` |
| Bulk ARI is keyed by price-list code, not rate code (R13) | **Not re-checked.** No Bulk ARI call was in the approved probe, and the request that produced the 2024 response was never recorded, so `tools/probe.py` cannot form one. It stays *unverified since 2024* | — |

**What did change**, none of it moving a verdict:

- **Room housekeeping status moved on 12 rooms**, and two codes appeared that no capture had shown,
  `R` (room 02) and `A` (room 102). Documented nowhere, they resolve UNKNOWN, and no control reads
  the field. The DemoPMS transcode writes them through unchanged, so both providers keep the gap.
- `SNG`'s description changed from a test string to `Single Room`.
- **2026 occupancy exists for the first time**: 35 segments for 21 reservations over 2026-07-08..07-15
  (`13_RoomStatus_2026-07.xml`). On this capture `resource_occupancy_consistency` concludes —
  31 PASS, 4 UNKNOWN — where it was blocked on every evidence set before (issue #9). It also showed
  two checked-in reservations with **no room assigned**, which the engine had grouped into a room
  called `False` and FAILed against each other: **issue #75, fixed (#76)**.
- **Rate codes are present** (#49): the 2026 reservation window asked again with room prices
  (`14_departures_2026-07_prices.xml`) carries `stay.rate_code` on 126 of 136 stays. Control 15
  still answers nothing, because the sandbox's nominated codes are *not decided* (1.4).

**How it was run**, for the next refresh. Print each call, get a yes to that call, then send it
with the same arguments plus `--run --yes` (#70: one call, sent once, no retry):

```bash
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity --endpoint getRooms
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity --endpoint getRoomTypes
python3 -m tools.probe --plan --property sandbox --control resource_occupancy_consistency
python3 -m tools.probe --plan --property sandbox --reask 9_departures_2026-07.xml --with IncludeRoomPrices
```

Then `tools.scrub_fixtures` over each raw response into a new file (#73 made it scrub the
occupancy response's guest names too), a new capture label in `fixtures/minihotel/index.json`
with its date and call count, and `tools.transcode_demopms`. Never an existing file.

### 1.3 Is the cancel-and-recreate pair a duplicate, or the expected pattern?

Portal id `test0000000N1` is shared by reservation `007003206` (status `CL`, cancelled) and
`007003207` (status `OK4`). v1 documented this as R7: **an OTA modification is a cancel plus a
recreate reusing the same portal id.**

Control 14 says *"two **active** reservations must not share the same OTA confirmation number"*. So
this pair is almost certainly the expected pattern, not a violation — but that turns entirely on
whether `OK4`, a status nobody has documented, means active. **See question 2.1.**

**Today.** Cancelled records are excluded from the group before counting, and `OK4` resolves
UNKNOWN, so the pair produces UNKNOWN rather than a false accusation. **Checkpoint before slice 5.**

### 1.4 Which rate codes has the property nominated?

`required_reservation_fields` (control 15) asks: *"every reservation in rate category X must contain
the required guest / company / payment information."* X is a property's own list, and nobody has
supplied one. In v1 the control excluded 71 of 108 records for exactly this reason and returned
zero answers.

**Before v3 slice 21.** The tenant config shipped with an empty nominated-rate-code list, so the control excluded
everything — which was honest but useless. ~~One sentence from a property makes the control work.~~
**Checkpoint before slice 6.**

**Corrected 2026-10-09 (issue #49). A list alone does not make the control work, on any evidence
held.** Measured: with `nominated_rate_codes: ["Tourist-BB"]`, sandbox2026 gives the same 0 PASS,
0 FAIL, 37 UNKNOWN and 71 EXCLUDED as with `[]`. `stay.rate_code` is **absent from all 108 captured
reservations**, because the captures were not taken with `IncludeRoomPrices`, which this control's
own IR says is required. The 2024 captures block the control outright. Two things are therefore
needed: **a capture taken with room prices** (v3 slice 23, D16) and **a list from a real
property**. The sandbox is the vendor's test hotel, so a list supplied for it would be an invented
policy moving the criterion-1 figure. v3 slice 21 also makes *"the hotel has not decided"* (`null`)
distinct from *"the hotel nominated none"* (`[]`), because today `[]` stands for both.

**Since v3 slice 21 (2026-10-09) the sandbox and demo tenants state `null`, not decided.** That
was the one declared verdict change of v3, dry-run at the slice-start checkpoint. The owner left
the decision to the implementer, who decided yes. It moved **no count and no outcome**: sandbox2026
and demo2026 still read 0 PASS, 0 FAIL, 37 UNKNOWN, 71 EXCLUDED. The 24 records whose scope the
list decides now read *"this property has not supplied 'nominated_rate_codes'"* instead of
*"stay.rate_code is unknown"*. Both are true, and the rate code's absence still shows on each
record's evidence row. The question stays open. What closes it is unchanged: a real property's
list and slice 23's capture.

### 1.5 Is unstructured free text an evidence source?

The sharpest finding of the whole project. MiniHotel has no VIP field and `market_segment` is empty
on every reservation. What it has is this, inside `<NonPrintedRemarks>`, in Hebrew:

> *"[GM] VIP upgrade: David Cohen — room 304 → 512 … **VIP policy is met. Approved by the manager on
> Telegram.**"*

Three things are true at once. The VIP status a control would need exists **only as narrative
prose**. So does **the approval** — the unanswerable half of question 1.1, sitting in a remarks
field, pointing at a chat app. And **the hotel is already writing control outcomes by hand**:
*"VIP policy is met"* is a person doing, in prose, what this engine does with evidence. That is the
manual process being replaced, found in the wild.

**Today.** Remarks are not mapped to any canonical field and nothing reads them. A control needing
VIP status returns UNKNOWN.

**The question, and why it is dangerous.** If free text becomes evidence, the natural-language
problem appears **twice** — once in the rule, once in the evidence — and the second is much the
riskier. An extractor would have to return a value **only with the exact quotation it relied on**,
and UNKNOWN whenever the text is ambiguous. Getting that wrong manufactures precisely the confidence
this product exists to refuse.

### 1.6 Control 9 — who supplies rate plan → permitted room types?

Unresolvable inside MiniHotel: a reservation's rate code (`Tourist-BB`) and the Bulk ARI price-list
code (`USD`) are different key spaces (R13). Either the hotel supplies the mapping as tenant
configuration, or we ask MiniHotel whether any endpoint resolves it.

**Today.** UNKNOWN for every record, with that reason — the "connect this to enable the control"
path, working as designed. v2 adds a tenant-config slot so a hotel *can* supply it.

**Corrected 2026-10-09 (issue #49): supplying the mapping alone changes nothing on the evidence
held.** With a populated mapping, sandbox2026 gives the same 0 PASS, 0 FAIL, 40 UNKNOWN and 71
EXCLUDED. 27 records stop at *"stay.rate_code is absent"* before the mapping is read, because no
capture was taken with room prices. Same remedy as [1.4](#14-which-rate-codes-has-the-property-nominated):
a capture with rate codes (v3 slice 23) and a real property's answer.

### 1.7 Mews

The canonical boundary exists so Mews is a second adapter and nothing more. v2 tests that claim with
DemoPMS, which makes the seam real — but Mews itself stays untested until there are credentials. It
remains the single most valuable thing that could be added to this project, because it is the whole
architectural thesis against a system nobody here designed.

### 1.8 Should the LLM adapter be wired to a real model?

**Answered for slice 9 by decision D9 above; the question itself stays open, because what is
undecided is *later*, not *now*.** The compiler's deterministic grammar needs no model and is what
CI runs. The `ModelCompiler` adapter exists so a sentence outside the grammar can still be proposed
as an IR — but it needs a model, a key, a cost decision and a privacy decision (control text is a
customer's own governance policy).

**Today.** The seam is built and exercised against a stub: `propose(sentence) -> dict`, and whatever
comes back goes through the same `spec.validate` a hand-written JSON file goes through. There is
nothing in `hotelcontrols/compiler/` to reach a model with — no `urllib`, no `http`, no socket, no
SDK — and a test asserts that over the AST.

**What wiring it would buy** is a *measurement* — how often a real proposal survives the validator —
which is a product experiment rather than a build gate, and it is more interesting once there are
more than eleven controls to compile. D9 records how it would be done if it is: `claude-opus-5`,
adaptive thinking, structured outputs fed from `spec/ir_schema.json`, living in `tools/` as a
drafting aid whose output a person reviews and commits. **No verdict may ever depend on a model
call.**

### 1.9 Should this ever touch a production PMS, and whose credentials would those be?

Raised by Q4 in `docs/QA.md`. Everything this project has ever seen came from
`sandbox.minihotel.cloud`. Production is a different host, and it has never been touched.

**Today.** Sandbox only, and that is the right target for verifying a control's logic: nothing about
whether `folio.balance_due lte 0` holds is better tested against real guests. Pointing the transport
at another host is configuration rather than code — but only for **one** property. Credentials are
keyed by provider alone (`HOTELCONTROLS_<PROVIDER>_{USER,PASSWORD,HOTEL,BASE_URL}`,
`Credentials.from_environment`), and the only caller passes `tenant.provider` and discards
`tenant.tenant_id` (`tools/probe.py`). Two properties on the same PMS therefore cannot hold distinct
credentials today; the second would overwrite the first.

**What the vendor says.** *"Production credentials will be provided upon completion of the staging
and testing phase"*, and *"before moving to production, it's essential to ensure your IPs are
whitelisted with us"*. No pricing, no rate limits and no partner-certification process are published
anywhere reachable — so whether production access costs anything is **unknown**, not free.

**Why it is a decision rather than a task.** Production credentials are **per-property and the
property's to give**. A hotel authorises access to its own data; this is not a key obtained once and
reused across customers. That changes three things at once — real guest PII becomes a GDPR question
rather than a style one (D6), R8 applies to a live property rather than a shared sandbox, and IP
whitelisting makes the machine that runs it matter. It also outgrows the keying above: a
per-property credential model needs the environment keyed by tenant, not by provider, which is a
code change rather than configuration. A single-property pilot does not hit this; a second property
on the same PMS does.

**What it would buy.** Real data volumes, real status codes in the wild — which would settle §2.1's
`OK4` and `WL` empirically rather than by asking — and real error behaviour, which is still
unobserved. None of that is needed to finish verifying the controls against the sandbox first.

**Recommendation.** Refresh the sandbox ([1.2](#12-are-the-2024-era-room-findings-still-true)), then
pilot with a real property that authorises its own production access. Not before.

### 1.10 Does StayOps act on a decision, or advise a human?

**Raised 2026-10-02 by the three StayOps documents. Gap G2 / question N1 in
`docs/stayops-gap-analysis.md`, where it is called the highest-value question in that report.**

Those documents add a second product capability — **Guest Service Rules** — in which a guest asks
for something and StayOps decides. *"Can I check out at 3 PM?"* → `APPROVED_WITH_FEE`, $25. And the
documents then describe what follows a decision: *calculate charge → create/modify service
request → respond to guest*, a maintenance request **created** and engineering notified, action
types `CREATE_SERVICE_REQUEST` and `CREATE_MAINTENANCE_REQUEST`.

**Today.** Nothing of guest services exists, and the engine **cannot write anywhere**. That is not
an omission — it is `prd.md` §6 (*"the hotel types controls, not commands. Read-only,
permanently"*), it is one file in the engine that imports an outbound client, and it is two locks:
the transport refuses unless its environment variable is set **and** refuses while a test runner is
loaded in the process, so the test that sets the variable is refused anyway.

**What it decides.** Which of two different products gets built:

| | What StayOps does | Cost |
| --- | --- | --- |
| **(a) advisory** | Decides, and hands staff a task. *"Late checkout until 3 PM: approved, $25. Confirm at the desk."* | The read-only rule survives untouched. Degrades honestly: if the charge is never posted, StayOps was still right |
| **(b) acting** | Posts the charge and creates the request in the hotel's system | **Reverses a founding constraint.** The HTTP client is the cheap part; the cost is that every write needs idempotency, rollback thinking, a model of who may authorise a charge, and credentials from each vendor that can write — none of which has ever been observed, read about or priced |

**Recommendation, and it keeps both futures open.** Ship **(a)**, and model every action as a
*record with a state* — `pending`, `done`, `dismissed` — performed by a human. If (b) is ever
chosen, an adapter performs the same record later and **the decision path does not change**. That
costs one indirection now and is the only version of this that does not have to be redone.

**Why it cannot be deferred quietly.** It is the difference between blast radius 2 and blast radius
5 on roughly half the roadmap, and *"we'll decide when we get there"* is in practice a decision for
(a) made without noticing — which is the right answer, but it should be the owner's.

**DECIDED 2026-10-09 by the project owner: (a) advisory.** StayOps decides and hands staff a task;
it never writes to a PMS, so `prd.md` §6's read-only rule stands unchanged. Every action is modelled
as a record with a state (`pending`, `done`, `dismissed`) that a person performs. Acting (b) is not
in scope; if it is ever proposed, it reopens this question rather than being built around it.
Built in v3 as slices 18 and 22 — see `docs/plan-v3.md`.

**Built, slice 22 (2026-10-10).** `POST /api/guest/requests` decides a late-checkout request by
the table in `spec/guest/late_checkout.json`, which the owner approved before any code, and every
decision except `DENIED` raises one `pending` task in slice 18's queue for a person to perform.
The task says what the engine did not do: it wrote nothing to the PMS, posted no fee, and did not
check whether the room is needed for an arrival (G12a). **Two things it raises, not decided:**
whether a guest task should be **emailed** like a violation's (slice 19's `dispatch` is scoped to
a run's FAILs, so today it is not), and whether the guest routes should get **golden payloads and
a React view** - both need `tools/dump_api_fixtures.py`, which was outside slice 22's may-change
line, so today the routes are proven by the Python suite and served by the engine's own page.

### 1.11 Which of the nine disagreements between the three StayOps documents stand?

**Raised 2026-10-02. Question N2 in `docs/stayops-gap-analysis.md` §6, where all nine are listed
with what each one breaks.**

The three documents are drafts at versions 1.0, 1.1 and 1.0, and they contradict each other in nine
places. Three need ruling before anything stores data, and they are the three a developer would
otherwise resolve silently — and resolve some of them wrongly:

| | The disagreement | Why it cannot wait |
| --- | --- | --- |
| **#1** | The guest decision set is four outcomes in one section of doc 02 and five in another, and `NEEDS_STAFF_REVIEW` in one place against `STAFF_REVIEW` in three | It becomes a stored enum on every decision ever made |
| **#2** | The flagship late-checkout template has **four different parameter name sets** across the three documents, in two different casings | The names go into a tenant's stored parameters and into a generated compiler prompt |
| **#9** | Build order. One document's seven-day plan never mentions multi-tenancy; another makes it Phase 1 and says *"implement before building the policy engine"*, while its own closing section says *"resist building a platform before proving the product — 1 hotel, 1 PMS, 1 control"* | They prescribe opposite first moves |

**Today.** None of it is built, so nothing is wrong yet — which is exactly why this is cheap now.
The gap report takes a position on #9 and says so openly (build the parameter mechanism against the
eleven controls that already exist and are already tested, then guest services inherits it), but a
position in a report is not a ruling.

**DECIDED 2026-10-09 by the project owner, for the three that could not wait:** #1 → five outcomes
spelled `STAFF_REVIEW` (D15); #2 → D2 §31's names in snake_case, plus `fee_per_hour` as Money and
`hour_rounding` with no default (D15); #9 → data isolation early, authentication last (D13). #3,
the two late-checkout examples, is dissolved rather than ruled: with per-hotel parameters they are
two hotels' policies, and both are tested. #4–#8 wait for the template that needs them. #8 (money's
type) needs nothing, because the engine already does what D3 says.

**One that is *not* a disagreement**, recorded so nobody fixes it: the suggested directory layout
(`stayops/apps/`, `services/policy/`). That document says itself that the architectural requirement
matters more than the layout and that an existing codebase should not be restructured to match. We
compare responsibilities, not folder names.

### 1.12 Do our four outcomes and the coverage verdict become part of the specification?

**Raised 2026-10-02. Question N3 in `docs/stayops-gap-analysis.md`. Unlike 1.10 and 1.11 this one
asks the owner to carry something *upward*, to the manager.**

The StayOps documents specify **three** outcomes. This engine has four, and the fourth is
load-bearing: **EXCLUDED** means the control does not apply to this record, and it is separate from
PASS because a record nobody examined has not passed. Every run also carries a **coverage verdict**
— `evaluated = PASS + FAIL`, and a run where that is zero renders as *"reached no conclusion"* with
no count tiles at all.

**Today.** Both are in the engine, enforced by tests, and inherited unchanged from v1. Neither is
in the documents.

**Why it needs saying out loud rather than leaving implied.** One of those documents contains a mock
dashboard: *8 Active · 1,284 Passed · 17 Failed · 6 Unknown*. No EXCLUDED tile, no coverage line.
Build that faithfully and a run where every record was out of scope renders as a clean bill of
health — and that is **measured, not hypothetical**: v1 reported 28 EXCLUDED / 0 FAIL for a control
on a property where the underlying mechanism had never been observed working, and on screen it was
indistinguishable from compliance. The next developer handed those documents and no ruling will
reproduce the mock, because reproducing the mock is what following the spec looks like.

**Three things to ask for, and the third is the cheapest and the most valuable:**

1. **EXCLUDED** as a fourth outcome.
2. **A coverage line** on any results screen, so `PASS + FAIL == 0` cannot read as success.
3. **`UNKNOWN` as a member of every canonical enumeration, including reservation status.** Both
   documents require that an unmapped provider value must never be guessed at and must resolve to
   UNKNOWN — and then define `ReservationStatus` as a closed set of six values with no UNKNOWN
   member, so **the rule cannot be implemented in the type they specify.** Here that is not
   theoretical: `OK4` and `WL` are one in five of every reservation this project has ever seen
   ([2.1](#2-questions-for-minihotel)), and the specified enum cannot represent any of them.

**2026-10-09: the owner's position is yes, and the owner will carry all three to the manager.** The
manager's answer is pending, so this stays open as a *specification* question. It is closed as an
*engineering* one: v3 keeps all three, and its criteria (V5, `docs/plan-v3.md`) require EXCLUDED
and the coverage verdict on every new surface it adds. Removing any of the three would widen
verdicts.

---

## 2. Questions for MiniHotel

1. **Is there a published list of reservation status codes?** `OK4` (32 reservations) and `WL` (12)
   appear in live data and in no documentation we have — **44 of the 217 distinct reservations we
   have ever seen, one in five.** We refuse to guess (A5), so every one of them makes a control
   unable to answer. A single sentence would resolve all 44, and it would also settle question 1.3.
2. **What does a negative `TotalDebit` mean officially** — an overpayment, a pending refund, or an
   accounting artefact? Decision D8 was taken on inference; this would settle it on fact.
3. **Is there any bulk folio or journal endpoint?** `GetReservationBalance` takes one reservation per
   call (R1). This is the main scalability constraint on the entire design.
4. **What is the format of `rm_clsdt1` / `rm_clsdt2`?** Never observed populated on any room, so the
   out-of-service mechanism has never been seen working. Controls 1d, 2 and 13 depend on it — and if
   the format differs from the docs, they would **silently pass everything**.
5. **Does any endpoint resolve a reservation's rate code to permitted room types?** (Control 9.)
6. **Agreed rate limits and windows** for a production integration (R8).
7. **Is there a partner or multi-property credential model, or is it strictly one credential set per
   property?** Raised 2026-10-02 by Q10. Everything we have seen is per-property: `Credentials`
   carries a `hotel` field, and the vendor's own words are that *"production credentials will be
   provided upon completion of the staging and testing phase"* and that IPs must be whitelisted —
   with **no partner-certification process published anywhere reachable**. So whether one
   integration identity can act for many properties, or forty properties mean forty credential
   sets and forty whitelisted IPs, is **unknown**. It decides how
   [1.9](#19-should-this-ever-touch-a-production-pms-and-whose-credentials-would-those-be) and
   issue #22 are built, and it is the first thing a hotel group of any size will ask. **It does not
   affect our own isolation work either way** — our rules, runs and verdicts never reach MiniHotel,
   so no credential model the vendor offers can isolate them (Q10).
8. **What does `<CreditCard Type="" Number="****" NameOnCard=" " ExpirationDate="202101"/>` mean?**
   Raised 2026-10-09 by issue #48. All 228 card elements across every capture carry
   `Number="****"` with no last four digits, so "a card is on file" is true of every reservation we
   have ever seen. 216 of them expire in January 2021, on reservations dated up to 2026. Is that a
   default the PMS emits when there is no card, a masked real card, or either? Until the vendor
   says, or a capture shows a reservation known to have no card, **card presence is not
   established**, and the StayOps payment-guarantee control (gap G4) stays blocked even in its
   narrowed form. **Today (since the fix for #48):** on both providers a card number that is a
   mask with no digits, or blank, resolves UNKNOWN naming #48 and this question. Only digits the
   mask did not hide would read as presence, and no capture has shown one.

---

## 3. Engineering gaps chosen deliberately

Not questions — decisions, recorded so they can be reversed knowingly.

| Gap | Behaviour | Why |
| --- | --- | --- |
| **No scheduler daemon** | `next_evaluation` computes the plan; nothing executes it on a timer. Since #42, `/api/plan` calls it on demand to *show* the plan | The decision is the hard part and is testable. A loop around it is a day's work whenever it is wanted. **v3 defers it for a further reason:** a loop means something only over live evidence, and continuous calls need MiniHotel's agreed limits (2.6) and per-property credentials. When it comes it is a separate process with its own store connection (`docs/plan-v3.md` §6) |
| **No webhook ingestion** | IRs declare their events; nothing subscribes | Requires a public endpoint, auth and replay protection — a different project |
| **No authentication** | Local demo, single operator. That includes the compose write routes on both surfaces | Out of scope by `architecture.md`. **Planned for v3** as slice 24: the host authenticates and the engine verifies a signed context (D14). Until then, `?property=` is a selection, not an identity. **Since slice 17 the selection is honoured all the way down**: the store refuses an unscoped read, and another property's run is a 404 |
| **The engine's web server is serial** | One request at a time. The React index asks for all eleven controls' readiness in one request (`/api/controls`) rather than eleven | The run store is a single-thread SQLite connection. A threaded server answered its first page with a `ProgrammingError` while the whole suite was green. The store must become thread-safe first, and that is core logic |
| **The React UI's CI job is not required** | `npm` failures show as a red `ui` check but never block a merge | A registry outage or a browser download must never block an engine fix. The UI's most important rules are duplicated into the required Python suite for exactly this reason |
| **`Value.source` carries a provider name** (`pms:minihotel/GetReservationBalance`) | Flows above the canonical boundary as data, and onto both screens | An auditor must know which system and which call produced a number. **No PMS field path ever crosses.** The one deliberate exception to criterion 5, inherited from v1 and still correct. The React UI displays it whole and never splits or branches on it; a required test fails if a vendor name appears anywhere in `ui/` |
| **Fixtures are pseudonymised** | Names, emails, phones and remarks replaced with stable fakes | Third-party personal data in a public repository is a legal question, not a style one. Structure, formats and every quirk are preserved exactly |
| **Free-text remarks unmapped** | Nothing reads them | Question 1.5 |
| **No FX source** | Cross-currency comparison raises; controls compare against literal zero | R9. Inventing a rate would be the single most damaging thing this engine could do to a finance team |
| **A run's identity does not include its rule** (slice 16) | `make_run_id` hashes control, property, provider, evidence, `as_of` and `created_at`, but not `policy_version`. In the demo, whose clock is fixed at the capture's instant, re-running the same question after a rule's version bump **replaces** that row. The replacement always carries the new rule's verdicts **and** its version together; history groups by version and digest | `docs/plan-v3.md` §6.6: every stored run and golden keeps its identity, and idempotency lives on the action record (slice 18), not on `run_id`. Outside the fixed-clock demo `created_at` differs, so two versions are two rows. Reversing it would change all 88 run goldens' ids |
| **Occupancy is a projection, not a native record** | Assembled by a declared join from sibling lists | The provider genuinely has no single block per occupancy record. Where a projection cannot be defined, the control is blocked **by name**, not crashed |

---

## Recently closed

Kept briefly, because *how* they closed matters more than that they did.

- **"The sandbox has no checked-out reservation."** *Closed — it was wrong.* Inferred from one 2024
  capture taken with an **arrival** filter. Seven authorised calls found seven checked-out
  reservations. The lesson: asking the server cost seven calls; assuming cost a wrong conclusion
  that looked strong.
- **"Does the server accept `BookingSearch Status='OUT'`?"** *Closed — yes.* The control 6 IR had
  claimed that filter since it was written and no call had ever exercised it. It narrows 65 bookings
  to 1, which also confirms the `1 + N` cost is per checkout, not per departure.
- **"Where does per-tenant configuration live?"** *Closed by v2 design* — a `spec/tenants/*.json`
  object, not constants in a provider module. Status codes and folio departments describe one
  hotel's vocabulary, not the provider's API.
- **"Is the canonical namespace right?"** *Closed by use* — 52 fields, hardened across ten IRs, an
  engine and two providers. Renaming remains a spec edit plus a validator run.
