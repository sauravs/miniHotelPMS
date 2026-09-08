# Plan — v2 build

Execution tracker. **Update the status table as slices close.** Design rationale lives in
`architecture.md`; do not duplicate it here.

---

## Status

| # | Slice | Unit | Integ | E2E | CI | PR | State |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Foundation, kernel & CI | ☑ | — | — | ☑ | ☑ | **done** — PR #1 |
| 1 | Spec layer & validator | ☑ | ☑ | — | ☑ | ☑ | **done** — PR #2 |
| 2 | MiniHotel provider (structured) | ☑ | ☑ | — | ☑ | ☑ | **done** — PR #4 |
| 3 | Evidence, references & budget | ☑ | ☑ | — | ☑ | ☑ | **done** — PR #5 |
| 4 | Evaluator — record level | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #6 |
| 5 | Evaluator — population level | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #7 |
| 6 | Runner, coverage, readiness, store | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #8 |
| 7 | Second provider — DemoPMS | ☐ | ☐ | ☐ | ☐ | ☐ | not started |
| 8 | Scheduling & freshness | ☐ | ☐ | — | ☐ | ☐ | not started |
| 9 | Compiler — English → IR | ☐ | ☐ | ☐ | ☐ | ☐ | not started |
| 10 | Web UI & JSON API | ☐ | ☐ | ☐ | ☐ | ☐ | not started |
| 11 | Transport (opt-in) & probe tooling | ☐ | ☐ | — | ☐ | ☐ | not started |

---

## Method

**Red → green → gate → PR → merge.**

1. Write the failing test first, **from the specification** rather than from the code you intend to
   write. Every test names the IR clause, success criterion, or risk id it protects.
2. Write the smallest implementation that passes.
3. A slice is not finished until its unit *and* integration tests are green, CI is green, and its
   gate conditions below are met. **The next slice does not open until it is.**
4. Branch `slice/NN-name` → push → open PR → CI must pass → **squash-merge** to `main`.

Commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q          # the suite, offline
python3 -m tools.validate_spec                          # spec + fixture checks
python3 -m hotelcontrols.web.server                     # the demo, http://127.0.0.1:8765/
```

### Non-negotiable rules while building

1. **Do not turn UNKNOWN into PASS to make a test green.** If a test is hard to satisfy because
   evidence is missing, the test is right and the implementation is wrong.
2. **Do not edit a fixture to match the code.** Fixtures are captured evidence. If the code and a
   fixture disagree, the fixture wins.
3. **Do not add provider calls to make a test pass.** Fixtures have what is needed.
4. **Do not compare two money amounts in different currencies** (R9). Compare against literal zero,
   or return UNKNOWN.
5. **Do not treat `0` as a number** for capacity or per-room price (R10, R12).
6. `PYTHONDONTWRITEBYTECODE=1` when checking that a test really fails without its fix. An edit that
   changes neither file size nor mtime-second leaves a stale `.pyc` valid, and the suite silently
   runs the OLD code and reports a green that means nothing. This happened in v1, twice.

### Bug workflow

A defect found mid-slice that is **inside** the current slice is just red-then-green — no ceremony.

A defect found **outside** the current slice, or after a slice has merged:

```
GitHub Issue  (what, reproduction, which slice/gate it violates, severity)
      ↓
branch fix/NN-short-description
      ↓
failing test that reproduces it, then the fix
      ↓
