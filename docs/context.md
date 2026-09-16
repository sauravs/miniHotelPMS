# Context — how we got here

Background a new session cannot infer from the code. For what we are building see `prd.md`; for the
design see `architecture.md`; for the build order see `plan.md`. For what v1 taught us, see
`old-codebase-improve.md`.

---

## Timeline

| When | What |
| --- | --- |
| 2026-08-31 | Task received: map 20 hotel controls to MiniHotel APIs, judge which are verifiable |
| 2026-09-01 | Documentation review of ~25 MiniHotel reference pages; feasibility workbook built |
| 2026-09-01 | **Live sandbox probing** — seven read-only calls. Found four defects documentation could not reveal |
| 2026-09-04 | Architecture doc received; 10-control dry run produced; Bulk ARI called for the first time |
| 2026-09-04 → 09-08 | v1 built: four silos, 152 tests, one control working end to end |
| 2026-09-08 | **Checkout probe** — seven more calls. Found the sandbox had moved on to 2026 data and held seven checked-out reservations. Control 6 reached PASS, FAIL and UNKNOWN on real records |
| 2026-09-08 | **v1 reviewed and measured.** Ran all 10 controls × 3 evidence sets: only 1 of 10 answers. v2 commissioned |
| 2026-09-09 → 09-15 | v2 built: twelve slices, twelve green pipelines. 11 of 12 criteria met, criterion 1 recorded as not met with its arithmetic |
| 2026-09-16 | **Slice 13 — the compose front end.** Prose → restricted sentence → the same grammar and the same validator. Decision D10 |

## The two source documents

Both were supplied by the project owner and both still govern.

**`Hotel Controls.docx`** — twenty governance controls as a table: a name, a MiniHotel/Mews
feasibility marker, and one example rule in plain English. It is written in an auditor's language,
not a schema's. The mapping from that English to API fields is the work.

**`control_rule_architecture.docx`** — twenty-five sections of design intent from the lead. The parts
that bind v2:

| § | What it requires | v1 | v2 |
| --- | --- | --- | --- |
| 1 | The rule must not contain PMS-specific information | done | kept |
| 2 | The customer types a sentence and sees a compiled control with field availability | **missing** | slice 9 + readiness; **slice 13 completes it** — `/compose` is the text box, and readiness was already on the page |
| 4, 22 | Logic and execution are separate objects | done in the IR | kept |
| 5–12, 23 | Trigger classification, freshness requirement, execution policy | declared, **ignored** | slice 8, as pure functions |
| 13 | Canonical field → per-provider endpoint + path + transformation | done | kept, made structural |
| 14 | PASS / FAIL / **UNKNOWN** — must not fail for missing evidence | done | kept, non-negotiable |
| 15, 16 | Readiness: "control readiness, 1 of 2 evidence sources connected" | **missing** | slice 6 |
| 17 | Six-stage pipeline, **never LLM → executable JSON directly** | 5 of 6 stages | all six, gate unchanged. Slice 13 adds a stage *before* stage 1 — prose → sentence — and the gate is still the only way through |
| 20 | Every violation must be explainable with an evidence table | done | kept, extended |
| 24 | The compiler produces a **population query**, not an IF statement | done | kept, plus reference sets |
| closing | Run 10 real controls through the architecture by hand before coding | done — `CONTROL_DRY_RUN.md` | that dry run is v2's specification input |

## What was verified, and how

Three passes against the vendor sandbox, and the order matters.

**Pass 1 — documentation.** All reference pages pulled as markdown. Produced the first feasibility
rating and risks R1–R8. Keyword sweeps were used only to prove the *absence* of entities (company,
package, rate-plan master), which is valid; concept mapping was done by reading, because the docx
speaks auditor's English and the API speaks schema.

**Pass 2 — live sandbox.** Seven read-only calls against `sandbox.minihotel.cloud` using the
credentials MiniHotel publishes in its own examples. Responses frozen as fixtures.
**Documentation review got 4 of 12 risks wrong.**

