# Slice 15 — a React/Next.js UI, added without touching the engine

**This file is the starter prompt for the next session.** Paste it, or point the agent at it.

Written at the end of slice 14 (`slice/14-ui-ux`), by the session that did the UI/UX pass on the
server-rendered surface and therefore read all of `render.py`, `app.py`, `server.py`, `style.css`
and the 204 tests over them.

---

## 0. Why this slice exists, and the one sentence that governs it

Two honest reasons, neither of them "React is better":

1. **The project owner reads React more fluently than Python**, and a UI you can read is a UI you
   can trust and change.
2. **This product will be patched into a superset product built in JavaScript / TypeScript /
   Next.js.** A React UI here converges the two; a bespoke Python rendering layer diverges them.

Neither is mandatory today. The owner's stated priority outranks both:

> **Nothing may break. No core logic may break.**

So the governing sentence of this slice:

> **This is an ADDITION, not a rewrite. The React UI becomes a second client of a JSON API that
> already exists. The server-rendered surface stays, working, until a separate and later decision
> says otherwise.**

A "redo" that deletes `render.py` is how core logic gets broken. A strangler-fig that adds `ui/`
beside it cannot break core logic *by construction* — and §3 turns that from a promise into a
mechanical gate.

---

## 1. READ FIRST, IN THIS ORDER

1. `CLAUDE.md` — the four ideas and the seven API facts. Non-optional.
2. `docs/prd.md` §4 (why UNKNOWN is first-class) and §7 (the twelve criteria). **§6 matters
   specially**: it lists *"A web surface: server-rendered, no JavaScript"* as **in scope**. This
   slice contradicts that line. See §12 — it needs the owner's sign-off, not a quiet edit.
3. `docs/architecture.md` §3 "L7 · WEB" and §5 (testing strategy).
4. `hotelcontrols/web/app.py` — the routing and, more importantly, `_execute`. Read it closely;
   `/api/run/` **has side effects** (trap 4).
5. `hotelcontrols/web/render.py` — specifically `run_json`, `_verdict_json`, `_line_json`,
   `_readiness_json`. **This is the contract you are consuming.** Also read `verdict_groups`,
   `_tiles` and `outcome_glossary` — they are the slice-14 answers to problems you will hit again.
6. `hotelcontrols/web/assets/style.css` — read the header comment first. It records which rules are
   a success criterion rather than a theme.
7. `tests/unit/test_web_routing.py` — the docstring at the top, the `text_of()` helper, and
   `TestCriterion2UnknownIsNotAFailure`. `text_of()` is the single most important idea to carry
   into the React suite.
8. `hotelcontrols/web/server.py` — short, and explains why the server is serial (trap 6).

Skip `docs/context.md`, `docs/plan.md`, `docs/QA.md`, `miniHotelLegacy/` and `stayops/*`.

**Do look at `ruleEngineAnishLegacy/`** — React 19 + Vite + axios + Express + ws, 216 lines of
`main.jsx`, 413 of backend, **zero tests**. It is prior art for the stack and a cautionary tale
about the test discipline. Do not copy its structure.

---

## 2. Run both surfaces and look at them before writing anything

```bash
python3 -m hotelcontrols.web.server                                   # :8765
HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub --port 8766 # :8766, adds /compose
```

Stdlib only — no venv, no `PYTHONPATH` needed. Tour these; each shows a different state, and your
React UI has to reproduce every one of them:

| URL | State it demonstrates |
| --- | --- |
| `/` | index + readiness per control per provider (criterion 10) |
| `/run/checkout_unrefunded_credit` | a real FAIL, −490.75 ILS |
| `/run/inactive_room_future_stay` | 111 records: PASS + UNKNOWN + EXCLUDED, grouped |
| `/run/ooo_room_protection` | **"reached no conclusion", NO tiles** — and `counts` IS in its JSON |
| `/run/resource_occupancy_consistency` | blocked, NO tiles, no `counts` key at all |
| `/history/checkout_money_owed` | past runs |
| `:8766/compose` | the compose window |

---

## 3. THE NON-NEGOTIABLE INVARIANT — and the gate that enforces it

**No file in these nine packages may change in this slice:**

```
hotelcontrols/kernel/  spec/  providers/  evidence/  evaluator/  runner/  store/  compiler/
```

That is the core logic, end to end: `Value`, `Money`, `Outcome`, `Verdict`, the clock, the IR
loader, both adapters, the budget, the Kleene evaluator, coverage, readiness, scheduling, the
SQLite store and the grammar. The React UI consumes their output as JSON and has no business
reaching into any of them.