PR "Fixes #NN"  → CI green → squash-merge
```

The issue is written **before** the fix, so the reproduction is recorded while it is still known.

---

## Slice 0 · Foundation, kernel & CI

`hotelcontrols/kernel/` · repo scaffolding · GitHub Actions

The vocabulary every later layer speaks, plus a mechanical gate from the very first commit.

**Scaffolding**
- [x] `git init`, remote `sauravs/miniHotelPMS`, `.gitignore` (raw captures, `runs/`, `__pycache__`, `.env`)
- [x] `README.md`, `CLAUDE.md`, all prose already in `docs/`
- [x] `requirements-dev.txt` — `pytest`, `coverage`. **Runtime dependencies: none, ever**
- [x] GitHub Actions: `PYTHONDONTWRITEBYTECODE=1`, full suite, spec validator, coverage floor
- [x] Branch protection on `main` requiring the workflow

**Unit tests**
- [x] A number without a unit **cannot be constructed** (R9)
- [x] Money is `Decimal`, parsed from the raw string — `float` never appears in the path (F10)
- [x] Two amounts in different currencies **raise** on comparison (R9)
- [x] Comparison against literal `0` is allowed across currencies, and only zero is
- [x] An unknown Value **raises** on comparison rather than returning `False`
- [x] An unknown without a reason cannot be constructed
- [x] `NOT_APPLICABLE` is distinct from absent, from empty string, and from `False` (R7)
- [x] A `Verdict` cannot be constructed without a reason or without evidence
- [x] `Clock` is a protocol; a fixed test clock and a property timezone both satisfy it (F11)

**Gate**
- [x] CI green on `main` — 101 tests, 99% coverage, Python 3.11 and 3.13
- [x] No runtime import outside the standard library — asserted by a test that walks the tree
- [x] Every kernel type is a frozen dataclass; mutation raises

---

## Slice 1 · Spec layer & validator

`hotelcontrols/spec/` · `spec/*.json` · `tools/validate_spec.py`

Migrate v1's 52-field registry and 10 IRs, **split control 6 into two**, and make tenant
configuration data instead of module constants (F12, resolves v1 open question 1.4).

**Unit tests**
- [x] An IR referencing a canonical field nobody declared is **rejected**, naming the field
- [x] A field used in scope/exceptions/assertion but not declared in `required_evidence` is rejected
- [x] An IR naming an unknown operator or assertion mode is rejected
- [x] A tenant config with an unmapped-by-design status code loads; the code resolves UNKNOWN (A5)
- [x] A tenant timezone that is not an IANA zone is rejected
- [x] The doc's own example — *"All VIP arrivals should have an assigned room that is clean by 2 PM"* —
      is rejected naming `reservation.vip` and `room.housekeeping_status_at` (§17 gate)

**Integration tests**
- [x] All 11 IRs are schema-valid and reference only declared vocabulary
- [x] Every canonical field is either mapped by at least one provider or explicitly marked
      unresolvable with a reason (`rate_plan.permitted_room_types`, R13)

**Gate**
- [x] `validate_spec` passes and reports its check count — **592 checks**
- [x] 11 IRs load; the two control-6 halves assert `lte 0` and `gte 0` respectively
- [x] No status map, department map or timezone remains in Python source

---

## Slice 2 · MiniHotel provider, structured

`hotelcontrols/providers/minihotel/` · `tools/scrub_fixtures.py`

The largest slice. Every quirk lives here and nothing above may know the PMS exists.
**This slice fixes F4, the silent-fragility finding.**

**Fixture preparation (first, before any resolver work)**
- [x] `scrub_fixtures.py` — deterministic pseudonymisation of names, emails, phones, ID numbers and
      free-text remarks. Stable mapping, so fixtures stay byte-identical between runs (F15)
- [x] Raw captures moved out of the repository and git-ignored; scrubbed fixtures committed
- [x] Each fixture carries a **request fingerprint** recording what was actually asked (F19c)

**Unit tests**
- [x] Each date transform, including one that **rejects** an unparseable value rather than guessing (R2, R3)
- [x] `createDateTime` resolves with date granularity and no caller can believe otherwise (R3)
- [x] `zero_is_unknown` returns unknown for `0`, known for `1` (R10, R12)
- [x] `casefold` makes `EXECUTIVE` and `Executive` compare equal (R13)
- [x] Tenant status map turns `OUT` into `checked_out`; `OK4` and `WL` resolve UNKNOWN (A5)
- [x] An absent field returns the registry's `absent_means` — unknown, false, or not_applicable — **never `None`**
- [x] A present-but-empty field is treated as absent
- [x] **Attribute order does not change any resolved value** — the exact v1 failure, as a regression test (F4)
- [x] **XML entities are decoded**: `O&apos;Brien` resolves as `O'Brien` (F4)
- [x] A money field with no establishable currency resolves UNKNOWN, not a bare number (R9)

**Integration tests**
- [x] All 52 mappings resolve against their fixture — the check `validate_spec` performs, enforced here too
- [x] `folio.balance_due` on `007003199` returns `Decimal('3262.5') ILS`, and `reservation.currency`
      on the same reservation returns `USD` — the currency split visible in one test (R9)
- [x] `folio.balance_due` on `007004348` returns `Decimal('-490.75') ILS` — the overpayment
- [x] `room.max_guests.adults` is unknown for 23 of 28 rooms — 21 configured `0`, 2 absent (R12)
- [x] A record reads a field from the record **containing** it, and **never from a sibling** (R7)
- [x] Live and frozen paths return identical `Value`s for the same record, with a fake transport

**Gate**
- [x] All 52 mappings resolve
- [x] No caller can obtain a number without its unit
- [x] Grep test: no PMS identifier outside `providers/minihotel/`
- [x] No guest name, email or phone from the vendor sandbox remains in a committed file

---

## Slice 3 · Evidence, references & budget

`hotelcontrols/evidence/` — **this slice fixes F1, the largest functional gap in v1**

**Unit tests**
- [x] A control's population query produces the documented request filters, with `today-1d`
      resolved through the **tenant clock**, not the machine's (F11)
- [x] An unrecognised relative-date token **raises** rather than being passed through
- [x] Exceeding the call budget **raises**; nothing further is fetched (R1, R8)
- [x] A failed follow-up yields a bundle marked unknown, not a dropped record
- [x] A reference key with no match resolves UNKNOWN — **a join never invents a match**
- [x] The run-scoped cache fetches one response once, however many records need it (F19b)

**Integration tests**
- [x] Against fixtures, the population is exactly the hand-computed expected set for its window
- [x] **Call count is `1 + R + N`**, asserted by counting invocations — the regression guard on R1
- [x] The room master is fetched **once** and joined to 111 stays: `room.type` and
      `room.max_guests.adults` resolve for records that previously returned 111 UNKNOWN (F1)
- [x] One unreachable follow-up degrades a single bundle, never the run

**Gate**
- [x] Population matches a hand-computed set
- [x] Call count asserted, not assumed
- [x] Grep test: no provider name, endpoint or field path anywhere in `evidence/`, prose included

---

## Slice 4 · Evaluator, record level

`hotelcontrols/evaluator/` (record path) — pure. No I/O, no clock, no network.

**Unit tests**
- [x] Balance of zero → PASS; positive balance → FAIL (control 6a)
- [x] **An unknown balance → UNKNOWN, never FAIL.** The rule that keeps the system honest
- [x] A record outside scope is **EXCLUDED**, not passed
- [x] An exception makes a record EXCLUDED, and is evaluated after scope
- [x] Unknown precedence, both directions: a definite FAIL under `all` outranks an unrelated
      unknown; a would-be PASS **never** outranks a missing field
- [x] `within` / `not_within` / `overlaps` on date intervals, including an open-ended window (F2)
- [x] Comparing `folio.balance_due` to `reservation.total_amount` is **refused**, with the reason (R9)
- [x] Every verdict carries a non-empty evidence table

**Integration + E2E**
- [x] Control 6a and 6b against real bundles from fixtures: the settled folio, the overpaid folio,
      and one whose folio was never captured — PASS, FAIL and UNKNOWN from **captured** evidence
- [x] Room type validity and inactive-room checks reach real verdicts using slice 3's reference
      join — 27 PASS each, where v1 returned 111 UNKNOWN out of 111. Capacity and OOO reach only
      EXCLUDED/UNKNOWN, correctly: 23 of 28 rooms report capacity `0` (R12) and no room has ever
      had a closed-date window set (open question 2.4). Slice 6's coverage verdict surfaces that

**Gate**
- [x] All four outcomes reachable from captured evidence
- [x] No path produces a verdict without evidence — structurally refused
- [x] **No I/O in this layer** — asserted by test (patched `open`/`socket` raise), not assumed

---

## Slice 5 · Evaluator, population level

`hotelcontrols/evaluator/population.py` — **fixes F2**

**Unit tests**
- [x] `count_lte` over a group: two records sharing a key violate `count_lte 1`
- [x] Cancelled records are excluded from the group before counting (R7)
- [x] A `NOT_APPLICABLE` key is excluded from grouping — **every direct booking must not look like a
      duplicate of every other** (R7)
- [x] A record whose key is UNKNOWN yields UNKNOWN, and does not corrupt other records' verdicts
- [x] `aggregate` mode attributes the group's evidence to each contributing record

**Integration + E2E**
- [x] `duplicate_channel_reservation` reaches the **known real pair** — portal id `test0000000N1`,
      shared by `007003206` (cancelled) and `007003207` (`OK4`). The engine's call: **EXCLUDED** for
      the cancelled half (R7's cancel-and-recreate) and **UNKNOWN** for the other, because `OK4` is
      documented nowhere so nobody can say whether it is active. It refuses to guess in either
      direction — see open questions 1.3 and 2.1
- [x] `resource_occupancy_consistency` reaches verdicts — 2 PASS, asked over the window its
      evidence actually covers. No projection was needed; see issue #3. **Corrected after the
      fact:** it was reaching those two PASSes at *any* as-of date, because the capture's
      occupancy window was replayed unchecked (issue #9). It concludes on 14 August 2024 and is
      blocked on both standard evidence sets, which is why criterion 1 measures 5 and not 6

**Gate**
- [x] Both population-level controls reach real conclusions on captured evidence: PASS for both,
      each asked over a window its evidence covers.
      **Neither reaches FAIL, and none was manufactured** — this property has no active duplicate
      and no double-booked room. v1 invented fixtures to reach a nicer demo; this repository does
      not
- [x] A group verdict names every record in its group in the evidence table

---

## Slice 6 · Runner, coverage, readiness & store

`hotelcontrols/runner/` · `hotelcontrols/store/` — **fixes F5, F8, F14**

**Unit tests**
- [x] A run aggregates verdicts into counts, with `EXCLUDED` counted separately
- [x] **Coverage:** a run where `PASS + FAIL == 0` is flagged as having concluded nothing, and
      carries the dominant reason (F5) — with UNKNOWN reasons outranking exclusions, and the full
      distribution reported, because the commonest reason is usually the least informative
- [x] A blocked run shows **no count tiles** — four zeroes must not read as a clean bill of health
- [x] `readiness(control, provider)` reports resolvable / total fields, grouped by evidence source (F8)
- [x] A stored run round-trips without losing value, unit, reason, risk id, provenance, or the
      `not_applicable` sentinel
- [x] Loading a control id from an untrusted string cannot escape the spec directory

**Integration + E2E**
- [x] All 11 controls × all evidence sets execute or report a named blocker — asserted.
      **5 of 11 reach PASS or FAIL, not the 8 criterion 1 asks for. Recorded as unmet below.**
      (Measured 6 when this slice merged; issue #9 removed one that was concluding from a window
      nobody had asked about.)
- [x] Run history: three runs of one control are listed newest-first and re-read with **zero**
      provider calls (R1)
- [x] The 100%-excluded case renders as "reached no conclusion", asserted on the coverage headline

**Gate**
- [x] Criterion 1 **assessed** by test and recorded as **not met** — 5 of 11, with each of the
      six shortfalls traced to a fact about the property or the provider rather than the engine
- [x] SQLite schema migrates from empty on first run; no manual setup step

---

## Slice 7 · Second provider — DemoPMS

`hotelcontrols/providers/demopms/` · `tests/contract/` — **fixes F9. This is the thesis.**

DemoPMS is fictional and speaks **JSON**, with quirks deliberately different from MiniHotel's: a
different date format, a different way of signalling "unconfigured", nested rather than sibling
occupancy, and a status vocabulary of its own.

**Unit tests**
- [ ] DemoPMS transforms, mirroring slice 2's suite against a different wire format

**Contract tests — one suite, run against every registered provider**
- [ ] Every provider implements the full `Provider` protocol
- [ ] A missing field returns the registry's `absent_means`, identically, on both
- [ ] Money always carries a currency, on both
- [ ] An unmapped status resolves UNKNOWN, on both
- [ ] A record never reads a sibling's field, on both

**E2E**
- [ ] **The same IR, over the same logical hotel, through two providers, yields the same verdicts**
      (criterion 7). The fixtures encode the same hotel twice, in two wire formats

**Gate**
- [ ] Criterion 7 asserted
- [ ] Adding DemoPMS required **zero changes** above the provider layer — verified by reviewing the
      diff, and recorded in the PR description

---

## Slice 8 · Scheduling & freshness

`hotelcontrols/runner/scheduling.py` — **fixes F7**

**Unit tests**
- [ ] Each execution mode — `event`, `scheduled`, `periodic`, `daily` — yields the documented plan
- [ ] An event-mode control on a provider **without** that webhook falls back to its declared
      periodic interval, and says that is why
- [ ] `before_event(arrival, 24h)` resolves through the **property clock**, not UTC (F11)
- [ ] Evidence older than `freshness_requirement.maximum_age` is marked stale on the run
- [ ] The function is pure: same inputs, same output, no wall clock read

**Integration**
- [ ] All 11 IRs produce a valid execution plan; none raises

**Gate**
- [ ] Clock injected everywhere; no `datetime.now()` outside the clock module
- [ ] A stale run says so on screen

---

## Slice 9 · Compiler — English → IR

`hotelcontrols/compiler/` — **fixes F6**

**Unit tests**
- [ ] The grammar parses the shapes the requirements doc uses: *"every X arriving within N hours
      must …"*, *"no X may …"*, *"X must not … unless …"*
- [ ] A sentence naming vocabulary that does not exist is **rejected, naming the missing fields** —
      not compiled into a rule that quietly answers about nothing (§17)
- [ ] An ambiguous sentence returns ambiguities rather than a confident guess
- [ ] The `ModelCompiler` adapter is exercised with a **stubbed** model; its output goes through the
      same validation, and a malformed proposal is rejected exactly as a human's would be
- [ ] No test path can reach a real model or the network

**Integration + E2E**
- [ ] At least 6 of the 11 shipped controls round-trip: `natural_language` → compiled IR → validates
      → produces the same verdicts as the hand-written IR
- [ ] Compiling and immediately running a **new** sentence produces a run with no code change
      (criterion 6, from the other end)

**Gate**
- [ ] Criterion 9 asserted
- [ ] The compiler emits IR only — never executable anything

---

## Slice 10 · Web UI & JSON API

`hotelcontrols/web/` — thin on purpose. Its job is to prove a verdict is explainable.

**Unit tests**
- [ ] `handle(path)` is a pure function of the path — routing testable without a socket
- [ ] Well-formed JSON for an empty population, a blocked run, and a run that concluded nothing
- [ ] An unexpected error renders as a page, never a dropped connection
- [ ] HTML escaping on every value that came from a provider

**Integration + E2E**
- [ ] Every control × every evidence set renders — the full matrix, asserted
- [ ] **UNKNOWN is distinguishable from FAIL by hue, border and wording** — asserted on text alone,
      so the distinction survives a monochrome screen (criterion 2)
- [ ] Every verdict block lists each field, its value with unit, and the call it came from (criterion 3)
- [ ] Readiness appears on the index; history appears per control

**Gate**
- [ ] Criteria 2, 3, 8 and 10 asserted
- [ ] The demo runs offline with no dependencies

---

## Slice 11 · Transport (opt-in) & probe tooling

`hotelcontrols/providers/transport/` · `tools/probe.py` — **fixes F13**

**Unit tests**
- [ ] The transport is **disabled unless an environment variable is set**, and a test cannot set it
- [ ] Token-bucket rate limiter honours its interval, with an injected clock
- [ ] Retry backs off and gives up; a give-up is UNKNOWN with a reason, never a crash
- [ ] The per-run call ceiling reuses the existing budget (R1, R8)
- [ ] **Record mode** writes a response plus its request fingerprint into the fixture set
- [ ] Credentials come from the environment with **no default**; a missing credential fails loudly (F15)

**Integration**
- [ ] A recorded response replays through the frozen path and yields identical `Value`s
- [ ] With the environment unset, every code path that would open a socket raises instead

**Gate**
- [ ] Criterion 11 asserted: no test can reach the network
- [ ] `probe.py` is staged and bounded, and prints its plan before making any call

---

## Definition of done

The twelve success criteria in `prd.md`, assessed honestly against tests — not against intent.

Where a criterion is not met, it is recorded here as **not met**, with what is missing. That is what
v1 did while control 6 could reach neither PASS nor FAIL, and it is why the eventual "met" was worth
something.

| # | Criterion | State |
| --- | --- | --- |
| 1 | ≥8 of 11 controls reach PASS or FAIL; the rest name their blocker | **NOT MET — 5 of 11.** The second half IS met: every non-concluding control names its blocker. See the assessment below |
| 2 | All four outcomes from captured evidence; UNKNOWN distinct from FAIL | pending |
| 3 | Every verdict traces to its fields | **Met** — structurally; a `Verdict` cannot be built without evidence |
| 4 | Call count is `1 + R + N`, asserted | **Met** — counted invocations, slice 3 and again end to end |
| 5 | No PMS identifier above the provider layer | **Met** — 20 identifiers grepped over the tree |
| 6 | A twelfth control is a spec change | pending |
| 7 | Same IR, two providers, same verdicts | pending |
| 8 | A run that concluded nothing says so | **Met** — slice 6's coverage verdict |
| 9 | English compiles to IR; unsupported sentences rejected by name | pending |
| 10 | Readiness reported per control per provider | **Met** in the API surface; the page lands in slice 10 |
| 11 | Offline, stdlib-only runtime, no test reaches the network | pending |
| 12 | Every slice green in CI before the next opens | pending |

## Checkpoints needing the project owner

Recorded here so they are not discovered late.

| Before slice | Decision needed |
| --- | --- |
| 3 | **Approval for 3 read-only calls** (`getRooms`, `getRoomTypes`, `RoomStatusInquiry`) to confirm whether the 2024-era room findings still hold. The sandbox is known to have moved on; three controls rest on findings that are now *unverified since the system changed* |
| 5 | Whether `007003206`/`007003207` — a cancelled booking and its recreation sharing one portal id — is a violation of control 14 or the expected OTA-modification pattern (R7). Affects the control's spec, not its code |
| 6 | Which controls a property has **nominated rate codes** for. `required_reservation_fields` excluded 71 of 108 records in v1 for want of them |
| 9 | Whether the LLM adapter should be wired to a real model, and to which |
