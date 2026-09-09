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
| 7 | Second provider — DemoPMS | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #11 |
| 8 | Scheduling & freshness | ☑ | ☑ | — | ☑ | ☑ | **done** — PR #12 |
| 9 | Compiler — English → IR | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #13 |
| 10 | Web UI & JSON API | ☑ | ☑ | ☑ | ☑ | ☑ | **done** — PR #14 |
| 11 | Transport (opt-in) & probe tooling | ☑ | ☑ | — | ☑ | ☑ | **done** — PR #15 |

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

`hotelcontrols/providers/demopms/` · `hotelcontrols/providers/registry.py` · `tests/contract/`
— **fixes F9. This is the thesis.**

DemoPMS is fictional and speaks **JSON**, with quirks deliberately different from MiniHotel's — and
"deliberately" is the load-bearing word. A second adapter that shared the first one's date format
and the first one's way of saying "nobody configured this" would be the same adapter twice, and the
boundary above it would still be untested.

| quirk | MiniHotel | DemoPMS |
| --- | --- | --- |
| dates | three numeric formats in one API (R2) | one format carrying a month **name** |
| "nobody configured this" | the number `0`, overloaded (R10, R12) | an out-of-band sentinel, so `0` stays real |
| money | amount and currency in different parts of the response (R9) | one self-describing object |
| booleans | `"YES"`, `"true"`, `"C"`/`"D"` | real JSON booleans, and words |
| occupancy | sibling lists | **nested inside its room** |
| statuses | `OK` / `IN` / `OUT` / `CL`, plus 3 nobody can name | `BOOKED` / `IN_HOUSE` / `DEPARTED` / `VOID`, plus the same 3 |

**The fixtures are generated, not written.** `tools/transcode_demopms.py` re-encodes the vendor
captures field by field: the same 138 reservations, 28 rooms, 5 folios and 2 occupancy segments —
**and the same gaps**. The folios nobody captured are still missing, the statuses nobody can name
are still unnameable, the 23 rooms with no configured capacity are still unconfigured. That last
part is what makes criterion 7 a test rather than a demonstration: a demo hotel that knew more than
the captured one would pass it by being a different hotel. v1 hand-wrote `fixtures/synthetic/` and
reached outcomes its captures could not.

