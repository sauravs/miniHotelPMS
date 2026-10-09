# v3 planner brief — choose, sequence and plan the next phase

**This file is the starter prompt for the next session.** Paste it, or point the agent at it.
Written 2026-10-09 on `main` after PR #46, by the session that built slice 15 and fixed #44.
**Delete it once the v3 plan it asks for is merged** — the same lifecycle as the slice-15 brief.

---

## 0. Who you are this session, and the one rule that governs it

**You are an expert planner first, and you write no code this session.** Your job is to read the
gap analysis, decide which gaps this codebase can take on **without damaging what already works**,
sequence them as vertical slices, write the plan, ask the owner what only the owner can answer —
and then **stop and wait for approval**. Implementation starts in a later session, slice by slice.

The owner's request, in substance:

> Analyse `docs/stayops-gap-analysis.md` thoroughly. Of all the gaps it lists that are not yet
> implemented, decide which we **can** implement — **not all of them**. The most important thing is
> the product's **accuracy**, and that **it must not break**. If a gap is not achievable, or could
> reverse or damage the core architecture, do not take it. Mews is **out**. Sequence what remains as
> vertical slices, write the updated plan and whichever docs need it, and **ask rather than guess**.

So the governing sentence of this session:

> **A gap earns a place in v3 only if it can be built without widening a verdict, without crossing
> the canonical boundary, and without changing a single answer the engine gives today — or, where
> it must change one, the change is deliberate, named, and shown in a reviewed diff.**

`CLAUDE.md`'s rule still outranks everything here: **never widen a verdict.** If evidence is
missing the answer is UNKNOWN. A plan that ships a feature by guessing is a failed plan.

---

## 1. Start-up procedure — before reading anything else

```bash
git status && git branch --no-merged main      # anything listed: resolve it, never leave it
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q            # expect 1996 passed, 2 skipped
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec  # expect PASSED - all 1080 checks
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.dump_api_fixtures --check   # expect 120 identical
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.transcode_demopms --check   # expect 11 identical
.venv/bin/python -m coverage run -m pytest && .venv/bin/python -m coverage report  # expect 96%
```

Write those five numbers down. They are the regression wall every v3 slice must keep, and the plan
you write must quote them. If any differs from the expected value, stop and find out why before
planning anything — a plan built on a red baseline inherits a defect it cannot see.

---

## 2. Read, in this order

| # | Document | Why |
| --- | --- | --- |
| 1 | `CLAUDE.md` | The four ideas, the seven API facts, the conventions, the rules. Non-optional |
| 2 | **`docs/stayops-gap-analysis.md` — all of it** | **Your primary input.** 15 gaps (G1–G15) with sub-rows, each scored `Impact × max(blast radius, evidence risk)`; §5 where we are deliberately ahead; §6 the nine contradictions inside the source documents; §7 a proposed roadmap (Phases A–J) |
| 3 | `docs/open-questions.md` — §0 decisions D1–D11, then **1.1, 1.4, 1.5, 1.9, 1.10, 1.11, 1.12**, then §3 engineering gaps | What is decided, what is open, and what was deliberately not built and why |
| 4 | `docs/prd.md` — §4, §6, §7 | The v2 contract and its twelve criteria. Any v3 criterion you write must be as falsifiable as these |
| 5 | `docs/architecture.md` — §1, §3, §5, §6 | The eight layers, what each hides, how they are tested, what is out of scope |
| 6 | `docs/plan.md` — "Method", "Definition of done", "Where this leaves the build", Slice 15 | How a slice is written here: test gate first, exit test stated before the code |
| 7 | `docs/context.md` — decisions and "what slice 13/15 did not change" | The project's habit of recording what an addition did *not* touch |
| 8 | `docs/QA.md` Q8–Q10 | The owner's own questions about multi-tenancy — directly relevant to G5/G11 |
| 9 | `docs/stayOps_Cotrols_Rule_Engine_V2.md` | The business-language account of what the StayOps documents ask for. Read if a gap's purpose is unclear |
| 10 | `docs/poc-comparison-brief.md` and `ruleEngineAnishLegacy/` | **Optional prior art.** A second implementation of the same requirements — guest services, templates, tenants — on **mock data with zero tests**. Harvest *shapes*, never its evidence layer or its assumptions. The comparison report that brief describes was never written |

---

## 3. The gap report is 18 commits old — re-verify every "what exists" claim

