# Open questions

Everything this project knows it does not know, in one place. Each entry says what the engine
**will do today**, so nothing is blocked waiting for an answer — the current behaviour is always
defensible, and a decision *changes* it rather than unblocks it.

Four sections: decided (kept for the record), open for the project owner, questions for MiniHotel,
and engineering gaps chosen deliberately.

**Last reviewed:** 2026-09-09, after the twelve-slice build closed.

---

## The two that are worth the most

Everything below is open. These two are different, and they are recorded here at the top because
the build being finished changes what is scarce: **there is more value in these two sentences than
in any code that could be written this week, and only the project owner can supply them.**

| | What is needed | What it changes |
| --- | --- | --- |
| **[1.4](#14-which-rate-codes-has-the-property-nominated)** | Which rate codes this property has **nominated** | `required_reservation_fields` currently excludes every reservation and answers nobody. One list turns it into a working control. It is the cheapest movement available on success criterion 1 |
| **[2.1](#2-questions-for-minihotel)** | Ask MiniHotel what **`OK4`** and **`WL`** mean | **44 of the 217 distinct reservations this project has ever seen — one in five — carry one of those two codes**, and neither is documented anywhere. Each resolves to UNKNOWN, because a status nobody can name must not decide whether a control applies (A5). One sentence from the vendor resolves all 44, and it also settles [1.3](#13-is-the-cancel-and-recreate-pair-a-duplicate-or-the-expected-pattern) |

Neither is a gap in the engine. Both are facts about a property and a vendor that the engine has
correctly refused to guess at — which is the whole design working, and also the reason it is stuck.

A third, one step behind them and **already planned, printed and waiting**: approval for the three
read-only calls in [1.2](#12-are-the-2024-era-room-findings-still-true). `python3 -m tools.probe
--plan` prints the exact request bodies with placeholders where the credentials go, so there is
something concrete to approve rather than an intention. It is the first TODO a fresh session
should raise — see `docs/session-handoff.md`.

---

## 0. Decided — 2026-09-08

Put to the project owner before any v2 document was written. Recorded here because the reasoning
matters as much as the answer, and because reversing one of these is cheap now and expensive later.

| | Question | Decision |
| --- | --- | --- |
| D1 | How far should v2 reach? | **All 10 dry-run controls genuinely executable** (11 IRs after the control-6 split). v1 measured 1 of 10 answering |
| D2 | Keep "zero dependencies"? | **Stdlib-only runtime; `pytest` + coverage as dev dependencies.** The demo keeps its no-install property |
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

---

## 1. Open — for the project owner

### 1.1 Does an unverifiable exception count as a pass?

**The biggest product question, and it is unchanged from v1.** Most hotel controls read
*"X must not happen **unless approved**"*. MiniHotel exposes no acting user, no reason codes and no
audit trail, so the approval half is usually unanswerable.

**Today.** UNKNOWN, always. The engine will not turn a missing exception into a pass.

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

**Today.** v2 builds against the 2024 capture for these, marked as *unverified since the system
changed* — which is a different status from *verified*, and a different status again from *wrong*.

**Status: the probe is planned, printed, and waiting on one word.** Slice 11 built the transport
and `tools/probe.py`, so there is now a concrete artefact to approve rather than an intention:

```bash
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity
python3 -m tools.probe --plan --property sandbox --control resource_occupancy_consistency
```

`--plan` makes **no calls at all** and prints the endpoint, the resolved window, the cost against
this property's budget, and the **exact request body** with `<user>` and `<password>` where the
credentials go. Between those two commands it covers all three calls: `getRooms`, `getRoomTypes`
and `RoomStatusInquiry` over a deliberately small 7-day window (R8).

Three read-only calls settle four load-bearing findings and cost nothing but permission. What is
missing is the owner's yes to *this specific probe* (D3) and the four `HOTELCONTROLS_MINIHOTEL_*`
credentials, which have no defaults and never will (F15). The full runbook — what to do with the
responses, and why `tools/scrub_fixtures.py` runs before anything is committed — is in
`docs/session-handoff.md`, "The probe that is waiting approval".

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

**Today.** The tenant config ships with an empty nominated-rate-code list, so the control excludes
everything — which is honest but useless. One sentence from a property makes the control work.
**Checkpoint before slice 6.**

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

---

## 3. Engineering gaps chosen deliberately

Not questions — decisions, recorded so they can be reversed knowingly.

| Gap | Behaviour | Why |
| --- | --- | --- |
| **No scheduler daemon** | `next_evaluation` computes the plan; nothing executes it on a timer | The decision is the hard part and is testable. A loop around it is a day's work whenever it is wanted |
| **No webhook ingestion** | IRs declare their events; nothing subscribes | Requires a public endpoint, auth and replay protection — a different project |
| **No authentication** | Local demo, single operator | Out of scope by `architecture.md` |
| **`Value.source` carries a provider name** (`pms:minihotel/GetReservationBalance`) | Flows above the canonical boundary as data | An auditor must know which system and which call produced a number. **No PMS field path ever crosses.** The one deliberate exception to criterion 5, inherited from v1 and still correct |
| **Fixtures are pseudonymised** | Names, emails, phones and remarks replaced with stable fakes | Third-party personal data in a public repository is a legal question, not a style one. Structure, formats and every quirk are preserved exactly |
| **Free-text remarks unmapped** | Nothing reads them | Question 1.5 |
| **No FX source** | Cross-currency comparison raises; controls compare against literal zero | R9. Inventing a rate would be the single most damaging thing this engine could do to a finance team |
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