Inside `hotelcontrols/web/` the permitted change is **narrow and additive**: new read-only JSON
routes in `app.py` (§6), with their tests. `render.py`, `server.py` and every existing route stay
byte-identical in behaviour.

**Prove it mechanically, in every PR, and put this in CI:**

```bash
git diff --name-only origin/main...HEAD \
  | grep -E '^hotelcontrols/(kernel|spec|providers|evidence|evaluator|runner|store|compiler)/' \
  && { echo "SLICE 15 TOUCHED CORE LOGIC - STOP"; exit 1; } || echo "core logic untouched"
```

Write it as a pytest too, so it is part of the suite and not just a CI step. **If you ever find
yourself wanting to change a file in that list, you have misunderstood the slice — stop and ask
the owner.** The most likely honest cause is a missing field in the JSON, which is a `render.py`
and `app.py` problem, not a kernel problem.

---

## 4. Where the React app lives, and what stack

```
miniHotelPMS/
├── hotelcontrols/      ← the engine. UNTOUCHED except web/app.py's new routes
├── spec/  tools/  tests/  fixtures/  docs/
└── ui/                 ← NEW. Next.js + TypeScript. Nothing here is importable from the engine
```

`ui/` sits **outside** `hotelcontrols/`, which is the same pattern `tools/proposers/` uses to keep
a model backend out of a stdlib-only engine. Consequences, all of them good:

- **Criterion 11 stays true as written.** `tests/unit/test_stdlib_only.py` walks `hotelcontrols/`.
  The engine still imports nothing outside the standard library, and still runs with no network.
- `npm` never becomes a dependency of the Python suite or of the two required CI checks.
- The engine can be shipped, audited or demoed with `ui/` deleted.

Stack: **Next.js (App Router) + TypeScript + React**, to match the superset product. Keep the
dependency list deliberately short — every package is a package somebody will have to justify in a
product sold on auditability (§5, trap 7). Server Components are a good fit here: the data is
read-only and the "no JavaScript in the page" instinct of the current design survives partially if
most of the tree renders on the server.

---

## 5. THE SEVEN TRAPS

Each one is verified against the live API, not inferred. Each one, if walked into, breaks a
success criterion silently — the page will look fine.

### Trap 1 — `counts` is present on a run that concluded NOTHING. This is the big one.

```
GET /api/run/ooo_room_protection?property=sandbox&evidence=sandbox2026
  blocked            : false
  coverage.concluded : false
  counts             : {"PASS":0,"FAIL":0,"UNKNOWN":0,"EXCLUDED":28,"total":28}   ← present!
```

A component that renders tiles whenever `counts` exists will render **0 PASS · 0 VIOLATION ·
0 NO ANSWER · 28 NOT APPLICABLE** — which is exactly the v1 finding F5 failure, reproduced in a new
language. Four zeroes with one of them under VIOLATION reads as a clean bill of health.

> **The gate is `coverage.concluded`, never the presence of `counts`.** Blocked runs happen to omit
> the key; non-concluding runs do not. Write the failing test for `ooo_room_protection` first.

### Trap 2 — money is a string, and parsing it loses the currency

```json
{"field":"folio.balance_due","known":true,"value":"-490.75 ILS","unit":"ILS","source":"pms:..."}
```

`parseFloat("-490.75 ILS")` → `-490.75`, and the ILS is gone. R9 is the reason this matters:
reservation `007003199` reports **870 USD** while its own folio reports **3262.5 ILS**, and no
exchange rate exists anywhere in the API. A bare number on screen invites a reader to do arithmetic
that is meaningless.

> **Render `value` verbatim. Never `parseFloat`, never `toFixed`, never `Intl.NumberFormat`, never
> re-join `value` with `unit`.** If you need to sort or compare, do it server-side.
> Ban the pattern with a lint rule or a test that greps `ui/` for `parseFloat`.

### Trap 3 — the provenance string carries a vendor name, and `ui/` is outside the criterion-5 guard

```json
"source": "pms:minihotel/GetReservationBalance"
```

This is the **one deliberate exception** to the canonical boundary: it crosses as *data* so an
auditor can see which system and which call produced a number. `tests/unit/test_canonical_boundary.py`
polices `hotelcontrols/` — **it does not walk `ui/`**. So `if (provider === "minihotel")` in a
`.tsx` file would pass CI in silence and quietly end the PMS-agnostic thesis.

