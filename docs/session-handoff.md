# Session handoff

Paste the block below into a fresh session to resume. Everything it references is in the
repository; nothing depends on the previous conversation.

**Last updated:** 2026-09-09, after slice 10 merged. **Next up: slice 11 — the opt-in transport and the probe tooling. That is the last slice.**

---

```
Continue building miniHotelPMS. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

Read these first, in order: CLAUDE.md, docs/plan.md, docs/prd.md, docs/architecture.md,
docs/open-questions.md, docs/old-codebase-improve.md. They are the specification and the
execution tracker; docs/plan.md is authoritative for what is done and what is next.

STATE: slices 0-10 of 12 are merged (PRs #1-#8, #10-#14 on github.com/sauravs/miniHotelPMS).
1391 tests, 95% coverage, 1080 spec checks, CI green on Python 3.11 and 3.13.
Two providers ship and agree on every verdict. The execution model is live. A sentence
compiles to a rule, and all 11 shipped controls recompile from their own restricted-English
sentence to the same rule and the same verdicts. The demo serves offline at
`python3 -m hotelcontrols.web.server`; nine of the twelve success criteria are met.

NEXT UP IS SLICE 11 - the opt-in transport and the probe tooling. Its scope is settled;
do not re-open it:

  - hotelcontrols/providers/transport/ - http.py, ratelimit.py, record.py. OFF unless an
    environment variable is set, and NO TEST MAY BE ABLE TO SET IT. With the variable
    unset, every path that would open a socket raises instead.
  - Token-bucket rate limiter with an INJECTED clock (F11 applies here too). Bounded retry
    with backoff; a give-up is UNKNOWN with a reason, never a crash.
  - The per-run call ceiling reuses the existing CallBudget (R1, R8). Do not add a second
    budget.
  - Credentials from the environment with NO DEFAULT, so a missing one fails loudly (F15).
  - Record mode writes a response AND its request fingerprint into the fixture set, in the
    shape fixtures/*/index.json already uses.
  - tools/probe.py is staged and bounded and PRINTS ITS PLAN BEFORE MAKING ANY CALL.
    `python3 -m tools.probe --plan` makes none at all.
  - tests/unit/test_stdlib_only.py forbids urllib.request/http.client/socket/ssl across the
    engine and exempts web/server.py by path. The transport needs the same explicit
    exemption, by path, and nothing broader.

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

### What slices 9 and 10 built, in two paragraphs

**Slice 9, the compiler.** `hotelcontrols/compiler/` — `grammar.py`, `model.py`, `problems.py`.
A restricted-English sentence compiles to an IR; the IR goes through `spec.validate`, unchanged
and unbypassed. The model seam is one method — `propose(sentence) -> dict` — and its refusals
are compared against `spec.validate` called directly on the same document, message for message.
Two things about it are easy to misread as gaps and are not. Each control carries **two**
sentences: `natural_language` is prose a person wrote, `restricted_language` is the controlled
form — **the grammar parses 0 of the 11 prose sentences and 11 of 11 restricted forms**, and a
test fails if the first number rises. And a sentence cannot supply a `population.provider_query`
without naming a PMS (criterion 5), so the document is split: sentence owns the rule, a
*deployment* dict owns the bounded query, trigger, freshness and action. Enforced both ways.

**Slice 10, the demo.** `hotelcontrols/web/` — `app.py` routes, `render.py` renders, `server.py`
is the only file that knows a socket exists. `handle(path) -> (status, content_type, body)` is a
pure function of the path, so the whole demo is asserted as strings. UNKNOWN is told apart from
FAIL by **wording** (VIOLATION / NO ANSWER, asserted with every tag stripped), border style and
hue. A run that concluded nothing, and a run that was blocked, show **no count tiles** — that is
finding F5 on screen. `as_of` defaults to the instant the capture declares it describes, because
asking today's date would produce a page of refusals about nothing.

### Success criterion 1 is still recorded as NOT MET

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
- The grammar refuses *"every reservation arriving within 24 hours must …"* — the shape the
  requirements doc uses. That is deliberate and is explained in the refusal itself: a window on
  arrival bounds the population, which is per-provider deployment data.
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
| `tests/contract/` | one suite over every registered provider. Adding a PMS means running it, not writing it |
| `tests/integration/test_compiler_roundtrip.py` | every shipped sentence recompiled, clause for clause, then run |
| `tools/transcode_demopms.py` | the demo fixtures are generated from the vendor captures, gaps included |
| `tools/scrub_fixtures.py` | must run before any capture is committed |