**Pass 3 — the checkout probe.** Seven more calls, staged and bounded, one second apart. Found that
the sandbox had **moved on to 2026 data**, that seven checked-out reservations existed, and that a
checked-out folio can be negative.

The lesson is now a rule: **if the documentation and a captured response disagree, the response
wins**, and a spec validator exists so that a claim cannot sit unchecked.

## The findings that shape the design

Each was found by calling the API, not by reading about it. Risk ids are carried forward from v1 so
the comments, the tests and the workbook all still cite the same identifiers.

| id | Finding | What it forces |
| --- | --- | --- |
| **R9** | A reservation and its own folio are in **different currencies** — `870 USD` vs `3262.5 ILS` on reservation `007003199` — and no exchange rate exists anywhere in the API | Money carries its currency or it is not evidence. Cross-currency comparison *raises*. Control 6 compares against literal zero, which sidesteps it entirely |
| **R10 / R12** | `0` usually means *"nobody configured this"*, not zero. 23 of 28 rooms report adult capacity `0`; some per-room prices are `0` on demonstrably paid bookings | `zero_is_unknown` on capacity and per-room price. Return UNKNOWN, never FAIL |
| **R1** | `GetReservationBalance` takes **one reservation per call**; there is no bulk journal endpoint | The population query exists. The call budget raises rather than truncating |
| **R8** | MiniHotel asks integrators not to query wide date ranges without agreement | Fixtures are the test set. No test touches the network. Live calls are opt-in and approved individually |
| **R2 / R3** | Three date formats in one API (`dd/MM/yyyy`, `yyyyMMdd`, `yyyy-MM-dd`), and `createDateTime` is **date-only** | Formats are parsed strictly and never fall back to each other. Same-day precision is impossible and must be stated, not implied |
| **R13** | Room type codes differ in case between endpoints (`EXECUTIVE` vs `Executive`); and a reservation's rate code and the ARI price-list code are **different key spaces** | Case-insensitive comparison. Control 9's evidence is unresolvable in MiniHotel and says so |
| **R7** | An OTA modification is a **cancel + recreate** reusing the same portal id; 7 of 11 sandbox bookings are direct and carry no portal id at all | Duplicate checks must exclude cancelled reservations *and* records with no channel id. "No channel id" is `not_applicable`, a distinct sentinel — never an empty string |
| **R11** | Rooms `9900`/`9901`/`9902` carry a type the room-type master does not define | A real latent defect in live data, found by running control 1. The engine reports it rather than crashing |
| **A5** | Reservation status codes and folio departments are **customisable per property** | Tenant configuration, not provider configuration. Unmapped codes resolve to UNKNOWN |
| — | A checked-out folio can be **negative**: `007004348` left at `−490.75 ILS`. The guest overpaid | Split into two controls — see the decisions below |
| — | **44 of 217 distinct reservations (one in five) carry a status this engine refuses to name** — `OK4` (32) and `WL` (12), neither documented anywhere | The honest cost of not guessing, and the cheapest open win available |
| — | VIP status and an approval exist only as **Hebrew free text** in `NonPrintedRemarks` — *"VIP policy is met. Approved by the manager on Telegram."* | The hotel is already writing control outcomes by hand, in prose. Whether that text is evidence is open question 3 |

## Decisions taken for v2, with reasons

Eight were put to the project owner on 2026-09-08 before any v2 document was written. All eight are
recorded here as decided.