> **Display `source` as an opaque string. Never split it, parse it, or branch on it.** Extend the
> boundary test to walk `ui/**/*.{ts,tsx}` for the same identifier list in the same PR. That
> extension is itself a deliverable of this slice.

### Trap 4 — GET `/api/run/` has side effects, and React StrictMode double-fires

`app.py:_execute` spends provider calls and writes a row to the store on a **GET**. React 19
StrictMode double-invokes effects in development; React Query's `refetchOnWindowFocus` is on by
default; Next.js prefetches links.

Any of those turns one run into two or many: double provider calls (criterion 4's `1 + R + N`
budget, R1, R8) and duplicate history. On fixtures this is slow and confusing; against a live
transport it would be a breach of the agreement with MiniHotel not to query wide ranges (R8).

> Fetch a run **once**, deliberately, then read it back from `/api/runs/<run_id>`, which costs zero
> provider calls by construction. Set `staleTime: Infinity` and `refetchOnWindowFocus: false`. Do
> not put a run fetch in a `useEffect` that can re-fire. Never fetch a run during render.

### Trap 5 — three JSON routes exist; the index and history pages cannot be built from them

The complete JSON surface today is `/api/run/<id>`, `/api/runs/<run_id>`, `/api/readiness/<id>`.
There is **no** controls list, no properties/captures list, no history endpoint. You must add them
(§6). This is the only place Python changes, and therefore the only place real risk lives.

### Trap 6 — the server is serial, and the store is a single-thread connection

`server.py` uses `HTTPServer`, not `ThreadingHTTPServer`, and the comment there records why: a
threading server answered its first run page with `500 ProgrammingError: SQLite objects created in
a thread can only be used in that same thread`, **with the whole suite green**.

A React index page that fires eleven parallel readiness requests will have them served one at a
time. That is correct and merely slow.

> **Do not "fix" this by making the server threaded.** The store must become thread-safe first, and
> that is core logic (§3). Batch on the server instead — one request that returns all eleven
> readiness reports (§6) — or accept the latency. `check_same_thread=False` would convert an
> exception into a data race and is forbidden.

### Trap 7 — you are spending the zero-supply-chain property; spend it consciously

The project today has **zero** third-party runtime code. This page renders guest names, surnames
and free-text remarks that arrive from booking channels. Two things follow:

- **Keep `ui/`'s dependency list short and justified**, pin exactly, and commit the lockfile. Every
  package is one somebody will have to account for.
- **`dangerouslySetInnerHTML` is banned outright.** React escapes by default; that default is now
  the only lock where the Python surface had two (`render._e()` *and*
  `Content-Security-Policy: default-src 'none'`). Add a test that greps `ui/` for it.

---

## 6. The API routes to add — read-only, and the only Python you touch

Add to `hotelcontrols/web/app.py:route()`. All GET, all read-only, all pure functions of the path.
`handle(path)` stays a pure function of the path; writes continue to go through `handle_post`.

| Route | Returns | Notes |
| --- | --- | --- |
| `/api/controls` | every reviewed control: `control_id`, `name`, `natural_language`, `entity`, plus its readiness per provider | What the index needs in **one** request. Solves trap 6 |
| `/api/properties` | each tenant: `id`, `name`, `provider`, `captures`, `default_capture` | Powers the evidence picker |
| `/api/history/<control_id>` | the rows `history_page` already renders | Same data, as JSON |
| `/api/drafts` | the draft IRs, each flagged unreviewed | Only when a `draft_dir` is wired |

Rules for these four:

- **Reuse the existing serialisers.** `_readiness_json` and `_verdict_json` exist; a second
  hand-rolled shape for the same object is how two surfaces drift apart.
- **No new provider calls.** `/api/controls` must be answerable from the spec alone — `readiness()`
  already is. Assert the call count is zero in a test.
- **Refuse an unknown id with the same 404** the HTML routes give, via `SpecError`/`_Refused`.
- Every new route needs unit tests in `tests/unit/test_web_routing.py` and matrix coverage in
  `tests/integration/test_web_pages.py`, in the house style: **every test names the criterion or
  risk id it protects.**
- Coverage floor is 90% and currently 96%. New Python without tests will push it down.

---

## 7. The four criteria the React UI must RE-PROVE

The existing tests prove these about the *server-rendered* surface. They say nothing about `ui/`.
A React UI that does not re-prove them is a React UI that silently fails the product.

