# Plan — v3

What v3 builds, in what order, and what it deliberately does not. `docs/plan.md` is the **v2
build log** (slices 0–15) and stays as it is; this file continues the numbering at **16**, so
branch names stay `slice/NN-name`.

Written 2026-10-09 on `docs/v3-plan`, from `main` at `7f384c4`. Input: `docs/stayops-gap-analysis.md`
(measured on `5d5143c`, 18 commits earlier), **every "what exists" claim in it re-verified against
`main` by a grep or a run** (§2). Owner decisions taken during planning are D12–D16 in
`docs/open-questions.md`.

**Status: APPROVED by the project owner on 2026-10-09 (PR #50).** Implementation starts from
`docs/v3-implementation-brief.md`: fix #48 first, then slice 16.

---

## The rule that governs v3

> **A gap earns a place in v3 only if it can be built without widening a verdict, without crossing
> the canonical boundary, and without changing a single answer the engine gives today — or, where
> it must change one, the change is deliberate, named, and shown in a reviewed diff.**

`CLAUDE.md`'s rule outranks this one: **never widen a verdict.** Applying it to the gap report was
not a formality. **The item the report and the brief both rated cheapest and safest — a twelfth
control, *card on file before arrival* — turned out to be the most dangerous thing on the list.**
Measured in §3, it would have passed every reservation ever captured, because the evidence it reads
is a placeholder.

---

## Status

| # | Slice | Gaps | Size | State |
| --- | --- | --- | --- | --- |
| — | Fix #48: card presence is not established | (G4) | S | **done** — PR #52, merged. A mask with no digits, or a blank, resolves UNKNOWN naming #48 / 2.8 on both providers. 2006 passed / 2 skipped, 1080 checks, 120 goldens and 11 DemoPMS files identical, 96% |
| — | Fix #49: the 1.4 rate-code claim | (docs) | — | **closed by this PR** |
| — | Fix #54: drafts README lacked the lock step | (docs) | — | **done** — PR #55 |
| 16 | Policy versioning | G6b | M | **done** — PR #53. — `slice/16-policy-versioning`. Spec lock + `tools/lock_spec.py`; runs name `policy_version` + `policy_digest`; pre-v3 rows say *version not recorded*; history grouped by rule. Declared: 99 goldens gain the two keys, nothing else (V1 holds). 2280 passed / 2 skipped, **1091** spec checks (+11, one lock check per control), 120 goldens and 11 DemoPMS files identical after the rebuild, 96%. The v3 scope guard and the V1 test run on every push from here |
| — | Fix #57: drafts README described the pre-slice-17 layout | (docs) | — | **done** — PR #58 |
| 17 | Tenant-scoped store | G5 (data half) | M | **done** — PR #56. — `slice/17-tenant-scoped-store`. Store reads take `tenant_id` keyword-only (a missing one is a `TypeError`); another property's run is the same 404 as a missing one; structural guard over every SQL literal and every executed statement, seen failing on a planted `SELECT`; drafts per property. Declared: 11 mixed history goldens split into 22 per-property ones, rows filtered and `property` added, nothing else; 88 run goldens and readiness byte-identical. 2321 passed / 2 skipped on the branch, 1091 checks, **131** goldens, 11 DemoPMS, 96%. On `main` the v3 scope guard skips, so expect one fewer pass and one more skip |
| 18 | Findings queue — advisory action records | G2(a), G8 queue, G10c | L | **done** — PR #61. — `slice/18-findings-queue`. New pure `hotelcontrols/actions/`: only a FAIL raises a task, severity and audience straight from the IR's `action` block. An `actions` table keyed by (property, control, policy version, record), born under slice 17's guard and seen failing on a planted unscoped `SELECT`. The layer above the run raises tasks (`runner/` untouched); drafts raise none. `pending → done | dismissed` through an injected clock, actor `operator`; a later PASS annotates and never closes. `/queue` and `/api/actions` state each control's latest conclusion beside the tasks; an in-memory queue says it is lost on restart; `--store PATH` is opt-in; React `/queue` too. **#59 corrected** (note under the exit test): proven on `007004348` (`medium`/`finance`, both providers) and on a constructed money-owed run. Declared contract changes: none — 4 new goldens, the 131 existing byte-identical. 2427 passed / 2 skipped on the branch, 1091 checks, **135** goldens, 11 DemoPMS, 96%. React: 182 Vitest, 22 Playwright. On `main` expect one fewer pass and one more skip |
| 19 | Email, opt-in, behind two locks | G8 email | M | **next** |
| 20 | Operational log | G14 | M | planned |
| 21 | Typed hotel parameters, with "not decided" | G6a (narrowed) | M | planned |
| 22 | Guest services: `LATE_CHECKOUT` | G1 (narrowed), G3a, G2(a) | L | planned |
| 23 | Evidence refresh — owner-approved probe | (1.2, #49) | S | planned; **skipped if not approved** |
| 24 | Authentication at the host, credentials per property | G5 (auth half), G11 (narrowed), #22 | L | planned |

Each row is one branch, one PR, green CI, squash-merge, and the next does not open until it has
merged (D7, criterion 12). Sizes are relative, like the report's effort scores, not estimates.

---

## 1. The regression wall

Measured at the start of this session, on `main` at `7f384c4`. **Every v3 slice keeps every one of
these, or its PR says which moved and why.**

| Check | Command | Baseline |
| --- | --- | --- |
| Suite | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q` | **1996 passed, 2 skipped**, 0 failed |
| Spec | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec` | **PASSED - all 1080 checks** |
| API goldens | `… -m tools.dump_api_fixtures --check` | **120 files, identical** |
| DemoPMS transcode | `… -m tools.transcode_demopms --check` | **11 files, identical** |
| Coverage | `.venv/bin/python -m coverage run -m pytest && … coverage report` | **96%** (3904 statements, 129 missed) |
| Criterion 1 | `tests/e2e/test_runs.py` | **5 of 11**, NOT MET, recorded as such |

The two skips are known and correct: the hosted model backend is an optional extra, and the
slice-15 guard skips on any branch not named `slice/15-*`.

**What "nothing breaks" means, per slice.** All six rows hold. The suite count may only rise. The
**120 golden payloads stay byte-identical** unless the slice *declares* a contract change, in which
case it rebuilds them and the PR shows that the diff touches only the declared keys or files, never
a verdict. The two-provider e2e test (`tests/e2e/test_two_providers.py`) is unchanged and passes.
The criterion-1 figure is re-measured, never rounded, whenever a control or a capture is added.

**A scope guard per slice.** Slice 15's `test_slice15_engine_untouched.py` proved that "no core
logic may break" can be a test rather than a promise. v3 generalises it: **the first commit on
slice 16's branch adds `tests/unit/test_v3_slice_scope.py`**, which holds a table of which paths
each v3 slice may change and fails a `slice/NN-*` branch that changes anything else. It is seen
failing on a planted edit before it is relied on, and it fails rather than skips when it cannot
find `origin/main`, as slice 15's does. The per-slice **may change / must not change** lines below
*are* that table.

---

## 2. What was re-verified, and what changed since the report

The report was measured on `5d5143c`. Each claim this plan relies on was re-checked on `7f384c4`:

| Report's claim | Re-verified by | On `main` now |
| --- | --- | --- |
| No guest services (G1) | `grep -rniE "late_checkout\|APPROVED_WITH_FEE\|staff_review\|early_checkin\|room_upgrade\|extra_towels\|maintenance_request" hotelcontrols spec tests` | **0 hits.** Unchanged |
| 11 IRs, 53 fields, 7 entities, no `hotel`/`availability`/guest entity | counted `spec/ir/`, `spec/canonical_fields.json` | **Unchanged**: reservation 22, stay 5, room 9, room_type 2, folio 8, occupancy 5, rate_plan 2 |
| IR `version` read by no loader; `Run` and `runs` have no version (G6b) | grep of `hotelcontrols/`; `Run` dataclass; `schema.sql` | **Unchanged.** Every IR says `"version": 2`; only `spec/schema.py` type-checks it |
| Two tenant settings, no parameter schema (G6a) | `spec/tenants/*.json` | **Unchanged**: `nominated_rate_codes: []`, `rate_plan_permitted_room_types: {}`. Fix #45 added a *collection-shape* check for `in`/`not_in`; still no schema and no "not decided" state |
| `tenant_id` stored, never filtered; property from `?property=` (G5) | every `SELECT`/`WHERE` in `store/sqlite.py`; `App._selection` | **Unchanged.** `load` and the evidence/verdict reads filter on `run_id`, `history` on `control_id`. `_selection` still falls back to the first property |
| IR `action` block read by nothing; no `smtplib` (G8) | grep | **Unchanged.** All 11 IRs declare `{type: notify, severity, audience}` |
| `next_evaluation` run by nothing (G10a) | grep for callers | **Changed, slightly**: `/api/plan` (#42) now calls it on demand to show "when this runs next". Still no loop |
| `make_run_id` hashes `created_at` (G10c) | `store/sqlite.py:81` | **Unchanged** |
| Credentials keyed by provider (G11, #22) | `Credentials.from_environment(cls, provider)` | **Unchanged**; issue #22 still open |
| No logging layer (G14) | `grep -rl "import logging" hotelcontrols tools` | **0 files.** Unchanged |
| No create/validate/activate/pause (G13) | the route table in `web/app.py` | **Unchanged.** Read-only routes plus the four compose `POST`s; `/api/controls`, `/properties`, `/history`, `/drafts`, `/outcomes`, `/plan` are new since the report |
| EXCLUDED tile + coverage headline (G13's note) | slice 14/15 | **Already true on both surfaces** |
| Webhooks: nothing subscribes (G10d) | grep | **Unchanged.** Four hits, all comments |
| The demo's store is in memory (brief §8.8) | `App.__init__`, `server.py` | **Unchanged.** `RunStore(":memory:")` unless a caller passes one |

**Two claims did not survive, and both are now issues.** They are §3.

---

## 3. Two findings from verification

### 3.1 The card on file is a placeholder — issue #48

`reservation.guest.payment_card_present` is mapped on both providers, flagged `observed_populated:
true`, and described as *"whether a card is on file"*. Every captured card element is the same:

```
grep -rhoE '<CreditCard [^>]*>' fixtures/minihotel/*.xml | sort | uniq -c | sort -rn
  216 <CreditCard Type="" Number="****" NameOnCard=" " ExpirationDate="202101" />
    8 ...ExpirationDate="202210"   2 ..."203110"   1 ..."202812"   1 ..."202510"
```

All **228 of 228** carry `Number="****"`, with no last four digits. So the field is `True` on every
record ever captured, and **216 of them "expire" in January 2021** on reservations dated up to 2026.
That is the shape of a default the PMS emits whatever the real state, and nothing captured shows
what a reservation with no card looks like.

Dry-run in a scratch spec directory outside the repository (never committed): a card-on-file control
over arrivals `today..today+90d` on sandbox2026 at 2026-07-08 gives **24 PASS, 0 FAIL**, 13 UNKNOWN
(`OK4`) and 71 EXCLUDED (cancelled), identical through both providers. **It cannot FAIL, because
the field is never false.** Shipped, it would have reported 24 reservations as compliant on the
strength of a placeholder: an UNKNOWN made into a PASS, in the first control v3 added.

No shipped IR, test or tool reads the field (`grep -rln payment_card_present spec/ir tests tools
hotelcontrols` → nothing), so **no current verdict is wrong**. The fix makes the field resolve
UNKNOWN with that reason. It lands on `fix/48-…` before slice 16, with no golden and no
criterion-1 change. What would establish the field properly: MiniHotel saying what that element
means (**new question 2.8**), or a capture of a reservation known to have no card.

### 3.2 Nominated rate codes alone would not move control 15 — issue #49

`plan.md` and `open-questions.md` said one sentence naming the property's nominated rate codes
(question 1.4) takes `required_reservation_fields` "from zero answers to real ones". Measured with
`nominated_rate_codes: ["Tourist-BB"]` in memory: **identical counts** to the shipped `[]`.
`stay.rate_code` is absent from all 108 captured reservations, because the captures were not taken
with `IncludeRoomPrices`, which the IR itself says is required. And the 2024 captures block this
control outright.

So control 15 needs a hotel's list **and** a capture taken with room prices (slice 23). There is a
second point, which this PR writes down: the sandbox is the vendor's test property, so **nobody can
honestly nominate its rate codes.** Supplying a list for it would mean inventing a hotel's policy
to move the criterion-1 figure.

---

## 4. Disposition of every gap

Five filters, applied in order (brief §5): **accuracy → architecture → evidence → decision → value**.
A gap that fails one does not reach the next. Exposure scores are the report's, carried so the
re-ranking is auditable.

| Gap | Exp | Disposition | Why — the filter that decided it | Where / trigger |
| --- | --- | --- | --- | --- |
| **G1** guest-service machinery | 15 | **TAKE, NARROWED** | Additive above L5; no boundary crossed; read-only (D12). **Cut:** prose intent extraction (a model reading guest prose would put NL in the decision path, so the request arrives structured, D12); every template but one | Slice 22 |
| **G2(a)** advisory actions | 8 | **TAKE** | Owner-decided (1.10). An action is a *record with a state* a person performs | Slices 18, 22 |
| **G2(b)** acting | 25 | **REJECT** | Architecture: reverses `prd.md` §6, *read-only, permanently*. Owner-decided 2026-10-09 | — |
| **G3a** `LATE_CHECKOUT` | 10 | **TAKE** | Evidence risk 2: `reservation.departure_date` and `reservation.status` resolve on both providers; the hotel's times and fee are parameters. Decision set and names ruled (D15) | Slice 22 |
| **G3b** towels + maintenance | 6 | **DEFER** | Value: sound and cheap, but not before one template has proved the path. Maintenance *classification* must be a pick-list or staff-confirmed, never a model's choice (D10) | Slice 22 merged, and the owner asks |
| **G3c** `EARLY_CHECKIN` | 9 | **DEFER** | Evidence: `room.housekeeping_status` is mapped and populated, but which code means *ready* is per property and unestablished, and the room captures are 2024-era (1.2). Built today, every request would be `STAFF_REVIEW` | Slice 23 refreshes room data, **and** a hotel supplies its "ready" codes |
| **G3d** `ROOM_UPGRADE` | 15 | **BLOCKED** | Evidence 5: no availability entity; the ARI key space is not the rate-code key space (R13); the only ARI capture is 2024 | A captured availability response joinable to a reservation |
| **G4** as specified | 20 | **BLOCKED** | Evidence 5: `payment_guarantee_status` and `complimentary` exist in no captured response | A hotel's guarantee/comp policy as data, **and** evidence to apply it to |
| **G4** narrowed (card on file) | 6 → **25** | **BLOCKED** — *re-scored* | **Accuracy, new in this plan.** The card is a placeholder on 228/228 captures (§3.1, #48). It would PASS everything. The comp exception cannot help either: the rate code it would key on is absent from all 108 captures (§3.2) | MiniHotel answers **2.8**, or a capture of a known no-card reservation. Then re-plan as a spec-only slice |
| **G5** isolation | 20 | **TAKE, NARROWED** | Architecture: L1–L5 untouched; additive layer. Order owner-decided (D13). **Cut:** roles beyond one signed context, the Organisation→Hotel hierarchy (D1 §48 defers it too), engine-owned login (D14) | Slices 17 (data), 24 (auth) |
| **G6a** templates + parameters | 12 | **TAKE, NARROWED** | Accuracy: the `tenant_setting` mechanism already lets one IR serve two hotels. What is missing is a *typed schema* and a **"not decided" state** distinct from "decided: none". Today an empty list means both, which is safe in a scope and would be **unsafe in an exception**. **Cut:** reshaping IR storage into a template library | Slice 21 |
| **G6b** policy versioning | 8 | **TAKE** | Additive: a field, a column, a spec lock. No verdict moves | Slice 16 |
| **G6c** lifecycle + activation gate | 6 | **DEFER** | Value: with no scheduler, *active* means nothing operational. Gated on readiness today, it would hide the five controls that correctly report their blockers, which hides honest UNKNOWNs | G10a returns: something runs unattended and needs to know what is active |
| **G7** adapter shape | 2 | **REJECT** | Architecture: entity methods (`getPayments()`) would hide the per-record call (R1, idea 4) and force a value onto fields that are *unknown with a reason* | Recorded as a decision, not a shortfall |
| **G8** notifications | 8 | **TAKE** (advisory) | Read the `action` block every IR has carried since slice 1. Email behind the transport's two locks | Slices 18, 19 |
| **G9** Mews | 20 | **BLOCKED — out of v3** | Owner decision. Also evidence 5: no credentials | Credentials, and the owner reopening it |
| **G10a** scheduler daemon | 6 | **DEFER** | Evidence/R8: an unattended loop means something only against **live** evidence, and continuous calls need the vendor's agreed limits (question 2.6) and per-property credentials. Over a frozen capture it would produce fresh-looking runs of stale evidence | MiniHotel answers 2.6, and slice 24 merged. **Design pre-recorded:** a second *process* with its own SQLite connection to a file store, never a shared connection (brief §8.3) |
| **G10b** queue + workers | 6 | **DEFER** | Value: unneeded below a few hundred properties | That scale |
| **G10c** idempotency | 8 | **TAKE, NARROWED** | Architecture: changing `make_run_id` would change every stored run's identity and every golden. Idempotency is placed instead on the **action record's natural key**, so a retried or repeated run never duplicates a notification. **`run_id` is unchanged** (§6.6). **Cut:** job-level keys, which belong with G10a | Slice 18 |
| **G10d** webhooks | 9 | **BLOCKED** | Evidence: MiniHotel's webhook payloads have never been observed. Architecture: a public endpoint changes the security posture | A captured webhook payload, plus auth (slice 24) |
| **G11** onboarding + connections | 12 | **TAKE, NARROWED** | Only #22: credentials keyed **per property** from the environment. **Cut:** connect/test/discover (each is a live call, D3), and encrypted storage (D14, deferred) | Slice 24. The rest returns with a pilot property (1.9) |
| **G12a** availability | 15 | **BLOCKED** | Evidence 5 (as G3d) | As G3d |
| **G12b** `vip_status` | 15 | **BLOCKED** | Accuracy + decision: exists only as Hebrew free text (1.5). An extractor would put NL into the *evidence* path. The most dangerous item in the report | Owner answers 1.5, and then only an extractor that quotes its source or says UNKNOWN |
| **G12c** `company_id` | 10 | **BLOCKED** | Evidence: no company or corporate-account entity in any endpoint | A PMS that exposes one |
| **G12d** stable ids | 6 | **DEFER** | Value: a second source of truth that can disagree with the provider | A provider renumbers anything |
| **G13** management API + admin UI | 6 | **DEFER** | Decision: the write half manages objects that do not exist yet (lifecycle, G6c) and needs an authorised caller (slice 24). The read half and compose JSON already exist (§2) | G6c taken, and slice 24 merged |
| **G14** observability | 6 | **TAKE, NARROWED** | Additive. **Cut:** metrics, external sinks, and anything logged from *inside* a provider (it would name endpoints above the boundary) | Slice 20 |
| **G15** per-tenant rate limits | 4 | **DEFER** | Value: nothing live to share yet | Two live properties on one provider |

**Not a gap, but in v3:** slice 23, the evidence refresh. It closes nothing in the report by itself.
It is what makes three BLOCKED/DEFER rows above movable, which is why the owner put it in (D16).

### Why the sequence is not the exposure order

The report ranks danger; a sequence must respect prerequisites and this plan's governing rule.

- **Versioning first (16)**, because every record v3 creates — an action, a guest decision — must
  name the policy version that produced it, and the findings queue's idempotency key includes it.
- **Isolation of data second (17)** (D13), so that every table v3 adds is *born* tenant-scoped under
  a structural guard rather than retrofitted. It is cheap, because three methods touch the store,
  and protective, because one missed `WHERE` is a breach rather than a bug.
- **The findings queue (18) before email (19)**, so a notification is a side effect of a record
  that already exists and is already deduplicated.
- **Typed parameters (21) immediately before guest services (22)**, because `LATE_CHECKOUT` is the
  purest case of one template with per-hotel parameters, and its times and fee must be typed,
  validated and able to say *"not decided"*.
- **The evidence refresh (23)** is independent of the others. It may move earlier at the owner's
  word. It is gated on the owner's approval of each printed request *at the time*, and if that
  approval never comes it is skipped and nothing depends on it.
- **Authentication last (24)** (D13), because its design depends on the host product (D14) and
  everything it protects must exist first.

---

## 5. The slices

Every slice: written test-first from the specification; every test names the criterion, IR clause
or risk id it protects; `PYTHONDONTWRITEBYTECODE=1` when proving a test fails without its fix;
branch `slice/NN-name` → PR → `test (3.11)` and `test (3.13)` green → squash-merge. Where a slice
adds an interface, its PR updates `docs/architecture.md` for what was built. The plan describes
design intent and does not pre-empt that.

---

### Before slice 16 · Fix #48 — card presence is not established

**Delivers:** the engine stops claiming to know whether a card is on file, because no capture can
tell it.

- **May change:** both providers' card transforms, `spec/canonical_fields.json` (description),
  `spec/providers/*.json` (notes), `tools/transcode_demopms.py` only if the DemoPMS transform needs
  it. **Must not:** any IR, any other field, the evaluator.
- **Test gate (red first):** a constant mask (`****`) resolves **UNKNOWN naming why**, on both
  providers (contract suite). A blank number resolves UNKNOWN too. No capture has ever shown one,
  so reading it as "no card" would be a guess about the vendor's encoding.
- **Nothing breaks:** 120 goldens byte-identical (no IR reads the field); criterion 1 unchanged;
  readiness unchanged for all 11 controls.
- **Not:** a G4 control. That stays BLOCKED until 2.8 is answered.

---

### Slice 16 · Policy versioning (G6b)

**Delivers:** every stored result says which version of the rule judged it, and editing a rule
without saying so is refused.

**Work.**
- The loader **reads** `version`. A spec lock (`spec/ir.lock.json`: control → version → digest) is
  generated by a tool. `tools.validate_spec` fails when a control's **verdict-bearing content**
  changed and its version did not: population, references, scope, exceptions, assertion,
  required evidence, unknown conditions, and the sentences shown beside a verdict. *"Editing a
  policy makes v2"* becomes mechanical rather than remembered.
- `Run` gains `policy_version` and `policy_digest`. `runs` gains two nullable columns through the
  existing `_migrate`. **A run stored before this slice reads back as "version not recorded"**,
  never as the current version. This is the freshness rule applied to identity.
- Both surfaces show *"judged under v2"* on a run, and history groups by it.

**May change:** `hotelcontrols/spec/` (loader), `hotelcontrols/runner/run.py` (two fields),
`hotelcontrols/store/`, `hotelcontrols/web/`, `tools/validate_spec.py`, a new lock tool,
`spec/ir.lock.json` (new), `fixtures/api/` (rebuilt), `ui/`, `tests/unit/test_v3_slice_scope.py`
(new, first commit). **Must not:** `kernel/`, `providers/`, `evidence/`, `evaluator/`,
`compiler/`, any `spec/ir/*.json`, any captured fixture.

**Exit test.**
- A stored run names its version and digest. A run re-read from a database written before this slice
  says *"version not recorded"*, asserted against a file database built with the old schema.
- Changing one predicate in a temp-dir copy of an IR without bumping `version` fails
  `validate_spec` naming the control; bumping it passes.
- Two runs of one control under v2 and v3 of its rule are distinguishable in history.

**Nothing breaks — a declared contract change.** Run payloads gain two keys. `fixtures/api/` is
rebuilt; the PR shows that **only those two keys** were added to the 88 run goldens and that no
`verdicts`, `counts` or `coverage` value changed. Every other row of §1 holds.

**Prerequisites:** fix #48 merged. **Assumes:** nothing about persistence. It works in memory and
is tested against a file. **Not:** a version store other than git; lifecycle states (G6c).

---

### Slice 17 · Tenant-scoped store (G5, data half)

**Delivers:** one property can no longer see another property's results, even by asking the API
directly.

**Work.**
- Every `RunStore` read takes the property as a **keyword-only argument with no default**, so a
  call without one is a `TypeError`. It fails loudly rather than returning everything (D3 §80).
  `load(run_id)` for another property's run returns nothing, which is a 404 and not a 403, so a run
  id cannot be probed for existence.
- **A structural test in the style of the canonical-boundary grep:** every SQL statement in
  `store/` that reads, updates or deletes a tenant-owned table carries a tenant predicate, or goes
  through the one helper that adds it. It is seen failing on a planted unscoped `SELECT` before it
  is relied on. It also covers every table v3 adds later, and that is the point of taking it now.
- **Drafts are namespaced per property** (QA Q10, collision A2): two properties composing
  `late_checkout_policy` no longer overwrite each other. Reviewed controls in `spec/ir/` stay a
  shared library *by design*. They are the building, not a flat (D1 §8).

**May change:** `hotelcontrols/store/`, `hotelcontrols/web/`, `tools/dump_api_fixtures.py`,
`fixtures/api/` (history and drafts payloads), `ui/`. **Must not:** `kernel/`, `spec/` (code or
data), `providers/`, `evidence/`, `evaluator/`, `runner/`, `compiler/`.

**Exit test.**
- With runs for two properties in one store, **`GET /api/history/<id>?property=B` returns none of
  A's runs and `GET /api/runs/<A's run id>?property=B` is a 404**. Asserted against the JSON API,
  not the page (D3 §80).
- A `RunStore` call without a property raises.
- The structural test fails on a planted unscoped query, then passes.

**Nothing breaks.** Run and readiness goldens byte-identical. History and drafts goldens may change
only if a fixture mixes properties, and the PR shows exactly which. `?property=` still *selects*
the property; until slice 24 it is a selection, not an identity, and the docs say so.

**Prerequisites:** slice 16. **Not:** authentication, roles, the Organisation level.

---

### Slice 18 · Findings queue — advisory action records (G2(a), G8 queue, G10c)

**Delivers:** a failed control becomes a task someone can see, mark done or dismiss, and running
it again does not create the task twice.

**Work.**
- A new pure module turns a run into action records using the IR's own `action` block — severity
  and audience, carried since slice 1 and never read until now. **No new configuration is invented
  for it.**
- Only a **FAIL** creates a record. **UNKNOWN does not**, because whether UNKNOWNs become a review
  queue is open question 1.1, and this slice must not answer it by accident. EXCLUDED does not.
  **A run that concluded nothing creates nothing.**
- **Idempotency is the record's natural key**: property, control, policy version, record id. Run a
  control five times and there is still one record. A new policy version judges afresh and makes a
  new record, while the old one stays linked to v1. `make_run_id` is untouched (§6.6).
- States: `pending → done | dismissed`, each transition stamped through the injected clock with an
  actor (`operator` until slice 24). A later PASS **annotates** a pending record (*"no longer
  failing as of run X"*). It never closes it, because a person performs actions (D12).
- **The queue states coverage.** An empty queue must not read as *all clear*. Beside it, each
  control's latest run says whether it concluded. This is criterion 8 applied to a new surface.
- `server.py` and `tools/serve.py` take an opt-in `--store PATH`. The default demo stays in memory,
  and **the queue page says so** (*"this queue is lost on restart"*) rather than implying a
  persistence it lacks (brief §8.8).

**May change:** a new `hotelcontrols/actions/`, `hotelcontrols/store/` (an `actions` table, scoped
under slice 17's guard), `hotelcontrols/web/` (queue page, JSON routes, state transitions as
`POST`s that write only our store), `tools/serve.py`, `tools/dump_api_fixtures.py`, `fixtures/api/`
(**new files only**), `ui/`. **Must not:** `kernel/`, `spec/`, `providers/`, `evidence/`,
`evaluator/`, `runner/` (a run does not create actions; the layer above it does), `compiler/`.

**Exit test.**
- `checkout_money_owed` on sandbox2026 creates one pending record per FAIL, severity `high`,
  audience `finance`, straight from its IR. Running it again creates none.

  > **Correction (issue #59, slice 18's PR).** As written this exit test passes with **zero
  > records**: `checkout_money_owed` has no FAIL on any capture (2 PASS at sandbox2026's default
  > instant, 0 FAIL at every instant 2026-07-01..31, an empty population in 2024). It is proven
  > instead, with no fixture edited and no FAIL invented, in three parts: **(a)** on captured
  > evidence, on the only FAIL anywhere in it: `checkout_unrefunded_credit` on `007004348`
  > (−490.75 ILS) creates exactly one pending record, severity `medium`, audience `finance`
  > from its IR, on both providers, and re-running it creates none
  > (`tests/integration/test_findings_queue.py`); **(b)** money owed's 0 FAIL → 0 records,
  > asserted as a fact about the evidence at every July instant; **(c)** money owed's
  > `high`/`finance` mapping, on a **constructed** run labelled as such
  > (`tests/unit/test_actions_records.py`). The same class of finding as #49.
- A control whose run concluded nothing creates no record, and the queue shows that control as
  *"reached no conclusion"*, not as clear.
- No UNKNOWN or EXCLUDED verdict creates a record (property test over every control × capture).
- Records for property A are invisible to property B (slice 17's guard covers the table).

**Nothing breaks.** Every existing golden byte-identical; new routes, new goldens. Criterion 1
untouched.

**Prerequisites:** slices 16 and 17. **Not:** email; UNKNOWN review queues (1.1); writing anywhere
outside our own store.

---

### Slice 19 · Email, opt-in, behind two locks (G8 email)

**Delivers:** the finance team is emailed when a control finds money owed, and nobody is emailed
because a test ran.

**Work.**
- A `Notifier` **protocol** in the engine and an SMTP backend in **`tools/notifiers/`**, outside
  the engine and injected by `tools/serve.py`, exactly as `tools/proposers/` is (D10). `smtplib` is
  standard library, but criterion 11's "exactly one file in the engine imports an outbound client"
  stays true, and both AST guards pass unedited.
- **Two locks** (brief §8.4): the backend refuses unless `HOTELCONTROLS_NOTIFY=1` **and** no test
  runner is loaded. The test that sets the variable is refused anyway.
- Addresses come from the environment per audience, with **no default and never committed** (staff
  addresses are personal data). An audience with no route leaves the record pending, with *"no
  route configured for audience finance"*. It is never silently dropped.
- One email per record per channel, even if dispatch runs twice: the sent marker lives on the
  record, so slice 18's key carries the idempotency.

**May change:** `hotelcontrols/actions/`, `hotelcontrols/store/` (sent marker),
`hotelcontrols/web/` (delivery status), `tools/notifiers/` (new), `tools/serve.py`, `ui/`.
**Must not:** `kernel/`, `spec/`, `providers/`, `evidence/`, `evaluator/`, `runner/`, `compiler/`.

**Exit test.**
- A FAIL emails its IR's audience once, through a recording stub; a second dispatch sends nothing.
- **A run that concluded nothing sends nothing; a blocked run sends nothing to the audience**
  (brief §8.5). Asserted on the all-excluded and the blocked cases by name.
- With `HOTELCONTROLS_NOTIFY=1` set inside pytest, the SMTP backend refuses.
- **No email body contains a guest name, email, phone or card token**, asserted over the rendered
  message for every FAIL in every capture. A record id, the control, the amount *with its
  currency* and a link are what an email carries.

**Nothing breaks.** Goldens byte-identical; `test_stdlib_only.py` and the transport's lock tests
unedited and green.

**Prerequisites:** slice 18. **Not:** SMS, Slack, WhatsApp (D3 §72: email first); retries beyond
leaving a record pending.

---

### Slice 20 · Operational log (G14, narrowed)

**Delivers:** someone running the service can see what ran, for whom, how long it took and what it
cost, without the log ever holding a guest's details or a password.

**Work.** Structured JSON-lines records from the standard `logging` module at three boundaries:
the web request, the run (start, finish, calls, counts, coverage, duration) and action dispatch.
Each carries `tenant_id`, `run_id`, `control_id`, `policy_version` and `provider`. The provider
name crosses as *data*, exactly like `Value.source`. **Timestamps come from the injected clock**,
not from the `LogRecord`'s own wall-clock read, because `kernel/clock.py` is the only module
allowed to read a wall clock.

**May change:** a new `hotelcontrols/ops/`, `hotelcontrols/runner/run.py` (emit only),
`hotelcontrols/web/`, `hotelcontrols/actions/`. **Must not:** `evaluator/` (**purity is asserted;
no `logging` import may appear there**), `kernel/`, `providers/` (anything logged inside an
adapter would name endpoints above the boundary), `evidence/`, `spec/`, `compiler/`.

**Exit test.**
- A full run of every control × capture emits records from which one `run_id` can be traced from
  request to dispatch.
- **No emitted record contains a credential, guest name, email, phone or card token.** Asserted
  over every record emitted by that full run, with fake credentials set in the environment, not by
  review.
- An AST test: `evaluator/` imports no `logging`.

**Nothing breaks.** Goldens byte-identical; the clock-injection test unedited and green.

**Prerequisites:** slice 19 (dispatch exists to log). **Not:** metrics, tracing inside providers,
external log sinks.

---

### Slice 21 · Typed hotel parameters, with "not decided" (G6a, narrowed)

**Delivers:** a hotel's settings — rate codes today, late-checkout times and fees next — are typed,
validated, and able to say *"we haven't decided"* without that being read as *"none"*.

**Why this is an accuracy slice, not a convenience.** Today `[]` means both *"the hotel decided
none"* and *"nobody has asked the hotel"* (`TenantConfig.setting`'s docstring tells you to write an
empty value if the hotel has not decided). In a **scope**, an empty list excludes every record,
which is safe. In an **exception**, it exempts nobody, so every complimentary stay would FAIL. That
would be a confident accusation manufactured from a missing answer. G4's comp exception would have
hit exactly this.

**Work.** A parameter schema in `spec/` (name, type, unit or currency, required, **no defaults**).
Tenant values are validated against it at load. **`null` means *not decided*:** a predicate reading
an undecided parameter is UNKNOWN naming it, using the evaluator's existing "has not supplied" path
with no evaluator change. A wrong type, unit or currency is refused at validation, naming the
parameter. Money parameters are `Money` with their currency.

**May change:** `spec/` (schema, tenant files), `hotelcontrols/spec/`, `tools/validate_spec.py`,
`fixtures/api/` (declared). **Must not:** `evaluator/`, `kernel/`, `providers/`, `evidence/`,
`runner/`, `store/`, `compiler/`.

**Exit test.**
- **Two properties, one IR, different parameters, correctly different verdicts, no second IR file**
  (D1 §74). A test asserts the IR count does not grow with the property count.
- An undecided parameter yields UNKNOWN naming it, in a scope, an exception and an assertion, never
  EXCLUDED, never FAIL.
- A string where a list is required, a bare number where Money is required, and a currency the
  property does not use are each refused by name.

**Nothing breaks — and one change may be declared.** The sandbox has not decided its nominated rate
codes, and nobody can decide them for it (§3.2), so the truthful value is `null`, not `[]`. If that
changes any reason string or count for `required_reservation_fields`, the PR names it as a
deliberate verdict change, shows the golden diff, and **the owner confirms it at slice start**.
Every other control's goldens stay byte-identical.

**Prerequisites:** slice 16. **Not:** a template library that reshapes how IRs are stored; a UI for
editing parameters (G13).

---

### Slice 22 · Guest services: `LATE_CHECKOUT` (G1 narrowed, G3a, G2(a))

**Delivers:** a guest asks to check out at 3 PM, and staff see *approved, 25.00 USD* (or *a person
needs to confirm this, because…*) as a task to carry out.

**Owner decisions it implements** (D12, D15): structured request, no model; decisions `APPROVED`,
`APPROVED_WITH_FEE`, `DENIED`, `STAFF_REVIEW`, `UNAVAILABLE`; parameters `free_until`,
`charge_from`, `maximum_time`, `approval_required_after`, `fee_per_hour` (Money) and
`hour_rounding` (no default).

**The decision rule, translated from this engine's principles:**
- **`STAFF_REVIEW` is guest services' UNKNOWN**, and it always names what was missing: an unnamed
  status (`OK4`, `WL`), an undecided parameter, a departure date that cannot be read.
- **`UNAVAILABLE` and `DENIED` are only ever reached from established evidence or stated policy**,
  never from missing evidence. A decision that cannot be justified line by line is `STAFF_REVIEW`.
- The fee is `Money`: `fee_per_hour` times the hotel's stated rounding of the hours past
  `charge_from`. That is repeated `Money.plus`, so the kernel is unchanged. A bare `25` fails the
  test.
- Every decision is stored (tenant-scoped, versioned) and, unless `DENIED`, produces an advisory
  action record through slice 18.
- **The decision table is written as a spec file and approved by the owner before any code** — a
  slice-start checkpoint, because it is where policy turns into behaviour. Example: is a request
  for a reservation not departing today `DENIED` or `STAFF_REVIEW`?

**May change:** a new `hotelcontrols/guest/` (request, policy, decision, fee; pure),
`spec/guest/` (the template and its decision table), `spec/tenants/` (parameters; the sandbox's are
`null`, undecided), `hotelcontrols/store/` (`decisions`, scoped), `hotelcontrols/actions/`,
`hotelcontrols/web/` (`POST /api/guest/requests` and a staff view), `fixtures/api/` (new files only),
`ui/`. **Must not:** `kernel/`, `providers/`, `evidence/`, `evaluator/` (its predicates are
*reused* by import, not changed), `runner/`, `compiler/`, any `spec/ir/*.json`.

**Exit test — D2 §49's Definition of Done, made executable.**
- Policy *free until 14:00, 25.00 USD per started hour from 14:00, approval after 16:00*. A
  checked-in guest departing today asks for 15:00 → **`APPROVED_WITH_FEE`, `25.00 USD` as Money**.
- **Both thresholds, both sides:** 14:00, 14:01, 16:00, 16:01.
- The **other** worked example in the source documents (*up to 3 PM, charged after noon*, D2 §1) is
  a second property's parameters, with its own expected answers (§6 contradiction #3, dissolved
  rather than ruled).
- A request on an `OK4` reservation, or with an undecided parameter, is **`STAFF_REVIEW` naming
  why**. The sandbox, whose policy is undecided, answers `STAFF_REVIEW` for every request, and says
  so.
- **The same request produces the same decision through both providers** (criterion 7, applied to
  a decision).
- **The same request submitted twice produces one decision and one action** (D1 §65: a double tap
  is Tuesday, not an edge case).
- **No model is reachable from `hotelcontrols/guest/`**, asserted over the AST like the compiler's
  network guard.

**Nothing breaks.** Every existing golden byte-identical; new routes, new goldens. Criterion 1 is
not affected, because a guest template is not a control.

**Prerequisites:** slices 18 and 21. **Not:** the other four templates; prose intake; posting the
fee anywhere (G2(b) is rejected); a guest-facing screen (staff see decisions; how a guest is
answered is the host product's).

---

### Slice 23 · Evidence refresh — an owner-approved probe

**Delivers:** the facts four controls rest on are re-checked against the live sandbox instead of a
2024 snapshot, and control 15 gets the rate codes it has never had.

**The first step is the owner's, and nothing happens without it.** `python3 -m tools.probe --plan`
prints each request body with placeholders where the credentials go. The owner approves **each
call** (D3, R8):
`getRooms`, `getRoomTypes`, `RoomStatusInquiry` (question 1.2), and one reservation call over the
existing 2026 window **with room prices**, so rate codes are present (#49). **If approval never
comes, this slice is skipped and nothing else depends on it.**

**Work.** Run the approved calls once, in record mode; scrub with `tools/scrub_fixtures.py` before
anything is staged; add them as a **new capture label**, never editing an existing file; rebuild
DemoPMS from them; restate each of the four 2024 findings as *still true*, *changed* or *gone*,
naming the capture.

**May change:** `fixtures/minihotel/` (**new files and `index.json` only**), `fixtures/demopms/`
(regenerated, new files), `fixtures/api/` (new capture's goldens: **new files only**),
`spec/providers/*.json` (`verified_against` dates), docs. **Must not:** `hotelcontrols/` at all. If
a new capture shows a defect, the defect gets a GitHub issue and its own `fix/` branch.

**Exit test.**
- Every existing capture and golden byte-identical; the new capture's index entry records date and
  call count.
- **Criterion 1 re-measured on the new capture and reported per capture**, never replacing the old
  figure silently, never rounded.
- Each of the four findings in 1.2 carries a dated verdict.

**Prerequisites:** owner approval per call; the four credentials in the environment. **Not:** a
standing permission; any write; any window wider than the printed plan.

---

### Slice 24 · Authentication at the host, credentials per property (G5 auth half, G11 narrowed, #22)

**Delivers:** a logged-in user of hotel A cannot see hotel B's anything, and two hotels on the same
PMS can each hold their own credentials.

**Owner decision it implements** (D14): **the host product authenticates; the engine verifies.**
The Next.js layer logs a user in and sends the engine a short-lived **tenant context signed with
HMAC-SHA256**. The engine verifies it with `hmac.compare_digest`, checks expiry **through the
injected clock**, and stores no passwords. Standard library only, so D2 holds. The shared secret
comes from the environment with no default.

**Work.**
- Auth mode is switched on by the secret's presence. When it is on, `?property=` **no longer
  selects a property**: the verified context does, and an unsigned, forged or expired context is
  refused. When it is off, the engine is today's single-operator demo exactly, which is what keeps
  every golden and the audit surface unchanged.
- `ui/` signs with `node:crypto`, so **no new runtime package** is needed (the exact-pins test stays
  unedited). Its user store is a development stand-in, labelled as one. The production host's user
  store is the host's.
- **#22:** `Credentials.from_environment(provider, property)` →
  `HOTELCONTROLS_<PROPERTY>_<PROVIDER>_*`. `tools/probe.py` passes the property it already has and
  stops discarding it.

**May change:** `hotelcontrols/web/` (a new `auth.py`), `hotelcontrols/providers/transport/http.py`
(the credential key only; no wire format, no PMS name), `tools/probe.py`, `ui/`, docs.
**Must not:** `kernel/`, `spec/`, `evidence/`, `evaluator/`, `runner/`, `store/` (already scoped
by slice 17), `compiler/`, the adapters.

**Exit test — D3 §80's mandatory tests, against the API, not the UI.**
- With auth on, **A's signed context cannot read B's runs, actions, decisions or drafts** through
  any JSON route.
- Unsigned, wrongly signed and expired contexts are each refused; the engine refuses to start in
  auth mode with no secret.
- **Two properties on the same PMS resolve distinct credentials** (#22's failing test, written
  first).
- With auth off, all 120 goldens are byte-identical.

**Prerequisites:** slice 17 (and every slice whose tables it protects). **Not:** roles beyond the
one context; the Organisation→Hotel hierarchy (D1 §48 defers it); encrypted credential storage
(D14 defers it with onboarding); an engine login page.

---

## 6. The brief's eight concerns, answered

| # | Concern | Resolution |
| --- | --- | --- |
| 1 | Encryption with a stdlib-only engine | **Owner decided (D14): no encryption in v3.** Credentials stay in the environment, keyed per property (slice 24). Encrypted at-rest storage returns with onboarding (G11), and if built, its dependency lives **outside `hotelcontrols/`**, in the host, as `tools/proposers/` does. D2 is not reversed |
| 2 | Authentication without dependencies | **Owner decided (D14): the host authenticates, the engine verifies an HMAC-signed context** (stdlib `hmac`). No password hashing or sessions in the engine (slice 24) |
| 3 | A scheduler and the single-threaded store | **G10a deferred** (§4). When it returns it is a **separate process with its own connection to a file store**, never `check_same_thread=False`, which would turn an exception into a data race. Recorded so the next planner does not rediscover it |
| 4 | Email is outbound network | Backend in `tools/notifiers/`, injected; **two locks**, the variable **and** a refusal under a test runner (slice 19) |
| 5 | A run that concluded nothing notifies nothing | Slice 18 creates no record from it; slice 19 sends nothing for it. Both are exit tests, named |
| 6 | Idempotency changes `run_id` | **It doesn't.** `make_run_id` is untouched; idempotency is the action record's natural key (slice 18). A repeated run is honest history; a duplicate *notification* is what D1 §65 forbids, and that is what is prevented. Job-level keys come with G10a |
| 7 | Parameters must not fork verdicts | Slice 21's exit test: two properties, one IR, different verdicts, and every other golden byte-identical |
| 8 | The demo's store is in memory | Slices 16, 17, 21 and 24 assume nothing and are tested against a file database too. Slices 18, 19 and 22 add an opt-in `--store PATH`; the default stays in memory **and says so on the queue page** |

---

## 7. v3 success criteria

Numbered **V1–V12** so they cannot be confused with `prd.md` §7's twelve, which all still apply,
including criterion 1 recorded as NOT MET. Each is a test, an observable behaviour or a number.

| # | Criterion | How it is proven |
| --- | --- | --- |
| V1 | **No v2 answer changes** unless a slice declares it: at the end of v3, the verdicts, counts and coverage inside all 88 run goldens equal those at `7f384c4`, apart from changes named in a PR (only slice 21's possible control-15 change is foreseen) | A comparison script over `fixtures/api/` against `7f384c4`, run in every slice PR |
| V2 | **The regression wall holds**: 0 failures; spec checks pass; coverage ≥ 96%; DemoPMS rebuild identical; the two-provider e2e unchanged | CI, per slice |
| V3 | **Every stored result names the policy version that produced it**, and a pre-v3 row says "not recorded" rather than claiming the current one; a rule edited without a version bump fails `validate_spec` | Slice 16 tests |
| V4 | **No query on a tenant-owned table lacks a tenant predicate**, and one property cannot read another's runs, actions, decisions or drafts **through the JSON API** | Structural test (slice 17); D3 §80 API tests (slices 17, 24) |
| V5 | **A FAIL creates exactly one pending action record however often it is re-run; a run that concluded nothing, an UNKNOWN and an EXCLUDED create none**; an empty queue never reads as "all clear" | Slice 18 tests |
| V6 | **No test can send email; one email per record; none for a run that concluded nothing; none containing guest PII** | Slice 19 tests, including the lock test with the variable set |
| V7 | **No log record contains a credential or guest PII**, and the evaluator imports no logging | Slice 20, over every record of a full run |
| V8 | **An undecided hotel parameter is UNKNOWN naming it, never "none"**; two properties with one IR get different verdicts with no second IR file | Slice 21 tests |
| V9 | **D2 §49's late-checkout Definition of Done holds**: 15:00 → `APPROVED_WITH_FEE`, `25.00 USD` as Money; both sides of both thresholds; the same decision through both providers; one decision for a double submission | Slice 22 tests |
| V10 | **Guest services never widens a decision**: blanking any single piece of evidence or any parameter yields `STAFF_REVIEW` naming it, never `APPROVED`, `DENIED` or `UNAVAILABLE`; no model is reachable | Slice 22: a test per evidence field; an AST guard |
| V11 | **With auth on, identity comes from a verified signature, never from the URL**; forged, unsigned and expired contexts are refused; two properties on one PMS hold distinct credentials | Slice 24 tests |
| V12 | **The engine is still read-only, still stdlib-only, still offline in tests**: one outbound-client file in `hotelcontrols/`, no PMS write mapped, both AST guards unedited | Existing tests, unedited, green at every merge |

### Anti-criteria — v3 failed if any of these happens, whatever else passes

- A control, a queue or a guest decision reaches PASS, `APPROVED` or "all clear" from evidence or a
  parameter that was not established. **The card-on-file control in §3.1 is the worked example.**
- A missing hotel decision is read as "none".
- Somebody is emailed because a test ran, or about a run that concluded nothing.
- One property sees another's data through any route.
- A fixture is edited, or a policy is invented for the sandbox, to move a number.

---

## 8. What v3 deliberately does not do

Named so nobody mistakes it for unfinished: **Mews** (owner, and no credentials); **writing to a
PMS**, ever (G2(b)); **a scheduler daemon** and **webhooks** (live-evidence and vendor
prerequisites, §4); **G4** (#48 and 2.8); **room upgrades**, **availability**, **VIP status** and
**company ids** (no evidence); **four of five guest templates**; **prose intake for guest
requests**; **free text as evidence** (1.5); **a model anywhere near a verdict or a decision**
(D10); **roles, the Organisation level and encrypted credential storage** (D14); **a lifecycle and
the management API's write half** (G6c, G13).

Open questions that stay open, and what v3 does meanwhile: **1.1** (UNKNOWN queues — slice 18
creates none), **1.4** (rate codes — needs a real property *and* slice 23's capture), **1.5** (free
text — nothing reads it), **2.1** (`OK4`/`WL` — still UNKNOWN), **2.6** (agreed limits — gates
G10a), **2.8** (the card placeholder — gates G4), and the manager's question: **is the
five-control list a requirement or an illustration?** v3 is unaffected either way, since G4 is
blocked and nothing is removed.