| Decision | Chosen | Why |
| --- | --- | --- |
| **Scope** | All 10 dry-run controls made genuinely executable (11 IRs after the split) | v1 measured 1 of 10 answering. Three capabilities unlock nine controls; without them the product is one balance check wearing an architecture as a costume |
| **Dependencies** | Stdlib-only runtime; `pytest` + coverage as dev dependencies | The demo keeps its "no install step" property. TDD gets real tooling and CI gets a coverage floor. `xml.etree`, `decimal`, `sqlite3`, `http.server`, `zoneinfo` are all stdlib |
| **Live API** | Allowed, with per-call approval | Honours R8. Lets us refresh the 2024-era room findings the review flagged as stale, without opening the door to casual querying |
| **Second provider** | A fictional **DemoPMS speaking JSON** | Mews has no credentials and may not for months. The portability claim is the whole thesis and can be tested today for nothing. JSON rather than XML because the difference is the point |
| **NL compiler** | Deterministic grammar core, with an LLM adapter behind the same interface | §17 forbids LLM → executable directly. A grammar is testable offline and is what CI runs; a model becomes an optional front end whose output must pass the same validation. **Slice 13 took the optional front end up on this**, with the model one step further back still: it drafts the *sentence* the grammar parses (D10) |
| **Repository** | Public, with fixtures **pseudonymised** and credentials in environment only | The capture contains 27 guest emails and 30 phone numbers from someone else's sandbox. Stable fake identities keep tests deterministic; raw captures stay local and git-ignored |
| **Git workflow** | Branch per slice → PR → CI gate → squash-merge; bugs as Issue → `fix/` branch → PR closing it | Every slice reviewable, the gate mechanical rather than remembered |
| **Overpaid folio** | **Split control 6 into two controls** | Money owed is a collections problem and a probable loss; an unrefunded credit is a liability with a different urgency and often a different team. One queue makes severity meaningless for both. It is a spec change, and therefore also the first real test of criterion 6 |

### Added later

| When | Decision | Chosen | Why |
| --- | --- | --- | --- |
| 2026-09-09 | **D9** — wire the model adapter now? | **No. Build the seam, exercise it against a stub** | A stub tests the §17 gate harder than a real model does: it emits exactly the proposals that exercise it, where a real model mostly emits plausible IR. Full reasoning in `open-questions.md` |
| 2026-09-16 | **D10** — both authoring paths, with a chat window, **free to run** | **Yes — and the model produces a SENTENCE, not IR** | The intermediate is readable and editable; nothing new decides what a rule means; and a free 7B model run locally can rewrite a sentence into a template where it cannot reliably emit a valid six-key IR. Supersedes D9's "never a runtime component" clause only — D9's substance, *no verdict depends on a model call*, is kept verbatim |

## Scope decisions inherited from the project owner

- **MiniHotel only** among real PMSs, for now. Mews is designed for, not verified.
- **Read-only.** The hotel types *controls*, not operational commands. We never write to a PMS.
- The dry run used the **10 controls rated Yes**, rather than a spread across difficulty. Those ten
  are v2's specification input.

## What slice 13 did not change

Listed because a model appearing in a project that spent twelve slices avoiding one invites the
question. None of the following moved:

- **The engine still imports only the standard library.** Every model backend lives in
  `tools/proposers/` and is *injected*. Both AST guards — the stdlib walk and the compiler's
  network guard — passed **without being edited**, which was the design target.
- **The validator is unchanged and is still the only way through.** A drafted sentence is refused by
  the same code, with the same messages, as a hand-written IR file.
- **No verdict depends on a model call.** The evidence layer and the evaluator never learn a model
  exists. A composed control carries `confidence == 1.0` and `source == "grammar"`.
- **The criterion-1 figure is untouched.** Composed rules are drafts in `spec/drafts/` and are
  excluded from it by construction.
- **The default demo is unchanged.** `python3 -m hotelcontrols.web.server` wires no proposer.

## What carries over from v1 unchanged

Listed so nobody re-litigates them: the canonical boundary, UNKNOWN as a first-class result with a
reason, `EXCLUDED` as a fourth outcome, money carrying its currency and refusing cross-currency
comparison, `spec/` as data read at runtime, the call budget that raises rather than truncates, a
`Verdict` that cannot exist without evidence, fixtures as the only test evidence, Kleene
three-valued logic, high comment density citing risk ids, and the spec validator.

`old-codebase-improve.md` lists these as K1–K12 with the reasoning. They are not open for redesign.