| # | Criterion | How the React suite must prove it |
| --- | --- | --- |
| **2** | UNKNOWN is distinguishable from FAIL by **hue, border AND wording** | Render a verdict of each outcome, **strip all styling**, and assert the words still differ — the direct analogue of `text_of()`. Then a Playwright test asserting the four *computed* `border-left-style` values are four different values and the hues differ. jsdom cannot see computed styles; do not pretend it can |
| **3** | Every verdict traces to its fields — name, value, unit, provenance, gap reason | Assert `-490.75 ILS` appears **with its currency**, `folio.balance_due` appears, and the `pms:` provenance appears, for `checkout_unrefunded_credit` |
| **8** | A run that concluded nothing says so, and shows no counts | `ooo_room_protection` → no tile row rendered, and the words "reached no conclusion" present. See trap 1 |
| **10** | Readiness per control per provider | The index shows both providers' ratios, and names what to connect for `rate_room_category_consistency` (3 of 5) |

Carry across the three ideas slice 14 added, too: **EXCLUDED is never folded into PASS**; the
glossary is built from one source of outcome wording, not restated per component; and help is
visible/inline, never a `title=` tooltip (invisible to touch, stripped by text extraction,
unreliable for screen readers). The slice-14 tests name all of this — read them as the spec.

---

## 8. End-to-end test strategy

Four layers. **No test may touch the network or need a listening port** — `architecture.md` §5 is
explicit, and a suite that needs someone else's server up is not a suite.

### Layer 1 — golden payloads (build this first; everything else rests on it)

Add `tools/dump_api_fixtures.py` which writes, for the **full matrix** (11 controls × every
property × every capture, ≈44 files) plus every history and readiness response:

```
fixtures/api/<control_id>.<property>.<capture>.json
```

These are generated artefacts, exactly like `fixtures/demopms/`: **a test asserts a rebuild is
byte-identical**, and they are never hand-edited. They give you:

- a React suite that runs offline with no Python process and no socket;
- immunity to trap 4 — the test suite never triggers a run;
- a diff-visible record of the contract, so a `render.py` change that alters the payload shows up
  as a failing rebuild rather than as a broken UI three weeks later.

### Layer 2 — Python contract tests

In `tests/integration/`: assert the payload shape every React component depends on. Especially that
`coverage.concluded` is `false` while `counts` is present for `ooo_room_protection` (trap 1) — pin
the trap so nobody "tidies" the payload and breaks the UI's gate.

### Layer 3 — React component tests (Vitest + React Testing Library)

Rendered from the golden payloads. The four criteria of §7, plus:
`dangerouslySetInnerHTML` absent; `parseFloat` absent from `ui/`; no PMS identifier in `ui/`.

### Layer 4 — the parity harness, and Playwright

**The parity harness is the "nothing breaks" proof.** For every golden payload, assert:

```
set of (record_id → outcome) rendered by React  ==  set of (record_id → outcome) in the payload
count of verdict blocks rendered                ==  len(payload["verdicts"])
tiles rendered                                  <=> payload["coverage"]["concluded"]
```

That catches dropped, duplicated and mis-grouped records — the three ways a grouping UI lies. Slice
14 hit exactly this: 111 verdicts in, 111 out, asserted.

Playwright does the small set of things only a real browser can: the four computed border styles,
keyboard reachability of every disclosure, and an `axe` pass per page state. Keep it to a handful
of assertions; it is the slowest layer and the easiest to let rot.

### Dev wiring — no CORS, no CSP change

Proxy in `next.config.js` so the browser only ever talks to one origin:

```js
async rewrites() {
  return [{ source: "/api/:path*", destination: "http://127.0.0.1:8765/api/:path*" }];
}
```

> **Do not add CORS headers to `server.py`** (and §3 forbids touching it anyway). **Do not relax the
> `Content-Security-Policy`** — it is asserted verbatim as
> `default-src 'none'; style-src 'self'; img-src 'self'`, and it protects the *existing* surface,
> which keeps working. Next.js serves `ui/` from its own origin with its own policy; set a real
> one there rather than inheriting nothing.

---

## 9. STANDARD INITIAL FOLLOW-UP PROCEDURE

Do these in order, before writing a line of React.

