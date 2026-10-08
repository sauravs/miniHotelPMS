# Working brief — the ruleEngineAnishLegacy comparison

> **This file is a task brief for a fresh session, not project documentation.** It exists so the next
> agent starts with the reconnaissance already done instead of spending turns rediscovering it.
> **Delete it once the report it describes is merged.**
>
> Reconnaissance date: **2026-10-02**, on `main` at `e4ccac7`. Every number below was produced by
> running something, and the command is named. Where a thing was *not* verified, it says so.

---

## 1. The task

A second, independent implementation of the **same requirements this project already analysed**
exists at `ruleEngineAnishLegacy/`. Produce **one** document in `docs/` that compares it against
this codebase and says what we should take from it.

**The four framing decisions below were already put to the project owner on 2026-10-02 and
answered.** Do not re-litigate them.

| | Decision | Consequence for you |
| --- | --- | --- |
| **Purpose** | **Harvest into our roadmap.** Not a head-to-head, not a winner-picking exercise | Frame everything as *"what does the POC teach us, and where does it fold into the existing roadmap?"* Both are inputs; neither is being retired |
| **Execution** | **Read-only. Do not run it.** | `npm install` is forbidden, `node src/index.js` is forbidden, no listening port. Reading source and opening `poc.db` read-only is the whole toolkit. Behaviour you cannot establish that way is marked **UNVERIFIED**, not guessed |
| **Git** | **Gitignore it, like `miniHotelLegacy/`** | **Already done** — `.gitignore:32`, uncommitted. So a reader of this repository **cannot open the POC**: quote generously rather than citing line numbers nobody can follow |
| **Requirements baseline** | **Reuse `docs/stayops-gap-analysis.md`; spot-check rather than re-derive** | Do **not** re-extract the three `.docx`. They are byte-identical to the ones already analysed — md5s checked, all three match. The requirements side is written |

---

## 2. The single most important thing to understand before you start

**The POC was built against the SAME three StayOps documents, and it is the mirror image of this
project.** Not better, not worse — mirrored.

This repository went **deep on one half**: a real PMS, captured evidence, an honest UNKNOWN, money
that carries its currency, a bounded call budget, 1,610 tests.

The POC went **broad on the whole shape**: two tenants with scoped queries, guest services
end-to-end, templates with parameters, a control lifecycle, events, actions, a React UI — against
**mock data**, with **no tests**.

So the POC implements, in 727 lines, most of what `docs/stayops-gap-analysis.md` lists as our
largest gaps. That is the finding the report exists to turn into a plan. **It is also why the report
must not read as an indictment of either side.** A POC that mocked the PMS could afford the breadth;
an engine that met the real PMS could not afford it yet and learned things the POC never had to face.

---

## 3. What is actually there — measured, so you need not re-derive it

```
ruleEngineAnishLegacy/
├── initial-req/          3 .docx — BYTE-IDENTICAL to the ones already analysed
├── backend/
│   ├── src/index.js      413 lines — the ENTIRE backend
│   ├── poc.db            212 KB SQLite, 11 tables, seeded working state
│   ├── package.json      express 5, sqlite3, ws, cors.  NO lockfile
│   └── README.md         49 lines
└── frontend/
    ├── src/main.jsx      216 lines — the ENTIRE frontend
    ├── src/styles.css    23 lines
    ├── index.html        13 lines
    ├── package.json      react 19, vite 7, axios.  NO lockfile
    └── README.md         13 lines
```

**727 lines across 6 source files**, by `wc -l`. It self-identifies as `@stayops/poc-backend`.

For scale, by `find … -name '*.py' | wc -l` and `cat … | wc -l` on this repository:

| | POC | This project |
| --- | --- | --- |
| Source | **727 lines, 6 files** | **9,732 lines, 61 files** (`hotelcontrols/`) |
| Tests | **none — `find` for `*test*`/`*spec*` returns nothing** | **11,833 lines, 64 files** (1,610 passing) |
| Runtime dependencies | 8 npm packages, **no lockfile** | **zero**, stdlib only, AST-enforced |
| PMS | `provider: "MOCK_MINIHOTEL"`, `endpoint: "mock://pms"` | real captured MiniHotel responses + a second provider |

### `poc.db` — 11 tables, and the schema is the story

Read with `sqlite3.connect("file:backend/poc.db?mode=ro", uri=True)`. Every table carries
`tenant_id`:

| table | rows | why it matters |
| --- | --- | --- |
| `tenants` | 2 | `tenant_hotel_a`, `tenant_hotel_b` — two customers, which is D3 §85's SaaS requirement |
| `hotels` | 2 | `Asia/Kolkata` and `Europe/London` — per-hotel timezone, as we have |
| `controls` | 4 | `template_id` + `parameters_json` + `status` + `schedule` — **template-with-parameters, which we lack (our G6a)** |
| `service_policies` | 6 | guest-service policies per tenant — **we have none** |
| `guest_requests` | 10 | `intent`, `decision`, `fee`, `escalation`, `actions_json` — **the whole capability we lack (G1)** |
| `executions` | 11 | `trigger_type`, `event_id` |
| `execution_results` | 21 | `result`, `reason_code`, `explanation`, `evidence_json` |
| `pms_events` | 1 | event-driven execution |
| `event_stream` | 28 | an activity feed, broadcast over WebSocket |
| `reservations` | 3 | **has `payment_guarantee_status` and `complimentary`** — the two fields we cannot source (our G4) |
| `rooms` | 3 | `raw_status` kept alongside the normalised value |

