# v3 implementation brief — build slices 16–24

**This file is the starter prompt for the implementation sessions.** Paste it, or point the agent
at it. Written 2026-10-09 on `main` at `6f77b80`, right after the v3 plan (PR #50) was **approved
by the project owner and merged**. Delete it in the PR that closes v3, the same lifecycle as the
slice-15 and v3-planner briefs.

---

## 0. Who you are, and the rule that governs every line you write

**You are the implementer.** The planning is done and approved. `docs/plan-v3.md` is the
specification: for each slice it says what to deliver, which paths may and must not change, the
test gate, the exit test, the prerequisites and the non-goals. **Do not re-plan it, re-order it, or
widen a slice.** If a slice turns out to need something its "must not change" line forbids, stop
and ask. Do not quietly edit the guard.

> **A gap earns a place in v3 only if it can be built without widening a verdict, without crossing
> the canonical boundary, and without changing a single answer the engine gives today — or, where
> it must change one, the change is deliberate, named, and shown in a reviewed diff.**

`CLAUDE.md` outranks this file: **never widen a verdict.** Missing evidence is UNKNOWN; for guest
services it is `STAFF_REVIEW`. The planning session found the reason this matters for v3: the
control everyone thought was cheapest would have passed every reservation, on a placeholder
(`docs/plan-v3.md` §3.1, issue #48).

---

## 1. Start-up procedure — every session, before anything else

```bash
git status && git branch --no-merged main       # LOCAL list must be empty: resolve anything listed
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -o addopts=""           # 1996 passed, 2 skipped
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec               # PASSED - all 1080 checks
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.dump_api_fixtures --check   # checked 120 file(s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.transcode_demopms --check   # checked 11 file(s)
.venv/bin/python -m coverage run -m pytest && .venv/bin/python -m coverage report   # TOTAL 96%
gh issue list --state open                        # #48 and #22 are expected; anything new, read it
```

Those are the baseline numbers on `6f77b80`. **Later slices raise the test count; that is fine.
Any failure, any golden mismatch or any coverage drop is not.** If a number differs from the
latest value recorded in the `docs/plan-v3.md` status table, stop and find out why before writing
code. A slice built on a red baseline inherits a defect it cannot see.

Two notes from the planning session, so they don't cost you time:

- `pytest -q` prints dots and no summary line in this repo (configured via `pyproject.toml`
  addopts). Use `-o addopts=""` to see `N passed, M skipped`.
- `git branch -r --no-merged main` lists about a dozen remote branches. They are squash-merge
  leftovers whose PRs are all merged, which is expected. Only the **local** list must be empty.

---

## 2. Read, in this order

| # | Document | Why |
| --- | --- | --- |
| 1 | `CLAUDE.md` | The four ideas, the seven API facts, conventions, rules. Non-optional |
| 2 | **`docs/plan-v3.md` — all of it** | **Your specification.** §1 the regression wall, §3 the two findings, §4 why each gap is in or out, **§5 the slices**, §6 the eight concerns already answered, §7 criteria V1–V12 |
| 3 | `docs/plan.md` → "Method", "Bug workflow", "Definition of done" | How a slice is run here, and how criterion 1 is kept honest |
| 4 | `docs/open-questions.md` → §0 **D12–D16**, then 1.1, 1.4, 1.11, 1.12, §2 question 8 | What the owner decided for v3, with what each decision rejected |
| 5 | `docs/architecture.md` §1, §3, §5 | The layers you are adding beside. Update it **in the PR that builds an interface**, for what was built |
| 6 | `tests/unit/test_slice15_engine_untouched.py` | The guard pattern slice 16 generalises. Copy its mechanics: compare against the merge base including the working tree, fail rather than skip when `origin/main` is missing |
| 7 | `docs/context.md` → "What slice 15 did not change" | Every v3 PR states, in the same spirit, what it did not touch |

---

## 3. The order of work

| Step | Branch | Owner checkpoint before it starts |
| --- | --- | --- |
| Fix #48 | `fix/48-card-presence-not-established` | none |
| Slice 16 — policy versioning | `slice/16-policy-versioning` | none |
| Slice 17 — tenant-scoped store | `slice/17-tenant-scoped-store` | none |
| Slice 18 — findings queue | `slice/18-findings-queue` | none |
| Slice 19 — email, two locks | `slice/19-email-notifier` | none |
| Slice 20 — operational log | `slice/20-operational-log` | none |
| Slice 21 — typed parameters | `slice/21-typed-parameters` | **Yes:** show the owner the declared change. The sandbox's `nominated_rate_codes` goes from `[]` to `null` (*not decided*). Show its effect on `required_reservation_fields` from a dry run, and get a yes |
| Slice 22 — `LATE_CHECKOUT` | `slice/22-late-checkout` | **Yes:** write the decision table as a spec file first, and get it approved before any code. Example open point: a request on a reservation not departing today, `DENIED` or `STAFF_REVIEW`? |
| Slice 23 — evidence refresh | `slice/23-evidence-refresh` | **Yes, per call:** print each request with `tools.probe --plan`, and the owner approves *each one at the time*. **No approval, no call; skip the slice.** Nothing else depends on it |
| Slice 24 — host auth + per-property credentials | `slice/24-host-auth` | **Brief check:** confirm the development login in `ui/` is acceptable as a labelled stand-in |

**The order is fixed** (D13, and the prerequisites in §5 of the plan), with one exception: slice
23 may move earlier if the owner says so.

**Merging.** As in v2: once a slice's exit tests pass and CI is green on `test (3.11)` and
`test (3.13)`, squash-merge it yourself, delete the local branch, **report to the owner after each
merge**, and open the next. Ask only at the checkpoints above, or when a decision is genuinely the
owner's. *(If the owner prefers to review each PR before merge, they will say so. Then open the PR
and wait.)*

---

## 4. The loop, for every slice

1. **Branch** from fresh `main`. Run §1. Add a row in progress to the `docs/plan-v3.md` status
   table.
2. **Slice 16 only, first commit:** `tests/unit/test_v3_slice_scope.py`, the generalised slice-15
   guard. It holds a table of permitted path prefixes per slice number, copied from each slice's
   **may change** line in plan-v3 §5, and runs on any `slice/1[6-9]-*` or `slice/2[0-4]-*` branch.
   **Show it failing on a planted edit** (for example, touch `hotelcontrols/kernel/` on the branch)
   before relying on it, then remove the plant. Test the rule itself on every branch, as slice
   15's `TestTheGuardRule` does, so it cannot rot into a test that always passes.
3. **Failing tests first, written from the plan's exit test**, not from the code you intend to
   write. Every test names what it protects: a V-criterion, a D-decision, a risk id, an IR clause.
   **`PYTHONDONTWRITEBYTECODE=1`** when proving a test fails without its fix.
4. **Smallest implementation that passes.** High comment density that explains *why* and cites
   the risk id. Match the surrounding code's idiom.
5. **Run the whole wall (§1).** If `dump_api_fixtures --check` fails:
   - **not declared by the slice** → you changed an answer. Stop and find out why.
   - **declared** (slice 16 adds two keys to run payloads; others add **new files only**) → rebuild,
     then prove the diff touches only what was declared. For V1, compare `verdicts`, `counts` and
     `coverage` in every run golden against `7f384c4`, and put the script and its output in the PR.
6. **Re-measure criterion 1** if a control or a capture was added (only slice 23 is expected to).
   Never round it, and never let a draft or an invented hotel setting move it.
7. **Docs in the same PR:** the plan-v3 status row, `docs/architecture.md` if an interface was
   added, and `docs/open-questions.md` if a question moved.
8. **PR** titled for the slice, with these sections: *What it delivers* · *What it did not change*
   (packages and goldens) · *Exit test → where it is proven* · *Regression wall* (the six numbers)
   · *Declared contract changes* (or "none"). End with the attribution line. CI green → squash-merge
   → report.

A bug found **outside** the current slice: a GitHub issue first (what, reproduction, which gate,
severity), then `fix/NN-…`, a failing test, the fix, and a PR "Fixes #NN". Do not fold it into the
slice.

---

## 5. Fix #48 — the first thing to build, and why it edits an existing test

Read issue #48. The card number is the constant `"****"` on 228/228 captured cards (216 expiring
2021-01), so presence is not established.

