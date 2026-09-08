# Session handoff

Paste the block below into a fresh session to resume. Everything it references is in the
repository; nothing depends on the previous conversation.

---

```
Continue building miniHotelPMS. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

Read these first, in order: CLAUDE.md, docs/plan.md, docs/prd.md, docs/architecture.md,
docs/open-questions.md, docs/old-codebase-improve.md. They are the specification and the
execution tracker; docs/plan.md is authoritative for what is done and what is next.

STATE: slices 0-6 of 12 are merged (PRs #1-#8 on github.com/sauravs/miniHotelPMS).
413 tests, 95% coverage, 590 spec checks, CI green on Python 3.11 and 3.13.
Next up is Slice 7 - the second provider, DemoPMS.

Keep working the same way:
  - TDD. Failing test first, written from the specification rather than from the code you
    intend to write. Every test names the IR clause, success criterion or risk id it protects.
  - One branch per slice (slice/NN-name) -> push -> PR -> CI must pass -> squash-merge.
    Bugs found outside the current slice get a GitHub issue first, then fix/NN-desc, then a
    PR closing it. Update the slice table in docs/plan.md as you go.
  - Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec
  - Zero runtime dependencies. pytest and coverage are dev-only and hotelcontrols/ may never
    import them. Coverage floor is 90%; raise it by adding real tests, never by lowering it.
  - High comment density, explaining WHY and citing the risk id (R1, R7, R9, R12, R13, A5).
  - Never widen a verdict. Missing evidence is UNKNOWN. This outranks every other instruction.
  - Never edit a fixture to make a test pass, and never invent one to reach a nicer outcome.
  - Do not call the MiniHotel sandbox without asking me first, each time (decision D3).

Work autonomously through the remaining slices, reporting after each merge. Ask me only when a
decision is genuinely mine to make.
```

---

## What a fresh session needs to know that the docs do not spell out

### Decisions already taken — do not re-litigate

Recorded as D1–D8 in `docs/open-questions.md` §0. In short: all 10 dry-run controls made
executable (11 IRs after splitting control 6); stdlib-only runtime with pytest as a dev
dependency; live sandbox calls allowed but approved individually; a fictional JSON `DemoPMS` as
the second provider; a deterministic grammar compiler with an LLM adapter behind the same
validation gate; public repo with pseudonymised fixtures; PR-per-slice with a CI gate; and
control 6 split into `checkout_money_owed` and `checkout_unrefunded_credit`.

### Success criterion 1 is recorded as NOT MET

5 of 11 controls reach a PASS or FAIL; the PRD asks for 8. **Do not relax the criterion.** The
six shortfalls are traced, one by one, in `docs/plan.md`, and none of them is a defect in the
engine. Three would move on a conversation rather than on code.

### Checkpoints that need the project owner

| Before | Decision |
| --- | --- |
| any live call | Approval for a specific, bounded, staged probe (D3). Three calls — `getRooms`, `getRoomTypes`, `RoomStatusInquiry` — would refresh the 2024-era findings the review flagged as stale (open question 1.2) |
| slice 9 | Whether the LLM adapter should be wired to a real model, and which |
| any time | **The cheapest open win:** which rate codes this property has nominated for control 15 (open question 1.4). One sentence takes `required_reservation_fields` from zero answers to real ones |
| any time | Ask MiniHotel what `OK4` and `WL` mean (question 2.1). They cover 44 of the 217 reservations ever seen, and they are why the known duplicate pair resolves to UNKNOWN rather than to an answer |

### Things that will look like bugs and are not

- `ooo_room_protection` excludes all 28 rooms, and `room_assignment_active_room` all 111 stays.
  No room in this property has ever had a closed-date window set (open question 2.4). The
  coverage verdict reports this rather than showing a reassuring zero.
- `room_capacity_compliance` answers for nobody: 23 of 28 rooms report adult capacity `0`,
  which means *unconfigured*, not zero (R12).
- `rate_room_category_consistency` is UNKNOWN everywhere. A reservation's rate code and the
  provider's price-list code are different key spaces (R13) — structurally unresolvable here.
- Neither aggregate control reaches FAIL. The property genuinely has no active duplicate and no
  double-booked room. **Do not manufacture one.**
- `miniHotelLegacy/` is git-ignored on purpose: it holds unscrubbed guest data and hard-coded
  sandbox credentials, and this repository is public.

### Where the interesting parts are

| | |
| --- | --- |
| `hotelcontrols/kernel/` | `Value`, `Money` (Decimal), `Outcome`, `Verdict`, `Clock`. Five guarantees enforced in constructors |
| `hotelcontrols/providers/minihotel/paths.py` | structured XML paths — the fix for the regex fragility in finding F4 |
| `hotelcontrols/evidence/reference.py` | the join stage that took three controls from 111/111 UNKNOWN to 97–98% |
| `hotelcontrols/evaluator/population.py` | aggregate assertions, and the two R7 guards |
| `hotelcontrols/runner/coverage.py` | finding F5 — a run that concluded nothing says so |
| `tools/scrub_fixtures.py` | must run before any capture is committed |