**Unit tests**
- [x] DemoPMS transforms, mirroring slice 2's suite against a different wire format — including a
      date parser with an **explicit month table**, because `strptime("%b")` reads the machine's
      locale and a verdict must not depend on the machine that produced it (F11's cousin)
- [x] The JSON path grammar, including `strip_prefix` returning None for a path on another branch
      — R7 made structural in a format with no element tags to anchor on
- [x] The provider registry names nobody: **discovery by import**, asserted over the AST

**Contract tests — one suite, run against every registered provider**
- [x] Every provider implements the full `Provider` protocol
- [x] A missing field returns the registry's `absent_means`, identically, on both
- [x] Money always carries a currency, on both — **and a reservation is still in a different
      currency from its own folio on both** (R9 survived a format that keeps them together)
- [x] An unmapped status resolves UNKNOWN naming the code, on both (A5)
- [x] A record never reads a sibling's field, on both (R7)
- [x] Every refusal descends from `ProviderError`, so a runner has one place to turn "no" into a
      sentence and a new adapter cannot invent a fifth exception nobody catches

**Integration**
- [x] All 51 mappings resolve against their probe
- [x] The transcode is byte-identical on rebuild, and **the two providers report the same records,
      the same amounts and the same gaps** — checked canonically, through each adapter

**E2E**
- [x] **The same IR, over the same logical hotel, through two providers, yields the same verdicts**
      (criterion 7) — 11 controls × 3 as-of dates, compared per record id, and both providers cost
      the **same number of calls** for every control

**Gate**
- [x] Criterion 7 asserted
- [x] Adding DemoPMS required **zero changes** above the provider layer. The engine diff is
      `hotelcontrols/providers/**` and nothing else: no kernel, spec, evidence, evaluator, runner or
      store file changed. Everything else was data — a provider map, a tenant file, and one more key
      in each control's `population.provider_query`
- [x] The canonical-boundary test is now **symmetric**: both vendors' identifiers are banned above
      the adapters, and the allowed directories are discovered rather than listed, so the third
      adapter is policed from the moment it exists

## Slice 8 · Scheduling & freshness

`hotelcontrols/runner/scheduling.py` — **fixes F7**

Two pure functions. `next_evaluation` decides when a control runs next on a given provider;
`freshness_of` decides whether the evidence a run used was still current. A daemon is out of
scope; the decision is not, and it is fully testable with an injected clock.

**Unit tests**
- [x] Each execution mode — `event`, `scheduled`, `periodic`, `daily` — yields the documented plan
- [x] An event-mode control on a provider **without** that webhook falls back to its declared
      periodic interval, and says that is why — **naming the missing event**, so a hotel can take
      it to its vendor rather than just seeing a slower schedule
- [x] A control whose events are unpublished and which declares **no fallback** is
      `unschedulable` rather than being given a plausible interval. There is no honest default,
      and inventing one produces a control that merely *appears* to be running
- [x] `before_event(arrival, 24h)` resolves through the **property clock**, not UTC (F11), and a
      naive instant is refused rather than assumed local
- [x] Evidence older than `freshness_requirement.maximum_age` is marked stale on the run — and
      evidence whose age **cannot be established is stale too**, never assumed current
- [x] A duration the grammar does not define **raises** rather than defaulting
- [x] The functions are pure: same inputs, same output, no wall clock read

**Integration**
- [x] All 11 IRs produce a valid execution plan on **both** providers; none raises, and none is
      left without a trigger
- [x] A run over evidence captured twelve days earlier reports itself **stale** — and still
      reports its 28 verdicts. Staleness annotates a run; it never suppresses one
- [x] Freshness survives a store round trip, including a database written before the columns
      existed, which reads back as *cannot say* and therefore stale

**The one place the two providers disagree, and why that is right**

`resource_occupancy_consistency` runs in **real time** on MiniHotel and on an **hourly timer** on
DemoPMS, because only one of them publishes a room-occupancy event. Same rule, same evidence,
the same verdicts — a different trigger, and the plan names the missing event.

That is not a crack in criterion 7, which is about answers. *When* a control runs is a
capability question, and two providers that happened to publish identical webhooks would have
left the fallback path untested.

**Gate**
- [x] Clock injected everywhere; **no wall clock is read outside `kernel/clock.py`** — asserted
      over the AST for the whole engine, with prose exempt. `run()` was calling `datetime.now()`
      until this slice: a run's own timestamp decides its freshness, and a laptop in another
      timezone would have dated it differently from the hotel it describes
- [x] A stale run says so — **met in the API surface**; the page lands in slice 10

## Slice 9 · Compiler — English → IR

`hotelcontrols/compiler/` — **fixes F6**

**Unit tests**
- [x] The grammar parses the shapes the requirements doc uses: *"no X may …"* and
      *"X must not … unless …"* compile; *"every X arriving within N hours must …"* is
      **refused by name**, and that refusal is the honest answer rather than a gap — a window on
      arrival bounds the *population*, which is one PMS's endpoint and filters (criterion 5), and
      no IR operator compares a date against "now plus a duration". Accepting the shape would have
      meant inventing one of the two
- [x] A sentence naming vocabulary that does not exist is **rejected, naming the missing fields** —
      including the requirements doc's own VIP example, refused through the compiler for the same
      two reasons slice 1 refused it as hand-written JSON (§17)
- [x] An ambiguous sentence returns ambiguities rather than a confident guess. The live case is an
      unquoted operand: `reservation.status is cancelled` is either a text value or a canonical
      field, and the grammar says so instead of choosing
- [x] The `ModelCompiler` adapter is exercised with a **stubbed** model; its output goes through the
      same validation, and a malformed proposal is rejected exactly as a human's would be —
      **decision D9: the stub is the whole of slice 9.** No real model is wired
- [x] The stub emits each class of bad proposal: an undeclared field, an unknown operator, an
      aggregate with no `group_by`, a predicate with two right-hand sides — and a fifth, a field
      read but never declared as evidence. Each is rejected exactly as a hand-written IR would be,
      **and the messages are compared against `spec.validate` called directly on the same
      document**, so "the same code path" is tested rather than asserted
- [x] No test path can reach a real model or the network — asserted over the AST: the package
      imports no `urllib`, `http`, `socket`, `ssl` or vendor SDK, and calls no `eval`/`exec`/
      `compile`

**Integration + E2E**
- [x] **All 11** shipped controls round-trip, and the check is stronger than "the same verdicts":
      the compiled rule is **clause for clause the shipped rule** — entity, references, scope,
      exceptions, assertion and the same set of evidence fields — and then reaches identical
      verdicts on **both providers across all three instants** (66 run comparisons). `note` is
      excluded from the comparison: it is prose explaining *why* a predicate is shaped as it is,
      which a compiler has no business inventing
- [x] Compiling and immediately running a **new** sentence produces a run with no code change
      (criterion 6, from the other end). *"every reservation where reservation.status is not
      `cancelled` must have reservation.guest.email exists"* — a control this repository has never
      held — reaches **5 PASS, 19 FAIL, 13 UNKNOWN, 71 EXCLUDED on both providers in one call**

**Gate**
- [x] Criterion 9 asserted
- [x] The compiler emits IR only — never executable anything. Asserted twice: the output survives
      a `json.dumps` round trip, and no dynamic-execution builtin appears anywhere in the package

**The measurement, recorded rather than engineered away**

Each control now carries **two** sentences. `natural_language` is the prose a person wrote —
*"A reservation cannot be closed while the guest still owes money."* `restricted_language` is the
same rule in the controlled language the grammar accepts:

```
every reservation where reservation.status is "checked_out"
    must have folio.balance_due at most 0
    showing reservation.departure_date and folio.currency and reservation.currency
```

**The grammar parses 0 of the 11 prose sentences, and 11 of 11 restricted forms.** The first number
is asserted by a test that fails if it ever rises. Teaching the grammar that "still owes money"
means `folio.balance_due at most 0` would be an eleven-entry phrase book, every measurement taken
against it would be a measurement of the phrase book, and it would put the §17 gate to sleep — the
gate can only answer "that field does not exist" *by name* if the author named a field.

`tools/validate_spec` recompiles every declared sentence on every run and compares it to the rule
filed beside it, so the two cannot drift apart: **1080 checks**, up from 1003.

---

## Slice 10 · Web UI & JSON API

`hotelcontrols/web/` — thin on purpose. Its job is to prove a verdict is explainable.

**Unit tests**
- [x] `handle(path)` is a pure function of the path — routing testable without a socket. Path
      segments are unquoted **individually, after splitting**, so a `%2F` inside an id cannot
      silently reshape the route: `/run/..%2F..%2Fetc%2Fpasswd` stays one control id and reaches
      the spec loader, which refuses it by name
- [x] Well-formed JSON for an empty population, a blocked run, and a run that concluded nothing —
      and a blocked run carries **no `counts` key at all**, because zeroes in a payload get
      charted by somebody and a chart of a run that never happened is a chart of nothing
- [x] An unexpected error renders as a page, never a dropped connection — and an error on an
      `/api/` path renders as JSON, because an API that answers HTML breaks its client's parser at
      the worst moment
- [x] HTML escaping on every value that came from a provider: values, reasons, record ids,
      provenance strings and the control's own sentence

**Integration + E2E**
- [x] Every control × every evidence set renders — 11 controls × 2 properties × 2 captures, HTML
      and JSON, asserted. Plus the cheapest useful guard in the file: no page ever contains
      `" object at 0x"`, which is what a `Value` interpolated into a template looks like
- [x] **UNKNOWN is distinguishable from FAIL by hue, border and wording** — the wording half is
      asserted with every tag stripped, so it survives a monochrome screen, a printout and a
      colour-blind reader: **VIOLATION** against **NO ANSWER**, each with a sentence saying which
      of the four things happened. The hue and border halves are asserted against the stylesheet
      itself, and all four outcomes carry a distinct border style — solid, double, dashed, dotted
- [x] Every verdict block lists each field, its value with unit, and the call it came from
      (criterion 3), asserted on the real overpaid folio: `007004348`, `-490.75 ILS`, from
      `GetReservationBalance`
- [x] Readiness appears on the index; history appears per control, newest first, re-read with
      **zero provider calls** — asserted by counting the app's own call meter across the re-read

**Gate**
- [x] Criteria 2, 3, 8 and 10 asserted
- [x] The demo runs offline with no dependencies: no page loads a script, a font or any `http://`
      resource, and the stylesheet is served from the package

**The bug this slice found by running the thing rather than reading it**

The suite was green and the demo answered `500 ProgrammingError: SQLite objects created in a
thread can only be used in that same thread` on its first run page. `ThreadingHTTPServer` handles
every request on a new thread; the run store is one `sqlite3` connection opened when the app was
built. Nothing in the suite had ever crossed a thread — because `handle(path)` is a pure function
of a string, which is exactly what makes this layer so pleasant to test.

The server is now serial, which is right for a single-operator local demo, and the constraint is
named in a test rather than hidden behind `check_same_thread=False` — that flag would have turned
an exception into a data race. **The lesson is the one this project keeps relearning: a green
suite is a statement about what was asked, not about what works.**

---

## Slice 11 · Transport (opt-in) & probe tooling

`hotelcontrols/providers/transport/` · `hotelcontrols/providers/minihotel/live.py` ·
`tools/probe.py` — **fixes F13**

**Unit tests**
- [x] The transport is **disabled unless an environment variable is set, and a test cannot set it.**
      Two locks, and the second one is the real one: an environment variable alone is a lock whose
      key is one line of `monkeypatch.setenv` away, so the transport also refuses to arm while a
      test runner is loaded in the process. The test that matters sets the variable and is refused
      anyway
- [x] Token-bucket rate limiter honours its interval, with an injected clock — and never sleeps:
      it is asked "may I go now?" and answers "yes" or "wait this long". A limiter that slept could
      only be tested by a test that slept, so it would be tested loosely, and a rate limiter that is
      wrong is wrong in production on somebody else's infrastructure
- [x] Retry backs off and gives up; a give-up is `ResponseUnavailable`, which the evidence layer
      turns into UNKNOWN with a reason. **A refusal to arm is never retried** — a disabled transport
      is a configuration mistake, and three attempts with backoff turns a loud instant failure into
      a slow confusing one
- [x] The per-run call ceiling reuses the existing `CallBudget` (R1, R8) — asserted by running
      `gather` over a live-shaped source. The honest footnote is recorded too: the budget counts
      LOGICAL calls, and one may cost up to `attempts` requests on a flaky network. That
      amplification is bounded and asserted rather than hidden
- [x] **Record mode** writes a response plus its request fingerprint into the fixture set — and
      writes into `raw/`, which `.gitignore` covers, because a live response carries guest names,
      emails and free-text remarks and this repository is public (D6, F15)
- [x] Credentials come from the environment with **no default**; a missing one fails loudly naming
      the variable, an empty one counts as missing, and the password never appears in a `repr` (F15)

**Integration**
- [x] A recorded response replays through the frozen path and yields identical `Value`s — and a
      whole control runs off a capture recorded seconds earlier, reaching the same verdicts as the
      shipped one
- [x] With the environment unset, every code path that would open a socket raises instead — the
      dialer, a source with no injected dialer, and a whole `run()` through an unarmed transport
- [x] **Exactly one file in the engine can reach the network at all**, asserted over the AST:
      `providers/transport/http.py`. `urllib.parse` and `http.server` are deliberately not on that
      list — splitting a URL and LISTENING on a port are not the capability R8 is about

**Gate**
- [x] Criterion 11 asserted: no test can reach the network
- [x] `probe.py` is staged and bounded, and prints its plan before making any call.
      `python3 -m tools.probe --plan` makes none, and a test asserts that by making
      `FrozenSource.fetch` raise and running the whole plan anyway

**The live request form, and where it comes from**

`providers/minihotel/live.py` is the encoder: one canonical `Request` becomes the call this vendor
actually accepts. Every form in it is **transcribed from a call that produced a response in
`fixtures/minihotel/`** — not from documentation, which never states how to encode a request at all.
Probing the WSDL showed the operations declare empty parameter types, so the service reads the raw
body. That was discovered by trying it.

Three things it refuses rather than guesses. `BulkARI`'s response is in the fixture set and the
request that produced it was not recorded, so there is no form to send. An occupancy query with no
window is the wide unbounded range R8 forbids. A filter with no captured form is refused rather than
dropped — dropping one hands back a wider population than the control asked for.

**The plan is the thing being approved.** `--plan` prints the endpoint, the resolved window, the
stage, the cost against the property's budget, and **the exact request body**, with `<user>` and
`<password>` where the credentials go — because a plan is made to be pasted into a message, and one
that leaked a password the first time it was useful would be worse than no plan.

**DemoPMS has no live request form and says so.** It is fictional; it can be replayed and it cannot
be probed. Inventing a wire format for a PMS that does not exist would make this slice look more
finished than it is.

---

## Definition of done

The twelve success criteria in `prd.md`, assessed honestly against tests — not against intent.

Where a criterion is not met, it is recorded here as **not met**, with what is missing. That is what
v1 did while control 6 could reach neither PASS nor FAIL, and it is why the eventual "met" was worth
something.

| # | Criterion | State |
| --- | --- | --- |
| 1 | ≥8 of 11 controls reach PASS or FAIL; the rest name their blocker | **NOT MET — 5 of 11.** The second half IS met: every non-concluding control names its blocker. See the assessment below |
| 2 | All four outcomes from captured evidence; UNKNOWN distinct from FAIL | **Met** — all four reached from captured evidence since slice 4, and the distinction is asserted three ways: wording with every tag stripped, border style, and hue |
| 3 | Every verdict traces to its fields | **Met** — structurally; a `Verdict` cannot be built without evidence |
| 4 | Call count is `1 + R + N`, asserted | **Met** — counted invocations, slice 3 and again end to end |
| 5 | No PMS identifier above the provider layer | **Met** — 28 identifiers from **both** providers grepped over the tree, with the allowed directories discovered rather than listed |
| 6 | A twelfth control is a spec change | **Met** — and in its stronger form: a control that has never existed is *compiled from a sentence* and run end to end from a spec directory, on both providers, with no import touched |
| 7 | Same IR, two providers, same verdicts | **Met** — 11 controls × 3 as-of dates, per record id, with identical call counts. The demo fixtures are the vendor captures transcoded, gaps included |
| 8 | A run that concluded nothing says so | **Met** — slice 6's coverage verdict |
| 9 | English compiles to IR; unsupported sentences rejected by name | **Met** — 11 of 11 controls recompile from their own restricted-English sentence to the same rule and the same verdicts; an undeclared field, an unknown operator, an ambiguous operand and a population window are each refused by name |
| 10 | Readiness reported per control per provider | **Met** — on the index, per control, for both providers, and at `/api/readiness/<control_id>` |
| 11 | Offline, stdlib-only runtime, no test reaches the network | **Met** — exactly one file in the engine imports an outbound client, and it refuses to arm both when the environment variable is unset AND while a test runner is loaded. A test that sets the variable is still refused |
| 12 | Every slice green in CI before the next opens | **Met** — twelve slices, twelve green pipelines on Python 3.11 and 3.13, each merged before the next opened |

### Criterion 1, assessed: 5 of 11, and where the other six went

The number is measured by `tests/e2e/test_runs.py`, which holds the sets by name so a change in
any of them turns a test red rather than passing quietly. It is asserted as **not met**, and the
test says so in its own name.

**Five conclude** on the 2026 capture: `checkout_money_owed`, `checkout_unrefunded_credit`,
`duplicate_channel_reservation`, `inactive_room_future_stay`, `room_assignment_type_validity`.

**One is blocked** — `resource_occupancy_consistency`. Its only occupancy capture covers
2024-08-14..2024-08-21, and a run asking about any other week is refused rather than answered from
the wrong one. Asked on 14 August 2024 it concludes perfectly well (2 PASS), which is asserted
separately. **It counted towards criterion 1 until issue #9 was fixed**: it had been reaching two
PASSes about July 2026 from segments captured in August 2024. The number went down and the guard
stayed, which is the whole point of the project.

**Five reach no conclusion**, and every reason is a fact about the property or the provider rather
than a gap in the engine:

| control | why it cannot answer |
| --- | --- |
| `ooo_room_protection` | no room in this property has ever had a closed-date window set, so the control correctly applies to none of the 28 (open question 2.4) |
| `room_assignment_active_room` | the same closed-date window, from the reservation side — 111 stays, all excluded |
| `room_capacity_compliance` | 23 of 28 rooms report adult capacity `0`, meaning *unconfigured* (R12). Reading those as real zeroes would be a wall of false FAILs |
| `rate_room_category_consistency` | a rate code and the price-list code are different key spaces (R13), so no endpoint resolves the mapping at all (open question 1.6) |
| `required_reservation_fields` | this property has nominated no rate codes, so the control applies to no reservation (open question 1.4) |

**Three of those six would move on a conversation rather than on code.** One sentence naming this
property's nominated rate codes takes `required_reservation_fields` from zero answers to real ones.
One sentence from the vendor about what `OK4` and `WL` mean resolves 44 of the 217 reservations
this project has ever seen. A rate-plan mapping supplied by the hotel unblocks control 9. The other
three are the property being what it is — and reporting "compliant" about a mechanism nobody has
ever seen working is exactly what v1 did.

**The second half of criterion 1 IS met**: every control that does not conclude names its specific
blocker, on screen and in the API, and a run that concluded nothing shows no count tiles.

---

## Where this leaves the build

Twelve slices, twelve green pipelines, **eleven of twelve criteria met**. The one that is not is
recorded above with its arithmetic, which is the outcome this document was written to make
possible: v1 met all seven of its own success criteria while nine of its ten controls answered
nothing at all.

What exists at the end: a canonical vocabulary and a validation gate; two provider adapters that
agree on every verdict over the same hotel through two deliberately incompatible wire formats; a
bounded evidence layer whose cost is asserted rather than assumed; a four-outcome evaluator with
Kleene logic and no path to a verdict without evidence; a runner that says when it concluded
nothing; scheduling and freshness as pure functions; a compiler from restricted English that
refuses vocabulary nobody declared, by name; a demo that shows the fields behind every answer; and
a live transport that is built, tested, and cannot be switched on by a test.

What does not exist, on purpose: Mews, a scheduler daemon, webhook ingestion, authentication,
writes to any PMS, and free text as evidence. Each is listed in `architecture.md` §6 with what it
would take.

## Checkpoints needing the project owner

Recorded here so they are not discovered late.

| Before slice | Decision needed |
| --- | --- |
| 3 | **Approval for 3 read-only calls** (`getRooms`, `getRoomTypes`, `RoomStatusInquiry`) to confirm whether the 2024-era room findings still hold. The sandbox is known to have moved on; three controls rest on findings that are now *unverified since the system changed* |
| 5 | Whether `007003206`/`007003207` — a cancelled booking and its recreation sharing one portal id — is a violation of control 14 or the expected OTA-modification pattern (R7). Affects the control's spec, not its code |
| 6 | Which controls a property has **nominated rate codes** for. `required_reservation_fields` excluded 71 of 108 records in v1 for want of them |
| ~~9~~ | ~~Whether the LLM adapter should be wired to a real model, and to which~~ — **answered 2026-09-09, decision D9: no, not in slice 9.** Build the seam, exercise it against a stub. The model adapter, if ever wired, is a dev-time tool under `tools/` and never a runtime component |