`stayops-gap-analysis.md` was measured on `5d5143c` (2026-09-28). Since then: slice 14 (the
server-rendered surface explains itself), slice 15 (a React UI in `ui/`, PRs #34–#40), #42
(`/api/plan`), and fixes #35 and #44. Known consequences — **verify, do not assume**:

| The report says | Now |
| --- | --- |
| 1610 tests, 9,732 engine lines | 1996 tests, ~10,400 lines. Use the numbers you measured in §1 |
| G13: "no create-control UI"; API is read-only plus `POST /compose` | Still no create / validate / activate / pause. But both surfaces now exist, compose has JSON routes (`/api/compose`, `/api/compose/accept`), and read-only `/api/controls`, `/properties`, `/history`, `/drafts`, `/outcomes`, `/plan` exist |
| G13: "any dashboard needs a fifth tile and a coverage headline" | **Already true on both surfaces** — EXCLUDED is its own tile and a run that concluded nothing shows no tiles |
| §6 contradiction #8 (money as a bare float) | Our engine already does what D3 says; nothing to build |
| G2 / question 1.10 — advisory or acting? | **DECIDED 2026-10-09: advisory** (see §4) |
| Every other gap | **Unchanged as far as is known.** Prove it with a grep or a run before you write "absent" in the plan |

The report is honest about its own limits (§9 of it): effort scores are relative, UNVERIFIED rows
are marked, and four evidence facts rest on a 2024 capture. Carry those caveats into your plan
rather than laundering them into confident rows.

---

## 4. Decisions already made — do not re-litigate

- **Mews (G9) is out of v3.** Owner's decision. It is also blocked on credentials nobody has.
- **Guest services is ADVISORY (G2(a)), decided 2026-10-09.** The engine never writes to a PMS;
  `prd.md` §6's read-only rule stands. Every action is a **record with a state** (`pending`,
  `done`, `dismissed`) that a person performs. **G2(b) — acting — is rejected**, and so is every
  action type that writes into a hotel system (`CREATE_SERVICE_REQUEST` and
  `CREATE_MAINTENANCE_REQUEST` exist only as records a human completes). Recorded in
  `open-questions.md` 1.10.
- **D1–D11** in `open-questions.md` §0: stdlib-only engine (D2), live API calls approved
  individually (D3), DemoPMS as second provider (D4), never LLM → executable (D5, D10: a model may
  draft a *sentence*, never a rule), pseudonymised fixtures (D6), slice-per-PR git workflow (D7),
  control 6 split in two (D8), two surfaces with the engine untouched (D11).
- **The guest-services translation of UNKNOWN is `STAFF_REVIEW`** (gap report G1). A guest must get
  an answer; *"a person will confirm this"* is the honest one when evidence is missing. Never a
  default approval, never a guess.

---

## 5. Deliverable 1 — the gap disposition table

Every gap and sub-row in the report (G1, G2(a), G2(b), G3a–d, G4 as specified, G4 narrowed, G5,
G6a–c, G7, G8, G9, G10a–d, G11, G12a–d, G13, G14, G15) gets exactly one disposition:

| Disposition | Meaning | Must state |
| --- | --- | --- |
| **TAKE** | In v3, assigned to a slice | Which slice, and its exit test |
| **TAKE, NARROWED** | In v3, but only the part evidence can honestly support | What was cut and why — the G4 narrowing in the report is the model |
| **DEFER** | Sound, but not now | The trigger that would bring it back |
| **BLOCKED** | Cannot be built honestly today | The missing evidence or the missing decision, **by name** |
| **REJECT** | Would damage accuracy or the architecture | Which invariant it breaks |

**Apply these five filters in order. A gap that fails one does not reach the next.**

1. **Accuracy.** Could it produce a verdict or a decision from evidence that was not established, or
   turn an UNKNOWN into anything else? → REJECT, or narrow until it cannot.
2. **Architecture.** Does it cross the canonical boundary, write to a PMS, put a model in the verdict
   path, add a runtime dependency to `hotelcontrols/`, or need the run store shared across threads?
   → REJECT, or redesign so it does not. (See §8 for the ones that are genuinely hard.)
