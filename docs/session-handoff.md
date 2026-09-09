# Session handoff

Paste the block below into a fresh session to resume. Everything it references is in the
repository; nothing depends on the previous conversation.

**Last updated:** 2026-09-09, after slice 11 and fix #16 merged. **The twelve-slice build is
complete.** What a fresh session does next is decided by the project owner, not by this plan.

**One thing is already queued and waiting on the owner** — the bounded three-call probe of the live
sandbox. It is planned, printed, and blocked on one word and four environment variables. Read
[The probe that is waiting approval](#the-probe-that-is-waiting-approval--the-first-todo) before
anything else.

---

```
Continue building miniHotelPMS. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

Read these first, in order: CLAUDE.md, docs/plan.md, docs/prd.md, docs/architecture.md,
docs/open-questions.md, docs/old-codebase-improve.md. They are the specification and the
execution tracker; docs/plan.md is authoritative for what is done and what is next.

STATE: ALL TWELVE SLICES ARE MERGED (PRs #1-#8, #10-#15, #17, #18 on
github.com/sauravs/miniHotelPMS). 1501 tests, 96% coverage, 1080 spec checks, CI green on
Python 3.11 and 3.13.
ELEVEN OF THE TWELVE SUCCESS CRITERIA ARE MET. Criterion 1 is recorded as NOT MET - 5 of 11
controls reach a PASS or a FAIL where the PRD asks for 8 - with each of the six shortfalls
traced to a fact about the property or the provider in docs/plan.md. DO NOT relax it.

TODO #1, AND IT IS WAITING ON THE OWNER, NOT ON CODE: a bounded three-call probe of the
live MiniHotel sandbox is planned, printed and approved-pending. Print it and show it:

    python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity
    python3 -m tools.probe --plan --property sandbox --control resource_occupancy_consistency

That is getRooms, getRoomTypes and RoomStatusInquiry - the three calls open question 1.2
asks for. It refreshes four load-bearing findings that now rest on a 2024 snapshot of a
system we KNOW has moved on. --plan makes no calls at all. DO NOT run --run without the
owner saying yes to that specific probe, each time (decision D3). It will refuse anyway
without HOTELCONTROLS_LIVE=1 and the four HOTELCONTROLS_MINIHOTEL_* credentials, which
have no defaults. See "The probe that is waiting approval" in docs/session-handoff.md.

THERE IS NO SLICE 12. The build plan is finished. Before starting anything, read the
"Where this leaves the build" section of docs/plan.md and the open decisions below - the
most valuable things left are conversations rather than code, and two of them would move
criterion 1.

If asked to build something anyway, the candidates in rough order of value are:
  - Mews as a third provider. It is the whole architectural thesis against a system nobody
    here designed. Needs credentials that do not exist (open question 1.7).
  - A scheduler daemon around next_evaluation(), and webhook ingestion. Both are scoped out
    deliberately in architecture.md section 6, with what each would take.
  - Wiring the ModelCompiler to a real model, as a dev-time tool under tools/ with the SDK
    as a dev dependency. Decision D9 records how, and why it is not a runtime component.
  - Free text as evidence (open question 1.5). Read it before agreeing: it is the sharpest
    finding in the project and the most dangerous thing that could be built.

Keep working the same way:
  - TDD. Failing test first, written from the specification rather than from the code you
    intend to write. Every test names the IR clause, success criterion or risk id it protects.
  - One branch per slice (slice/NN-name) -> push -> PR -> CI must pass -> squash-merge.
    Bugs found outside the current slice get a GitHub issue FIRST, then fix/NN-desc, then a
    PR closing it. Update the slice table in docs/plan.md as you go.
  - Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.transcode_demopms --check
  - Zero runtime dependencies. pytest and coverage are dev-only and hotelcontrols/ may never
    import them. Coverage floor is 90%; raise it by adding real tests, never by lowering it.
  - High comment density, explaining WHY and citing the risk id (R1, R7, R9, R12, R13, A5).
  - Never widen a verdict. Missing evidence is UNKNOWN. This outranks every other instruction.
  - Never edit a fixture to make a test pass, and never invent one to reach a nicer outcome.
    fixtures/demopms/ is GENERATED - change tools/transcode_demopms.py and rebuild.
  - Do not call the MiniHotel sandbox without asking me first, each time (decision D3).

Work autonomously through the remaining slices, reporting after each merge. Ask me only when a
decision is genuinely mine to make.
```

---

## What a fresh session needs to know that the docs do not spell out

### Decisions already taken — do not re-litigate

Recorded as D1–D9 in `docs/open-questions.md` §0. In short: all 10 dry-run controls made
executable (11 IRs after splitting control 6); stdlib-only runtime with pytest as a dev
dependency; live sandbox calls allowed but approved individually; a fictional JSON `DemoPMS` as
the second provider; a deterministic grammar compiler with an LLM adapter behind the same
validation gate; public repo with pseudonymised fixtures; PR-per-slice with a CI gate; control 6
split into `checkout_money_owed` and `checkout_unrefunded_credit`; and **D9 — the model adapter
is a seam exercised against a stub, not a wired model.**

### What slices 9, 10 and 11 built, in three paragraphs

**Slice 9, the compiler.** `hotelcontrols/compiler/` — a restricted-English sentence compiles to
an IR; the IR goes through `spec.validate`, unchanged and unbypassed. The model seam is one
method, `propose(sentence) -> dict`, and its refusals are compared against `spec.validate` called
directly on the same document, message for message. Each control carries **two** sentences: the
prose a person wrote, and the controlled form. **The grammar parses 0 of the 11 prose sentences
and 11 of 11 restricted forms**, and a test fails if the first number rises — a lexicon that knew
"still owes money" would be an eleven-entry phrase book. A sentence cannot supply a
`population.provider_query` without naming a PMS, so the document splits: sentence owns the rule,
a *deployment* dict owns the query, trigger, freshness and action.

**Slice 10, the demo.** `hotelcontrols/web/` — `handle(path) -> (status, content_type, body)` is a
pure function of the path, so the whole demo is asserted as strings. UNKNOWN is told apart from
FAIL by wording (asserted with every tag stripped), border style and hue. A run that concluded
nothing, and a blocked run, show **no count tiles**. `as_of` defaults to the instant the capture
declares it describes.

**Slice 11, the transport.** `hotelcontrols/providers/transport/` is built, tested and **off**.
Two locks: an environment variable, and a refusal to arm while a test runner is loaded — because
an environment variable alone is a lock a test opens in one line. Exactly one file in the engine
imports an outbound HTTP client. `providers/minihotel/live.py` holds the request forms,
**transcribed from the calls that produced the captures**, never from documentation; `BulkARI` is
refused because its request was never recorded. `python3 -m tools.probe --plan` prints the
endpoint, the resolved window, the stage, the cost against the property's budget and the exact
request body, with `<user>` and `<password>` where the credentials go — so the thing being
approved (decision D3) is the thing that would happen.

### Success criterion 1 is recorded as NOT MET, and stays that way

5 of 11 controls reach a PASS or FAIL; the PRD asks for 8. **Do not relax the criterion.** The six
shortfalls are traced one by one in `docs/plan.md`, and none is a defect in the engine. Three
would move on a conversation rather than on code.

It was 6 until issue #9 was fixed: `resource_occupancy_consistency` had been reaching two PASSes
about July 2026 from occupancy segments captured in August 2024, because the frozen source's
window guard checked three filter names instead of every window. **That is the shape of defect
this project exists to catch, and the number went down rather than the guard going away.**

### The probe that is waiting approval — the first TODO

**Status: planned, printed, and blocked on the owner.** Not on code, not on a decision anybody
here can make. Nothing about it is half-built — the plan exists, the transport exists, and the
only missing inputs are one "yes" and four environment variables.

**Print it first, always:**

```bash
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity
python3 -m tools.probe --plan --property sandbox --control resource_occupancy_consistency
```

`--plan` makes **no calls at all** — a test asserts that by making `FrozenSource.fetch` raise and
running the whole plan anyway. It prints the endpoint, the resolved window, the stage, the cost
against the property's budget, and the **exact request body**, with `<user>` and `<password>` where
the credentials go. That is the artefact decision D3 approves: the thing being approved is the
thing that happens.

**The three calls, and what each settles** (open question 1.2):

| call | what it settles |
| --- | --- |
| `getRooms` | Whether 23 of 28 rooms still report adult capacity `0` (R12 — the entire argument for `zero_is_unknown`); whether rooms 9900/9901/9902 still carry an undefined type (R11); and **whether any room now has a closed-date window set**, which is why `ooo_room_protection` and `room_assignment_active_room` currently exclude every record |
| `getRoomTypes` | The other half of R11 — are the codes still the nine we have |
| `RoomStatusInquiry` | A **7-day** window, deliberately small (R8). The only occupancy capture is stuck at one week of August 2024, which is why `resource_occupancy_consistency` is blocked on both evidence sets |

**To run it, once the owner has said yes to this specific probe:**

```bash
export HOTELCONTROLS_LIVE=1
export HOTELCONTROLS_MINIHOTEL_BASE_URL=...      # the sandbox host
export HOTELCONTROLS_MINIHOTEL_USER=...
export HOTELCONTROLS_MINIHOTEL_PASSWORD=...
export HOTELCONTROLS_MINIHOTEL_HOTEL=...
python3 -m tools.probe --run --yes --property sandbox --control room_assignment_type_validity
```

There are no defaults for any of those and there will not be any (F15). The transport refuses
without them and names the variable that is missing. **Never put a credential in a file in this
repository** — v1 hard-coded the vendor's published sandbox account in a file about to be pushed
public, which was defensible and made the habit dangerous.

**Afterwards, in this order:**

1. Responses land in `fixtures/minihotel/raw/`, which git ignores, each with the request that
   produced it. **Run `python3 -m tools.scrub_fixtures` before committing anything derived from
   them** — a live response carries guest names, emails, phone numbers and free-text remarks, and
   this repository is public (D6, F15).
2. Compare against what the 2024 capture says and **update open question 1.2 with what was
   actually found**, whichever way it goes. The four findings there are currently marked
   *unverified since the system changed*, which is a different status from *verified* and a
   different status again from *wrong*.
3. If closed-date windows now exist, the occupancy **reference** request needs a window too — it
   carries none today, so `providers/minihotel/live.py` refuses it as the unbounded query R8
   forbids. Deliberately left: that control excludes all 28 rooms anyway while no window has ever
   been seen. It becomes worth fixing the moment one is.
4. The first real call is also the first observation of this vendor's **error** behaviour. Issue
   #16 classified failures by status code, which is standard HTTP and needed no observation; what
   their error *bodies* look like is still unknown and stays unguessed until one is seen.

---

### Checkpoints that need the project owner

| Before | Decision |
| --- | --- |
| **now** | **Approval for the bounded three-call probe that is already planned and printed** — `getRooms`, `getRoomTypes`, `RoomStatusInquiry` (D3, open question 1.2). See the section above; this is the first TODO |
| any time | **The cheapest open win:** which rate codes this property has nominated for control 15 (open question 1.4). One sentence takes `required_reservation_fields` from zero answers to real ones |
| any time | Ask MiniHotel what `OK4` and `WL` mean (question 2.1). They cover 44 of the 217 reservations ever seen, and they are why the known duplicate pair resolves to UNKNOWN rather than to an answer |

### Things that will look like bugs and are not

- `ooo_room_protection` excludes all 28 rooms, and `room_assignment_active_room` all 111 stays.
  No room in this property has ever had a closed-date window set (open question 2.4). The
  coverage verdict reports this rather than showing a reassuring zero.
- `room_capacity_compliance` answers for nobody: 23 of 28 rooms report adult capacity `0`,
  which means *unconfigured*, not zero (R12). On DemoPMS the same rooms report `-1`, and the
  canonical answer is the same UNKNOWN.
- `rate_room_category_consistency` is UNKNOWN everywhere on both providers. A reservation's rate
  code and a price-list code are different key spaces (R13) — structurally unresolvable.
- `resource_occupancy_consistency` is **blocked** on both standard evidence sets, and concludes
  perfectly well asked on 14 August 2024. See issue #9 above.
- Neither aggregate control reaches FAIL. The property genuinely has no active duplicate and no
  double-booked room. **Do not manufacture one.**
- The two providers **disagree about scheduling, on purpose**: `resource_occupancy_consistency`
  is event-driven on MiniHotel and hourly on DemoPMS, because only one publishes
  `room.occupancy_updated`. Criterion 7 is about verdicts, and those are identical.
- The grammar refuses *"every reservation arriving within 24 hours must …"* — the shape the
  requirements doc uses. That is deliberate and is explained in the refusal itself: a window on
  arrival bounds the population, which is per-provider deployment data.
- `--run` on the probe refuses even with `HOTELCONTROLS_LIVE=1` and `--yes`, inside a test. That
  is lock 2 and it is deliberate. Outside a test it refuses too, at the missing credential — the
  only thing between here and a live call is real credentials, which is exactly what D3 wants.
- The demo's history is in-memory and empty when the server restarts. `RunStore(":memory:")`
  is the default; point it at a file to keep runs between sessions.
- Every run over the 2026 captures reports its evidence as *captured after the instant asked
  about*. That is true — the bytes were fetched in September for a question about July — and it
  is neither stale nor fresh.
- `miniHotelLegacy/` is git-ignored on purpose: it holds unscrubbed guest data and hard-coded
  sandbox credentials, and this repository is public.

### Where the interesting parts are

| | |
| --- | --- |
| `hotelcontrols/kernel/` | `Value`, `Money` (Decimal), `Outcome`, `Verdict`, `Clock`. Five guarantees enforced in constructors |
| `hotelcontrols/spec/ir.py` | The validation gate everything writes through — six checks beyond the schema |
| `hotelcontrols/compiler/grammar.py` | Restricted English → IR, and the refusals that make it safe |
| `hotelcontrols/compiler/model.py` | The model seam. One method in, the same gate out, no network |
| `hotelcontrols/providers/registry.py` | adapters discovered by import, so no module above one names a PMS |
| `hotelcontrols/providers/*/paths.py` | structured addressing per wire format — the fix for the regex fragility in finding F4 |
| `hotelcontrols/evidence/reference.py` | the join stage that took three controls from 111/111 UNKNOWN to 97–98% |
| `hotelcontrols/evaluator/population.py` | aggregate assertions, and the two R7 guards |
| `hotelcontrols/runner/coverage.py` | finding F5 — a run that concluded nothing says so |
| `hotelcontrols/runner/scheduling.py` | finding F7 — when a control runs, and whether its evidence was current |
| `hotelcontrols/web/render.py` | criteria 2, 3 and 8 on screen. `WORDING` is the monochrome half of criterion 2 |
| `hotelcontrols/web/server.py` | the only file that knows a socket exists. Serial on purpose — see the comment |
| `hotelcontrols/providers/transport/http.py` | the two locks, and the only outbound client in the engine |
| `hotelcontrols/providers/minihotel/live.py` | the request forms, transcribed from the calls that produced the captures |
| `tools/probe.py` | `--plan` prints what would be asked and makes no calls. This is what D3 approves |
| `tests/contract/` | one suite over every registered provider. Adding a PMS means running it, not writing it |
| `tests/integration/test_compiler_roundtrip.py` | every shipped sentence recompiled, clause for clause, then run |
| `tools/transcode_demopms.py` | the demo fixtures are generated from the vendor captures, gaps included |
| `tools/scrub_fixtures.py` | must run before any capture is committed |
