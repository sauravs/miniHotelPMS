# Session handoff

Paste the block below into a fresh session to resume. Everything it references is in the
repository; nothing depends on the previous conversation.

**Last updated:** 2026-09-09, after slice 8 merged. **Next up: slice 9 — the English → IR compiler.**

---

```
Continue building miniHotelPMS. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

Read these first, in order: CLAUDE.md, docs/plan.md, docs/prd.md, docs/architecture.md,
docs/open-questions.md, docs/old-codebase-improve.md. They are the specification and the
execution tracker; docs/plan.md is authoritative for what is done and what is next.

STATE: slices 0-8 of 12 are merged (PRs #1-#8, #10, #11, #12 on github.com/sauravs/miniHotelPMS).
1086 tests, 95% coverage, 1003 spec checks, CI green on Python 3.11 and 3.13.
Two providers ship and agree on every verdict. The execution model is live.

NEXT UP IS SLICE 9 - the compiler, English -> Control IR. Its scope is settled; do not
re-open it:

  - GrammarCompiler: a restricted-English parser. Deterministic, offline, no model. This is
    what CI runs and what every test asserts against.
  - ModelCompiler: the SEAM only - one method, propose(sentence) -> dict - exercised against
    a STUB. Decision D9 in docs/open-questions.md: no real model is wired in this slice, and
    the reasoning is recorded there. Do not add an SDK, an API key, a network path or a
    `urllib` call to hotelcontrols/.
  - Both front ends go through the IDENTICAL validation gate. A model's proposal is rejected
    exactly as a human's is, by the same code path, with the missing vocabulary NAMED.
  - The compiler emits IR only, never executable anything. Section 17 of the requirements doc
    is explicit about why, and that rule outranks any convenience.

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

### Slice 9, in one paragraph

`hotelcontrols/compiler/` — `grammar.py`, `model.py`, `problems.py`. A sentence compiles to an
IR; the IR is validated by the code that already exists (`spec/ir.py`, unchanged); a sentence
naming vocabulary nobody declared is rejected **naming the missing fields**. The gate that makes
this safe already works and is already tested: fed the requirements doc's own example — *"All VIP
arrivals should have an assigned room that is clean by 2 PM"* — the validator answers with
`reservation.vip` and `room.housekeeping_status_at`, the two canonical fields that do not exist.
Slice 9 puts a front end on that, and the front end may not weaken it.

**The measurable claim** is criterion 9 plus the second half of criterion 6: at least 6 of the 11
shipped controls round-trip from their own `natural_language` field through the compiler and back
to the same verdicts, and a *new* sentence compiles and runs with no code change.

**If the stub work goes quickly**, the honest extra is a measurement rather than a feature: how
many of the eleven `natural_language` sentences the grammar can actually parse, recorded as a
number in `docs/plan.md` the way criterion 1's 5-of-11 is. Do not tune the sentences to raise it.

### Success criterion 1 is recorded as NOT MET

5 of 11 controls reach a PASS or FAIL; the PRD asks for 8. **Do not relax the criterion.** The six
shortfalls are traced one by one in `docs/plan.md`, and none is a defect in the engine. Three
would move on a conversation rather than on code.

It was 6 until issue #9 was fixed: `resource_occupancy_consistency` had been reaching two PASSes
about July 2026 from occupancy segments captured in August 2024, because the frozen source's
window guard checked three filter names instead of every window. **That is the shape of defect
this project exists to catch, and the number went down rather than the guard going away.**

### Checkpoints that need the project owner

| Before | Decision |
| --- | --- |
| any live call | Approval for a specific, bounded, staged probe (D3). Three calls — `getRooms`, `getRoomTypes`, `RoomStatusInquiry` — would refresh the 2024-era findings the review flagged as stale (open question 1.2) |
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
- Every run over the 2026 captures reports its evidence as *captured after the instant asked
  about*. That is true — the bytes were fetched in September for a question about July — and it
  is neither stale nor fresh.
- `miniHotelLegacy/` is git-ignored on purpose: it holds unscrubbed guest data and hard-coded
  sandbox credentials, and this repository is public.

### Where the interesting parts are

| | |
| --- | --- |
| `hotelcontrols/kernel/` | `Value`, `Money` (Decimal), `Outcome`, `Verdict`, `Clock`. Five guarantees enforced in constructors |
| `hotelcontrols/spec/ir.py` | **The validation gate slice 9 puts a front end on.** Six checks beyond the schema; read this before writing a line of the compiler |
| `hotelcontrols/providers/registry.py` | adapters discovered by import, so no module above one names a PMS |
| `hotelcontrols/providers/*/paths.py` | structured addressing per wire format — the fix for the regex fragility in finding F4 |
| `hotelcontrols/evidence/reference.py` | the join stage that took three controls from 111/111 UNKNOWN to 97–98% |
| `hotelcontrols/evaluator/population.py` | aggregate assertions, and the two R7 guards |
| `hotelcontrols/runner/coverage.py` | finding F5 — a run that concluded nothing says so |
| `hotelcontrols/runner/scheduling.py` | finding F7 — when a control runs, and whether its evidence was current |
| `tests/contract/` | one suite over every registered provider. Adding a PMS means running it, not writing it |
| `tools/transcode_demopms.py` | the demo fixtures are generated from the vendor captures, gaps included |
| `tools/scrub_fixtures.py` | must run before any capture is committed |