3. **Evidence.** Evidence risk 5 — no captured response can support it — → BLOCKED unless narrowed.
4. **Decision.** Does it depend on a question still open (1.11 #1/#2/#9, 1.12, 1.1, 1.5)? → put the
   question to the owner **before** you include it. Never resolve a contradiction in the source
   documents silently.
5. **Value against effort.** Only now does exposure, impact and effort decide order.

The report already pre-classifies some rows. **Confirm each with your own reasoning; do not copy:**
G7 (no action recommended), G9 (out — owner), G2(b) (rejected — owner), G12c (not buildable),
G12b (`vip_status` from Hebrew free text — turns on 1.5 and is the most dangerous item in the
report; the default is BLOCKED), G12d (revisit when a provider renumbers), G10b (defer below a few
hundred properties), G3d `ROOM_UPGRADE` (an evidence investigation before it is code).

---

## 6. Deliverable 2 — the v3 plan, as vertical slices

**Numbering.** v1 is `miniHotelLegacy/`. `docs/plan.md` is the *v2 build*, slices 0–15. **This is
v3, and its slices continue at 16** so branch names stay `slice/NN-name`. The gap report labels its
own roadmap *Phase A–J*; do not let "Phase C" and "v3" blur — cite the report's phases by letter
only when explaining where an idea came from.

**What a slice is here** (read `docs/plan.md` → "Method"): one thin piece that works **end to end**
— spec, engine, API, and both screens where the feature is visible — with its **test gate and exit
test written before the code**, its own branch, PR, green CI, squash-merge. Not a layer at a time.
Each slice must be releasable on its own: if v3 stopped after any slice, nothing would be broken
or half-wired.

**Each slice in the plan must state:**

- what it delivers, in one sentence a hotel manager would understand;
- **which packages it may change and which it must not** — slice 15's
  `tests/unit/test_slice15_engine_untouched.py` is the pattern; propose an equivalent guard where the
  blast radius warrants one;
- the exit test, adapted from the report's where one exists, and falsifiable;
- the "nothing breaks" proof: the regression wall from §1 unchanged, **the 120 golden payloads
  byte-identical unless the slice declares a contract change** (then rebuild and review the diff in
  the PR), the two-provider e2e test unchanged, and the criterion-1 figure re-measured — never
  rounded — if a control is added;
- its prerequisites (a decision, an earlier slice, evidence);
- what it deliberately does **not** do.

**A starting view, offered as input to your judgement, not as the answer.** The report's own
sequence (A → B → C → D → E → F → G → H → I, with J dropped) is reasoned in its §7.2. Among the
cheapest, safest, highest-value candidates it identifies: **G4 narrowed** (a `spec/` change — the
twelfth control, card-on-file before arrival, UNKNOWN wherever the hotel's real guarantee policy is
what matters); **G6b policy versioning** (identity for "which version judged this"); **G10c
idempotency** (must precede any notification); **G8 advisory notifications** and **G14
observability**. G6a (templates with parameters) is the spine guest services would inherit, but it
reshapes how controls are stored, so its slice must prove every existing verdict unchanged. G5
(multi-tenant isolation) is the largest structural item and the report puts it after the policy
spine; contradiction #9 in §6 is exactly about that order, and it is the owner's call. Decide, and
**say why** in the plan.

---

## 7. Deliverable 3 — the docs, and you decide which

At minimum: a **v3 plan document** (recommended `docs/plan-v3.md`, since `docs/plan.md` is the
v2 build log and already 800 lines — link it from `plan.md`'s end and from `CLAUDE.md`'s status
table) containing the disposition table, the slice sequence, and v3's own **falsifiable success
criteria** in the style of `prd.md` §7.

Then decide, and justify in the PR, which of these also need updating — do not update one without
a reason you can state:

- `docs/prd.md` — v3's scope and criteria, or a pointer to them;
- `docs/open-questions.md` — every new question you raise, every decision the owner makes during
  this session (in the decided-with-reasons form, with the rejected alternative);
- `docs/architecture.md` — only if a slice adds a layer or a new interface;
- `docs/context.md` — the timeline entry and any decision;
- `CLAUDE.md` — the status table;
- `docs/session-handoff.md` — so the session after yours starts from the plan.

Leave the dated records alone: the gap analysis itself, `QA.md` (append-only), the v1 review, the
StayOps business explainer.

---

## 8. Concerns the plan must answer, not skip

These are where "take the gap" collides with an existing invariant. Each needs a stated resolution
or an owner question — never a silent workaround.

1. **Encryption with a standard-library-only engine (G11).** The report asks for *encrypted*
   per-tenant credentials. Python's standard library has hashing, HMAC and `secrets` — and **no
   symmetric encryption**. Rolling our own cipher is out of the question. The options (a runtime
   dependency in the engine, which reverses D2; a dependency confined outside `hotelcontrols/` as
   `tools/proposers/` does; or delegating secrets to the environment or the OS keychain) are an
   owner decision. Ask.
2. **Authentication without dependencies (G5).** Same constraint, for sessions and password
   hashing. `hashlib.scrypt` and `hmac` exist; a full auth stack does not. The React UI is a
   separate process with its own dependency budget. Decide where authentication lives and ask.
3. **A scheduler and the single-threaded store (G10a).** `server.py` is serial on purpose, and the
   SQLite store must not be shared across threads (`check_same_thread=False` would turn an
   exception into a data race — see the comment in `hotelcontrols/web/server.py` and
   `open-questions.md` §3). A daemon is a second process or it is a redesign of the store, and the
   latter is core logic.
4. **Email is outbound network (G8).** `smtplib` is standard library, but no test may touch the
   network. It needs the same two locks the PMS transport and the model proposers have: an
   environment variable **and** a refusal to arm while a test runner is loaded.
5. **A run that concluded nothing must notify nothing (G8).** The report's Phase G exit test says
   so; it is the coverage verdict applied to alerts.
6. **Idempotency changes `run_id` (G10c).** `make_run_id` hashes `created_at`. Changing it changes
   every stored run's identity and every golden that carries one. That is a declared contract
   change, not an incidental one.
7. **Parameters must not fork verdicts (G6a).** "Two tenants, one template, different parameters,
   correctly different verdicts, no second IR file" — and every one of today's verdicts identical.
8. **The demo's store is in memory.** Versioning, history and multi-tenancy all assume persistence
   that the default `RunStore(":memory:")` does not give. State what each slice assumes.

---

## 9. Questions you must put to the owner — with `AskUserQuestion`, not by guessing

Known to be open; add any you find. Recommend an answer for each, and say what changes in the plan
under each answer.

- **1.11 #1** — the guest decision set and its spelling (`STAFF_REVIEW` vs `NEEDS_STAFF_REVIEW`; four
  outcomes or five). Only if guest services is in v3.