**The data is unambiguously mock** and safe to quote: `Hotel A Group`, `Hotel B Group`, guest names
that are obviously synthetic, and phone numbers in reserved test ranges (`+919999999999`,
`+447700900000`). `grep` for `api[_-]?key|password|secret|token|bearer|credential|sk-` over all
source found **nothing** but the README sentence disclaiming production data. No credentials exist in
this tree.

### What `index.js` contains, by `grep -nE "^(const|function|app\.(get|post))"`

- `POLICY_CATALOG` — **all five hotel-control templates and all five guest-service templates**, with
  the documents' own parameter names (`freeUntil`, `chargeFrom`, `maximumAutomaticTime`, …)
- `normaliseRoomStatus` — a 5-entry map, `|| "UNKNOWN"` for anything unmapped
- `interpretPolicy(sourceText, kind)` and `extractGuestIntent(text)` — **keyword matching, no model**
- `evaluateControl`, `executeControl`, `broadcast`, `recordStreamEvent`, `actionsForDecision`,
  `validateGuestParameters`, `evidence(field, raw, value, …)`
- REST routes: controls list/create/**activate**/execute/results, service-policies list/create,
  guest-requests create/list, event-stream, policy-catalog, health

---

## 4. Findings that will produce a wrong report if you miss them

**1 · The tenancy is real plumbing behind a fake door, and the distinction is the most valuable
thing in this analysis.** `grep -c "tenant_id = ?"` returns **20** in `index.js`; the same grep over
`hotelcontrols/store/sqlite.py` finds **zero** `WHERE tenant_id`. So the POC genuinely scopes every
query — the discipline our Phase F needs. **But the tenant arrives in a header:**

```javascript
const tenantId = req.header("x-tenant-id")
if (!tenantId) return res.status(401).json({ error: "x-tenant-id header is required" })
const tenant = await db.get("SELECT id, name FROM tenants WHERE id = ?", [tenantId])
```

That is self-asserted identity with no authentication — any caller can claim any tenant by changing
one header. It is precisely what doc 01 §45 forbids: *"The API layer determines the tenant from
authentication rather than trusting a tenant ID supplied by the browser."* It is the same class of
hole as our `?property=`, one layer along.

**So the harvest is specific: take the scoped-repository discipline, and do not take the header
trust.** A report that says "the POC solved multi-tenancy" is wrong, and one that says "the POC's
tenancy is fake" is also wrong. It solved the half we have not, and left the half we also have not.

**2 · The POC has no EXCLUDED and no coverage verdict.** `grep -ohE '"(PASS|FAIL|UNKNOWN|EXCLUDED)"'`
finds PASS ×8, FAIL ×5, UNKNOWN ×5, **EXCLUDED ×0**. It implements the documents' three outcomes
faithfully — and therefore inherits the blind spot that `docs/stayops-gap-analysis.md` §5.1 argues
about, and that v1 of this project measured as a real failure (28 EXCLUDED / 0 FAIL rendering as a
clean bill of health). **This is the clearest case where we are ahead, and it is not a criticism of
the POC: it is a criticism of the specification both were built from.** It strengthens open question
1.12.

**3 · Mock data means none of the seven documented API facts ever bit it.** `CLAUDE.md` lists seven
findings that came from calling the real API. A mock PMS returns `payment_guarantee_status` and
`complimentary` as clean enums because somebody typed them. Check each of the seven against the
POC's model and expect most to be simply absent — no reservation-folio currency split (R9), no `0`
meaning "unconfigured" (R10/R12), no undocumented status codes, no per-property status
customisation. **Do not score this as negligence.** Score it as the cost of mocking, and note what it
means for the harvest: **the POC's shape is reusable, its evidence layer is not.**

**4 · Keyword matching, not a model, and that is a legitimate choice to assess honestly.**
`interpretPolicy` and `extractGuestIntent` are string matching — `grep -inE "llm|openai|anthropic|
claude|gpt|model"` over `index.js` returns **nothing**. Compare against decision D10 and this
project's own `StubProposer`, which is *also* a lookup table and is defended as the right thing for
tests. The honest comparison is not "they have no AI" but *"how far does a keyword matcher get, and
what does it do when it does not recognise something?"* — check whether it falls back to
STAFF_REVIEW/UNSUPPORTED or guesses. `guest_requests` contains a `MISCELLANEOUS` → `STAFF_REVIEW`
row, which suggests it does the right thing; **verify before claiming it**.

**5 · `EXTRA_TOWELS` became `EXTRA_ITEM_REQUEST`.** The POC generalised one of the manager's five
templates into a configurable item request with `itemName`, `freeQuantity`, `maximumQuantity`. That
is arguably better than the specification and worth flagging as a POC-ahead row.