**1. Baseline, and write the numbers down.**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest            # expect 1662 passed, 1 skipped
python3 -m tools.validate_spec                         # expect PASSED - all 1080 checks
python3 -m coverage run -m pytest && python3 -m coverage report   # expect 96%, floor is 90
python3 -m tools.transcode_demopms --check             # expect 11 files, byte-identical
```

These four numbers are the regression wall. **Report them in the PR, before and after.** If
slice 14 has merged, 1662 is the floor; if not, branch from `slice/14-ui-ux` and say so.

`PYTHONDONTWRITEBYTECODE=1` is not hygiene — it is a correctness gate. v1 recorded two occasions
where a stale `.pyc` made the suite run old code and report a meaningless green.

**2. Confirm the invariant guard works before you need it.** Write the §3 test, make it fail by
touching a kernel file, revert, watch it pass.

**3. Build the golden payloads (§8 layer 1) and commit them.** This is the contract. Review the
diff by eye; it is the most informative artefact in the slice.

**4. Add the four API routes (§6) with their tests, as one PR of its own.** Python-only, no React.
Merge it green. Now the React work cannot be blocked by a missing field, and if anything *does*
break, it broke here, in a small reviewable diff.

**5. Scaffold `ui/` and prove the test harness works** on one page — the run page for
`checkout_unrefunded_credit` — including all four criteria of §7 and the parity harness. Only then
build the rest.

**6. Then, page by page**, TDD: failing test first, written **from the requirement rather than from
the component you intend to write**. One page per PR: run → index → history → compose.

---

## 10. Git and CI

```
branch  slice/15-react-ui-<page>        one branch per PR, as above
   ↓    push, open PR, CI green
   ↓    squash-merge to main
```

`main` is strict and requires `test (3.11)` and `test (3.13)`. **Do not commit or push without
asking the owner.** Bugs get a GitHub Issue written *before* the fix, while the reproduction is
still known, then `fix/NN-short-description` with a failing test first.

CI changes needed, all additive:

- the §3 core-logic diff guard;
- a **separate** `ui` job (node + `npm ci` + vitest + playwright). It must not be a dependency of
  the two required Python checks, so a broken `npm` can never block an engine fix.

---

## 11. Definition of done

- [ ] Python suite ≥ 1662 passing, 0 failing. `validate_spec` 1080. Coverage ≥ 90.
- [ ] `git diff` shows **no** file changed under the nine engine packages, enforced by a test.
- [ ] `render.py` and `server.py` behaviourally unchanged; every existing route still answers.
- [ ] The server-rendered surface still works, end to end, unmodified. **Both UIs ship.**
- [ ] Golden payloads committed, with a byte-identical rebuild test.
- [ ] Criteria 2, 3, 8, 10 each re-proven in the React suite, criterion 2 including a real-browser
      assertion on the four computed border styles.
- [ ] Parity harness green across the full matrix: no record dropped, duplicated or mis-grouped.
- [ ] `ui/` greps clean for: PMS identifiers, `dangerouslySetInnerHTML`, `parseFloat`, `title=` as
      a help mechanism.
- [ ] The canonical-boundary test extended to walk `ui/`.
- [ ] `axe` passes on index, run, no-conclusion, blocked, history and compose.
- [ ] CSP on the Python surface byte-identical; a real CSP set on the Next surface.
- [ ] `docs/prd.md` §6 and `docs/architecture.md` §3 updated to describe two surfaces — **with the
      owner's sign-off** (§12).

---

## 12. Out of scope, and one thing to ask the owner first

**Ask before starting:** `prd.md` §6 lists *"A web surface: server-rendered, no JavaScript"* as in
scope, and `architecture.md` §3 gives the reasoning (a page that assembles itself from an API call
is a page a browser, a CSP or a `file://` open can break). This slice does not violate that while
both surfaces ship — but the document must be updated to say "two surfaces, and why", and that is
the owner's call, not a quiet edit in a PR. Get it in writing.

**Explicitly not in this slice:**

- Deleting or retiring the server-rendered surface. Separate, later, evidence-based decision. It is
  the offline, printable, zero-dependency audit surface and it is what proves criterion 11 at the
  page level.
- Authentication, multi-user, roles — `prd.md` §6 out of scope.
- A rule editor — out of scope. `/compose` is a draft-filing window, nothing more.
- Writing to a PMS. Read-only, permanently.
- Making the server threaded, or `check_same_thread=False` (trap 6).
- Any change that widens a verdict. **If evidence is missing the answer is UNKNOWN.** Turning an
  UNKNOWN into a PASS to make a test green, a number look better or a demo look finished defeats
  the entire product. This rule outranks everything else in this file.

**Rollback:** `rm -rf ui/` and revert the `app.py` routes. Because the work is additive, rollback is
two commands and loses nothing — which is the whole reason it is additive.