- **Files:** `hotelcontrols/providers/minihotel/transforms.py` (`masked_to_presence_bool`),
  `hotelcontrols/providers/demopms/transforms.py` (the `card_last4` transform near line 171),
  `spec/canonical_fields.json` (the field's description), and `spec/providers/*.json` (mapping
  notes).
- **Behaviour:** a constant mask resolves **UNKNOWN with a reason naming #48 / question 2.8**. A
  blank number resolves UNKNOWN too: no capture shows one, so reading it as "no card" would be a
  guess about the vendor's encoding.
- **`tests/unit/test_minihotel_transforms.py:111-112` currently asserts `"****" → True` and
  `"" → False`.** Those assertions encode the very claim #48 refutes. Changing them **is** the fix.
  Say so in the PR in those words, so nobody reads it as a test weakened to go green. Add the
  contract-suite assertion that both providers agree.
- **Expected:** all 120 goldens byte-identical, criterion 1 unchanged, readiness unchanged. No
  shipped IR reads the field. **If any golden changes, stop.** It would mean something reads the
  field after all.
- Not part of the fix: any G4 control. G4 stays BLOCKED until MiniHotel answers question 2.8.

---

## 6. Traps the plan already found — per slice

| Slice | The trap | What the plan says |
| --- | --- | --- |
| 16 | A hand-maintained `version` can lie | The **spec lock** (control → version → digest of verdict-bearing content) makes "edited without a bump" a `validate_spec` failure. A pre-v3 stored run reads **"version not recorded"**, never the current version |
| 16 | Two new keys on run payloads | A declared contract change. Rebuild goldens and prove nothing else moved |
| 17 | `RunStore` reads with a default tenant | **Keyword-only, no default**: a missing tenant is a `TypeError`. Another property's run is a **404, not a 403** |
| 17 | A structural test that never fails | Plant an unscoped `SELECT`, watch it fail, then remove the plant |
| 18 | Changing `make_run_id` to get idempotency | **Don't.** Idempotency is the action record's natural key (property, control, policy version, record). Every stored run and golden keeps its identity |
| 18 | Creating actions inside `run()` | `runner/` is a must-not. The layer above the run creates them |
| 18 | An empty queue reading as "all clear" | The queue shows each control's coverage. A run that concluded nothing creates no record and shows as *reached no conclusion*. **UNKNOWN creates no record** (1.1 is open) |
| 18 | The demo store is in memory | Opt-in `--store PATH`. The default stays `:memory:` and the page says the queue is lost on restart |
| 19 | `smtplib` in the engine | The backend lives in `tools/notifiers/`, injected. The engine holds a protocol. **Two locks**: `HOTELCONTROLS_NOTIFY=1` **and** a refusal while a test runner is loaded |
| 19 | Staff addresses in committed files | Environment only, no default. A missing route leaves the record pending, saying so |
| 20 | `LogRecord` reads the wall clock | Stamp through the injected clock (`kernel/clock.py` is the only wall-clock reader, and an AST test enforces it). No `logging` in `evaluator/`. Nothing logged inside `providers/` (endpoint names would cross the boundary) |
| 21 | `[]` means both "decided none" and "not decided" | `null` = not decided → UNKNOWN naming it, through the evaluator's existing "has not supplied" path. **No evaluator change** |
| 22 | A model reading the request | The request is structured (D12). An AST guard asserts no model is reachable from `hotelcontrols/guest/` |
| 22 | `Money` has no multiplication | The fee is repeated `Money.plus` over whole hours after the hotel's stated `hour_rounding`. The kernel is untouched |
| 22 | `UNAVAILABLE` or `DENIED` from missing evidence | Never. Missing evidence or an undecided parameter → `STAFF_REVIEW` naming it. The sandbox's policy is `null`, so it answers `STAFF_REVIEW` to everything, which is honest |
| 23 | A probe as a standing permission | Each call approved at the time. Scrub before staging. Add a **new capture label**, never edit an old file. Nothing in `hotelcontrols/` changes |
| 24 | Expiry checked against the machine clock | Through the injected clock. Secret from the environment, no default. **Auth off → today's demo exactly, all 120 goldens identical.** `ui/` signs with `node:crypto`, so no new package (the pins test stays unedited) |

