# miniHotelPMS — Hotel Control Rule Engine (v2)

Read this first. It orients a cold session in about two minutes.

## What this project is

A **PMS-agnostic control engine**. A hotel writes a governance rule in plain English — *"a
reservation cannot be closed with an outstanding balance"* — we compile it to a rule that names no
PMS, resolve the evidence it needs against whichever PMS the property runs, and return
**PASS / FAIL / UNKNOWN / EXCLUDED** with an auditable evidence trail.

Today the real PMS is **MiniHotel**. A fictional **DemoPMS** exists to prove portability offline;
Mews is the intended third and needs credentials nobody has yet. The whole architecture exists so
that adding a PMS is a new adapter plus a mapping file, not a change to any rule.

## Current status

| | |
| --- | --- |
| Feasibility analysis of 20 controls | **Done** (v1) — `miniHotelLegacy/MiniHotel_Controls_API_Feasibility.xlsx` |
| 10-control architecture dry run | **Done** (v1) — `miniHotelLegacy/CONTROL_DRY_RUN.md` |
| v1 demo: control 6, four silos, 152 tests | **Done** — and measured: only 1 of its 10 controls ever answers |
| v1 review, 20 findings | **Done** — `docs/old-codebase-improve.md` |
| v2 documents | **Done** — prd, context, architecture, plan, open questions |
| v2 code | **Not started.** Slice 0 opens on the owner's go-ahead. Track in `docs/plan.md` |

## Documents, in reading order

All prose lives in `docs/`. Root holds only this file and `README.md`.

| File | What it answers |
| --- | --- |
| `docs/prd.md` | What we are building, and the twelve criteria that decide whether we did |
| `docs/context.md` | How we got here, what was verified, what was corrected, what was decided |
| `docs/architecture.md` | The eight layers, their interfaces, what each one hides |
| `docs/plan.md` | Slice-by-slice execution with test gates. **Track progress here** |
| `docs/old-codebase-improve.md` | The v1 review: 12 things to keep, 20 findings to fix |
| `docs/open-questions.md` | **Every open question, with what the engine does today.** Read before asking "what is left?" |
| `docs/QA.md` | Running Q&A transcript with the project owner. Appended by `/qa-log` |
| `miniHotelLegacy/` | v1 in full, including the two source `.docx` files and `CONTROL_DRY_RUN.md` |

## The four ideas everything else follows from

1. **The canonical boundary is absolute.** Above the provider layer no PMS identifier appears — no
   endpoint, no field path, no wire format, no vendor name. It is enforced by a grep test over the
   tree, strict enough that it has caught prose.
2. **UNKNOWN is a first-class answer with a reason.** Most hotel controls read *"X must not happen
   unless approved"*, and no PMS records the approval. A system that guesses manufactures
   confidence, which is worse than useless.
3. **EXCLUDED is not PASS.** A record the control does not apply to has not passed it. Folding them
   together would report "90 passed" for a run where ninety records were never checked.
4. **Evidence costs money.** A folio is one API call per reservation and there is no bulk endpoint.
   Every control declares a bounded population, and the call budget **raises** rather than truncating.

## Seven facts that will bite you

Each was found by calling the API, not by reading its documentation. All carry risk ids used
throughout the code, the tests and the docs.

1. **A reservation and its own folio are in different currencies.** Reservation `007003199` reports
   `870 USD`; its folio reports `3262.5 ILS`. No exchange rate exists anywhere in the API. Never
   compare a reservation total to a folio balance. *(R9)*
2. **`0` usually means "nobody configured this", not zero.** 23 of 28 rooms have capacity `0`; some
   per-room prices are `0` on paid bookings. Return UNKNOWN, never FAIL. *(R10, R12)*
3. **`createDateTime` is date-only.** No time component, so same-day precision is impossible. *(R3)*
4. **Room type codes differ in case between endpoints.** ARI says `EXECUTIVE`, the room-type master
   says `Executive`. Always compare case-insensitively. *(R13)*