- **1.11 #2** — `LATE_CHECKOUT`'s parameter names (four different sets in the source documents).
  Only if guest services is in v3.
- **1.11 #9** — build order: multi-tenancy before or after the policy spine.
- **1.12** — do EXCLUDED and the coverage verdict become part of the StayOps specification?
- **Is guest services (G1/G3) in v3 at all?** It is XL, and half the source documents' Definition of
  Done. Taking only `LATE_CHECKOUT` (G3a) is the report's recommended vertical slice.
- **The encryption and authentication constraints in §8.1–8.2.**
- **The manager's question in the report's §8** — is the five-control list a requirement or an
  illustration? (Affects whether G4 is "the missing fifth" or "the twelfth".)
- Standing, cheap, and still unanswered: **1.4** (nominated rate codes), **1.2** (the three-call
  sandbox probe, planned and waiting on one word), **2.1** (what `OK4` and `WL` mean).

Ask in **one batch** where you can. Do not ask what the codebase or the gap report already
answers; do not ask what §4 has decided.

---

## 10. Definition of done for THIS session

- [ ] Start-up procedure run; the five baseline numbers recorded in the plan.
- [ ] Every gap and sub-row has a disposition with its reason; Mews is OUT; G2(b) is REJECTED.
- [ ] Every "absent" or "partial" claim re-verified against `main` by a grep or a run.
- [ ] The v3 slice sequence (16+) with, per slice: delivery, allowed and forbidden packages, test
      gate, exit test, prerequisites, non-goals, and the "nothing breaks" proof.
- [ ] v3 success criteria, each falsifiable.
- [ ] §8's concerns each answered or turned into an owner question.
- [ ] Owner questions asked, answers recorded in `open-questions.md` in decided-with-reasons form.
- [ ] Docs updated where justified; dated records untouched.
- [ ] **One docs-only PR** (branch `docs/v3-plan`), CI green, merged with the owner's approval.
- [ ] **Then stop.** No `slice/16-*` branch, no code, until the owner approves the plan.
- [ ] Delete this brief in that PR, or in the first slice PR, as the owner prefers.

---

## 11. How to work — unchanged from v2

- **Never widen a verdict.** This outranks everything above.
- TDD with gates: failing test first, written from the specification, every test naming the
  criterion, IR clause or risk id it protects. `PYTHONDONTWRITEBYTECODE=1` — a correctness gate.
- `spec/` is data; `fixtures/` are evidence and are never edited to make a test pass;
  `fixtures/demopms/` and `fixtures/api/` are generated.
- No live MiniHotel call without the owner's approval of that specific call (D3, R8).
- No credentials in source, ever. No third-party personal data in a committed file.
- Git: `slice/NN-name` or `fix/NN-desc` → PR → CI (`test (3.11)`, `test (3.13)` required; `ui`
  separate) → squash-merge. A bug found outside the current slice gets a GitHub issue **first**.
  Commit and push only when the owner asks.
- High comment density that explains *why* and cites the risk id.