**6 · The POC resolved two of the nine document inconsistencies, by choosing.** It picked the
five-outcome decision set including `STAFF_REVIEW` (inconsistency #1) and camelCase parameter names
(#2). That is **evidence for open question 1.11** — somebody has already made these calls once, and
their choices are a reasonable default to adopt rather than re-deciding from scratch.

**7 · No tests, and say it without sneering.** 727 lines and zero tests is normal for a POC and
disqualifying for a product. The useful sentence is not "it is untested" but *"which of its
behaviours can we therefore not rely on when we port them?"*

**8 · Do not compare file layouts or line counts as quality.** 727 lines doing ten things and 9,732
lines doing five things are different bets, not different skill levels. Doc 03 §2 says the
architectural requirement matters more than the layout. Compare **responsibilities and guarantees**.

---

## 5. Suggested structure for the report

One document, in `docs/`. Suggested name: `docs/poc-comparison.md`. Adjust if the reading suggests
better.

1. **What the POC is, in five sentences** — 727 lines, same three requirement documents, mock PMS,
   no tests, and it implements most of what our gap report says we lack. State the mirror-image
   framing immediately; everything else reads wrongly without it.
2. **Side-by-side capability matrix** — reuse `docs/stayops-gap-analysis.md` §3's requirement areas
   as the rows, and add a POC column. Three columns: requirement · us · POC. This is the table the
   owner will actually use, so make it the centrepiece.
3. **Where the POC is ahead, and what we take** — per item: what it does, how it does it, whether
   the mechanism survives contact with a real PMS, and which roadmap phase it folds into. Be
   concrete: name the function, name the table.
4. **Where we are ahead, and what the POC would have to add** — EXCLUDED and coverage, UNKNOWN with
   a reason, money with currency, the call budget, the canonical boundary as a test, two real
   providers, the tests.
5. **Where both are short** — authentication (both trust a self-asserted identity), policy
   versioning, observability, idempotency. A requirement neither met is a requirement the
   *documents* failed to make urgent, which is a finding about the specification.
6. **The harvest plan** — the actual deliverable. For each item taken: which phase of
   `docs/stayops-gap-analysis.md` §7 it belongs to, whether it is a port, a rewrite or just an idea,
   and **an exit test**, in the style `docs/plan.md` uses. Keep the existing phase letters so the
   two documents compose instead of competing.
7. **What must NOT be ported** — the header-trusted tenant, mock evidence shapes, the missing
   EXCLUDED. A harvest document without this section is a liability.
8. **Open questions** — cross-reference `docs/open-questions.md`, and add entries if warranted.
   Expect at least one: *is the POC's author available to explain intent?* That changes how much can
   be inferred from the code.

**Length.** `docs/stayops-gap-analysis.md` is 1,321 lines and the owner chose to keep it as one
file. This report compares a 727-line codebase; it should be **considerably shorter** — if it runs
past ~600 lines, something is being padded. Reuse the gap report by reference rather than restating
it.

---

## 6. Constraints

- **Read-only on the POC.** No `npm install`, no `node`, no listening port, no network. `poc.db`
  opens with `?mode=ro`. If a behavioural claim cannot be established by reading, mark it
  **UNVERIFIED** — that habit is this project's whole personality and a comparison report that
  manufactures confidence would be the wrong artifact.
- **Do not implement anything.** Not the harvest, not one line of it.
- **`ruleEngineAnishLegacy/` is gitignored as of this brief** (`.gitignore:32`, **uncommitted** —
  commit it with the report). Readers cannot open it, so quote.
- **Nothing sensitive crosses over.** Verified clean, but re-check anything you quote.
- **Start on a fresh branch off `main`** — e.g. `docs/poc-comparison`. Branch → PR → CI green →
  squash-merge, per `CLAUDE.md`. **`main` requires the `test (3.11)` and `test (3.13)` checks and is
  strict**, so a direct push will be refused; the PR route is the only one.
- **Do not commit or push without being asked.**

---

## 7. Repository state you are inheriting

`main` at `e4ccac7`, working tree carrying **one uncommitted change: the `.gitignore` entry above**.

Five PRs merged on 2026-10-02: #27 (the two StayOps analysis documents), #28 (QA Q6–Q7), #29 (Q8),
#30 (Q9), #31 (Q10 + vendor question 2.7).

**Read these first, in this order** — they are the other side of the comparison and they are
current: `CLAUDE.md`, then `docs/stayops-gap-analysis.md` (the requirements *and* our state, already
measured), then `docs/stayOps_Cotrols_Rule_Engine_V2.md` (the plain-language account of intent),
then `docs/open-questions.md` §1.10–1.12 and §2.7, then `docs/QA.md` Q8–Q10 — which already answer,
at length, the multi-tenancy questions this comparison will raise again.

Two branches remain **committed, never pushed, now 5 commits behind `main`**, and neither bears on
this task: `fix/27-unvalidated-predicate-operands` (three operand-validation bugs fixed TDD, 41
tests, green) and `docs/27-resync-explainers`. Note that **GitHub issue #27 was never filed** — the
number is now PR #27 — so those branch names reference an issue that does not exist.