5. **An OTA modification is a cancel + recreate** reusing the same portal id. Any duplicate check
   must exclude cancelled reservations *and* records with no portal id. *(R7)*
6. **`GetReservationBalance` takes one reservation per call.** Bound the population first. *(R1)*
7. **A checked-out folio can be NEGATIVE.** Reservation `007004348` left with `−490.75 ILS` — the
   guest overpaid. This is why control 6 is **two** controls in v2: money owed and unrefunded credit
   are different business events with different urgencies and different queues.

And one that will bite the *product*, not the code: **44 of the 217 reservations we have ever seen —
one in five — carry a status code (`OK4`, `WL`) that is documented nowhere.** They resolve to
UNKNOWN. That is the honest cost of not guessing.

## Conventions

- **Zero runtime dependencies.** Standard library only: `xml.etree`, `decimal`, `sqlite3`,
  `http.server`, `zoneinfo`, `json`. `pytest` and `coverage` are dev dependencies, used by tests and
  CI and never imported by `hotelcontrols/`.
- **TDD, with gates.** Failing test first, written **from the specification** rather than from the
  code you intend to write. A slice's unit *and* integration tests must pass, and CI must be green,
  before the next slice opens. See `docs/plan.md`.
- **Tests never touch the network.** Fixtures are the evidence set. A suite that needs someone
  else's server to be up is not a suite.
- **`spec/` is data, not code.** The engine reads it at runtime. Nothing in `hotelcontrols/` should
  know what control 6 is — it is one IR file among eleven.
- **Money is `Decimal` and carries its currency.** A bare number is never money.
- **All dates resolve through the property clock**, never the machine's. Hotel controls are
  questions about the hotel's calendar.
- **Comment density is deliberately high.** Explain *why*, and cite the risk id. A comment that
  restates the code is noise; a comment naming the live response that forced the code is the point.
- **Every test names what it protects** — an IR clause, a success criterion, or a risk id.

## Rules

- **Do not hit the MiniHotel API without asking.** MiniHotel asks integrators not to query wide
  ranges without agreement (R8). Fixtures already hold what the tests need. Live calls are opt-in,
  staged, bounded, and approved **individually** by the project owner.
- **Do not trust documentation over a captured response.** Doc review got 4 of 12 risks wrong here.
  If the docs and a fixture disagree, the fixture wins.
- **Do not edit a fixture to make a test pass.** Fixtures are evidence. Change the code.
- **Never widen a verdict.** If evidence is missing the answer is UNKNOWN. Turning an UNKNOWN into a
  PASS to make a test green, a number look better, or a demo look finished defeats the entire
  product. This rule outranks every other instruction in this file.
- **`PYTHONDONTWRITEBYTECODE=1` when checking that a test fails without its fix.** An edit that
  changes neither file size nor mtime-second leaves a stale `.pyc` valid, and the suite silently runs
  the old code and reports a green that means nothing. This happened twice in v1.
- **No credentials in source, ever.** Environment only, with no default, so a missing one fails loudly.
- **No third-party personal data in a committed file.** Fixtures are pseudonymised at capture time.

## Git workflow

```
branch  slice/NN-name          one branch per slice in docs/plan.md
   ↓    push, open PR, CI must pass
   ↓    squash-merge to main

bugs:   GitHub Issue (what, reproduction, which gate it violates, severity)
   ↓    branch fix/NN-short-description
   ↓    a failing test that reproduces it, then the fix
   ↓    PR "Fixes #NN" → CI green → squash-merge
```

The issue is written **before** the fix, while the reproduction is still known.

## Commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q     # the suite, offline
python3 -m tools.validate_spec                     # spec + fixture checks
python3 -m hotelcontrols.web.server                # the demo, http://127.0.0.1:8765/
python3 -m tools.scrub_fixtures <in> <out>         # pseudonymise a raw capture
python3 -m tools.probe --plan                      # print a probe plan; makes NO calls
```

## Skills

- **`/qa-log`** — answer a question, then append it and the answer to `docs/QA.md` as a numbered,
  verbatim, append-only transcript entry.