---

## 7. Decided — do not re-litigate

- **Mews is out.** **The engine never writes to a PMS** (1.10, G2(b) rejected).
- **D12** `LATE_CHECKOUT` only, structured, no model · **D13** data isolation early, auth last ·
  **D14** host authenticates, engine verifies HMAC; credentials per property in the environment;
  no encryption in v3 · **D15** five decisions `APPROVED`, `APPROVED_WITH_FEE`, `DENIED`,
  `STAFF_REVIEW`, `UNAVAILABLE`; parameters `free_until`, `charge_from`, `maximum_time`,
  `approval_required_after`, `fee_per_hour` (Money), `hour_rounding` (no default) · **D16** the
  evidence refresh is a slice, approved per call.
- D1–D11 stand: stdlib-only engine, per-call live approval, DemoPMS, never model → executable,
  pseudonymised fixtures, slice-per-PR, control 6 split, two surfaces.
- **G4 is BLOCKED** (#48, question 2.8). Do not build a payment-guarantee or card-on-file control
  in v3, under any name.

---

## 8. Rules, unchanged from v2

- **Never widen a verdict.** It outranks everything here.
- Tests never touch the network. Fixtures are evidence: never edited to pass a test, and never
  invented to reach a nicer outcome. `fixtures/demopms/` and `fixtures/api/` are generated.
- No live MiniHotel call without the owner's approval of that call (D3, R8).
- No credentials in source. No third-party personal data in a committed file. Staff email
  addresses count.
- Zero runtime dependencies in `hotelcontrols/`. `ui/` keeps its three exact pins.
- Before ending any session, update `docs/session-handoff.md` and the plan-v3 status table, so the
  next session starts from the truth.
