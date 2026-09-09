# Q&A Log

A running transcript of questions from the project owner and the answers given, newest at the
bottom. Appended to by the `/qa-log` skill; **append only, never rewritten.**

Three conventions make this useful rather than merely long:

- The question is recorded **verbatim**. A paraphrase quietly changes what was asked.
- Every answer states **what was actually checked** — files read, commands run, fixtures inspected —
  or says plainly that it was reasoning only. Documentation review got 4 of 12 risks wrong on this
  project; that is why the field exists.
- A wrong answer is **corrected by a new entry, not by an edit**. The old entry gets one added line
  (`Status: superseded by Q<n>`) and otherwise stands. Being wrong on the 4th is part of the record.

The v1 transcript — twelve entries covering the feasibility analysis, the sandbox probing and the
architecture dry run — is preserved at `miniHotelLegacy/QA.md`. This file starts fresh at Q1 for v2.

---

## Q1 — 2026-09-08

**Q:** There is already a folder named "miniHotelLegacy". It is old codebase containing all
important docs explaining the requirements of this project like claude.md, context.md, prd.md, etc.
It also contains two very important initial requirement docs Hotel Controls.docx and
control_rule_architecture.docx. MiniHotel_Controls_API_Feasibility.xlsx was created after verifying
with miniHotel docs API. Please first analyze this codebase deeply with all important aspects
covered, so that you understand the requirement thoroughly and have accurate context. After that in
this root directory, re-implement this requirement step by step with proper claude workflow like
freshly creating and implementing everything from scratch like plan.md, prd, context etc.

**A:**

Reviewed the whole of `miniHotelLegacy/` in four passes: the two requirement `.docx` files, the nine
markdown documents, all 4,286 lines of `engine/` and `tests/`, the `spec/` layer (52 canonical
fields, 10 IRs, 880 validation checks) and the 14 frozen `probe/` responses — then **ran** the code
rather than only reading it.

**What v1 is.** A PMS-agnostic control engine in four silos: evidence (the only layer that knows
MiniHotel exists), population (bounded queries, call budget), evaluator (pure, four outcomes) and
runner/UI. 152 tests, all offline, all green. The design is right and the engineering discipline is
unusually good — `old-codebase-improve.md` lists twelve things (K1–K12) carried into v2 unchanged.

**What running it revealed.** Executing all 10 controls against all 3 evidence sets:

| | |
| --- | --- |
| Controls that ever produce a PASS or FAIL | **1 of 10** |
| Blocked against every evidence set | 2 |
| 100% EXCLUDED (looks identical to a clean bill of health) | 1 |
| 100% UNKNOWN | 6 |

Three missing capabilities explain all nine failures: no **reference stage** (a record can never be
joined to property-wide data — three controls return 111 UNKNOWN out of 111 records), no
**cross-record evaluation** (duplicate detection returns zero answers despite the fixtures containing
a known real duplicate pair), and no **record projection** for composite entities.

Two further defects were reproduced directly against the v1 resolver rather than inferred:
reordering two XML attributes in a semantically identical document silently turns a known arrival
date into UNKNOWN, and XML entities are never decoded, so a guest named `O'Brien` resolves as
`O&apos;Brien`.

**What v2 is.** Eight layers instead of four, adding the reference stage, population-level
evaluation, a coverage verdict, a readiness report, a second provider, the natural-language
compiler, scheduling, and SQLite run history — built as twelve TDD slices, each gated by CI and
merged through a PR. Full detail in `prd.md`, `architecture.md` and `plan.md`.

**Evidence:** read every file in `miniHotelLegacy/`; extracted both `.docx` files; ran
`python3 -m unittest discover -s tests` (152 pass) and `validate_spec.py` (880 checks pass); ran all
10 controls × 3 evidence sets and tabulated the outcomes; wrote throwaway probes that reproduced the
attribute-order and XML-entity failures against the live v1 resolver.

**Status:** answered

---

## Q2 — 2026-09-08

**Q:** Do not guess, ask questions in case of any concerns or needed clarification first before
implementing/writing plan, prd, etc.

**A:**

Eight decisions were put to the project owner before any v2 document was written, because each would
have changed the plan materially. All eight are recorded in `open-questions.md` §0 as D1–D8:

| | Decided |
| --- | --- |
| Scope | All 10 dry-run controls made genuinely executable (11 IRs after splitting control 6) |
| Dependencies | Stdlib-only runtime; `pytest` + coverage as dev dependencies |
| Live API | Allowed, with per-call approval |
| Second provider | A fictional `DemoPMS` speaking JSON, offline |
| NL compiler | Deterministic grammar core, LLM adapter behind the same validation gate |
| Repository | Public, fixtures pseudonymised, credentials from environment only |
| Git workflow | Branch per slice → PR → CI gate → squash-merge |
| Overpaid folio | Split control 6 into two controls — money owed, and unrefunded credit |

Four further decisions were deliberately **not** taken unilaterally and are carried as checkpoints
in `plan.md`: approval for three read-only calls to refresh the stale 2024 room findings (before
slice 3); whether a cancel-and-recreate pair sharing one portal id is a duplicate (before slice 5);
which rate codes a property has nominated (before slice 6); and whether the LLM adapter should be
wired to a real model (before slice 9).

**Evidence:** decisions collected directly from the project owner on 2026-09-08.

**Status:** answered

---

## Q3 — 2026-09-09

**Q:** Pls check  and verify  with intial req doc (inside miniHotelLegacy) Hotel Controls.docx / MiniHotel_Controls_API…xls out of 20+ controls given, how much we have implemented and verified so far in our current codebase?

**A:**

Three different numbers, and they are worth keeping apart.

| | count |
| --- | --- |
| Controls in `Hotel Controls.docx` | **20** |
| Rows in the feasibility workbook | **21** (control 1 splits into 1a–1c and 1d) |
| Feasibility verdict: Yes / Partial / No | **9 / 10 / 2** |
| **Built as an executable IR** | **10 of 21 rows → 11 IRs** (control 6 splits in two) |
| **Reaching a real PASS or FAIL on captured evidence** | **6 IRs — 5 source controls** |
| **Re-verified against the live API by v2** | **0 calls** |

### What was built, and what it answers

| row | feasibility | our control | answers? |
| --- | --- | --- | --- |
| 1a–1c | Yes | `room_assignment_type_validity` | **yes** — 27 PASS |
| 1d | Yes | `room_assignment_active_room` | no — 111 excluded |
| 2 | Yes | `ooo_room_protection` | no — 28 excluded |
| 4 | Yes | `room_capacity_compliance` | no — 40 UNKNOWN |
| 6 | Yes | `checkout_money_owed` | **yes** |
| 6 | Yes | `checkout_unrefunded_credit` | **yes** — the −490.75 ILS overpayment |
| 9 | Partial | `rate_room_category_consistency` | no — 40 UNKNOWN |
| 13 | Yes | `inactive_room_future_stay` | **yes** — 27 PASS |
| 14 | Yes | `duplicate_channel_reservation` | **yes** |
| 15 | Yes | `required_reservation_fields` | no — 37 UNKNOWN |
| 20 | Yes | `resource_occupancy_consistency` | **yes**, but only over the one week its capture covers |

**Every row the feasibility study rated "Yes" was built** — all nine — plus one "Partial" (control
9). No scope drift: that is exactly the list `prd.md` §6 committed to.

### The eleven not built, and why

Two are **structurally blocked** — the entities do not exist in the API:

- **8** rate-plan eligibility — no rate-plan master, nothing to validate a rate against
- **17** company/corporate rate control — no company or account object anywhere

Nine need something the PMS does not record:

| row | what is missing |
| --- | --- |
| 3 | only one room type per stay — no booked-vs-assigned distinction, so an upgrade cannot be told from an error |
| 5 | no endpoint exposes the *configured* payment/guarantee requirement |
| 7 | no cancellation-policy endpoint — penalty window and charge must come from outside |
| 10 | no field-level change log, no acting user, no reason code |
| 11 | no price history or versioning — needs our own snapshots |
| 12 | `createDateTime` is date-only (R3), so same-day backdating is undetectable |
| 16 | no package or product entity |
| 18 | detection is solid; the *approved reason* half does not exist |
| 19 | no chart-of-accounts or department master |

Row 3 is partly covered already — clause 1c of `room_assignment_type_validity` compares the stay's
type against the room's actual type — but it cannot distinguish an approved upgrade, so it is not
claimed as control 3.

### On the word "verified"

- **Feasibility-verified against live responses: 20 of 20.** v1 made 14 read-only calls in 2024 and
  September 2026, which is where R9 (a reservation in USD against its own folio in ILS), R11 and
  R12 came from. Documentation review had 4 of 12 risks wrong.
- **Verified as executable and validated: 11 IRs**, each schema-valid, referencing only declared
  vocabulary, running on both providers with identical verdicts.
- **Verified as producing an answer: 5 source controls.** Not 8, which is what criterion 1 asks for.
- **Re-verified against the live API by v2: none.** Every verdict this engine has produced comes
  from captures — real responses, but taken in 2024 and September 2026.

**Headline: 10 of 21 rows implemented (100% of what was rated buildable), 5 reaching real verdicts,
0 re-verified live.**

**Evidence:** `miniHotelLegacy/Hotel Controls.docx` (extracted with `zipfile` + regex over
`word/document.xml`, 20 controls); `miniHotelLegacy/MiniHotel_Controls_API_Feasibility.csv`
(21 rows, `Verifiable` and `What's missing` columns read in full); `source_control` read from all
11 files in `spec/ir/`; and every control RUN against `sandbox2026`, `sandbox2024` and the
2024-08-14 instant through `hotelcontrols.runner.run` to measure which reach `coverage.concluded`.
The mapping table above is generated, not asserted.

**Status:** answered

---

## Q4 — 2026-09-09

**Q:** "│ Re-verified against the live API by v2" 0 calls,is this mean we currently verfired by their test api provided, I think demo.... and not via their mainnet(production API)? And is their mainnet production API free? How to get the crednetial(u can search their website)

**A:**

### Yes — sandbox only, never production

Every byte of evidence in this repository came from `sandbox.minihotel.cloud`. v1's probe script
says so on the line that sets the host, and names the other one:

```python
BASE = "https://sandbox.minihotel.cloud"   # production would be api2.minihotel.cloud
```

Production has never been touched, by v1 or v2.

### Three things could be called "the test API" and only one of them is MiniHotel's

| | what it is | have we called it? |
| --- | --- | --- |
| **MiniHotel sandbox** (`sandbox.minihotel.cloud`) | A real server of theirs, the real API, with credentials MiniHotel publishes openly in its own documentation examples | **Yes** — 14 read-only calls, by v1, in 2024 and September 2026. Every fixture is one of those responses, pseudonymised |
| **MiniHotel production** (`api2.minihotel.cloud`) | Real hotels' live data | **Never** |
| **DemoPMS** | *Ours.* A fictional second PMS with no server at all, generated by transcoding the MiniHotel captures field by field, gaps included | Nothing to call. It exists to prove the boundary is real |

So DemoPMS is not MiniHotel's demo — it is our own invention, and it is offline by construction.

### What "0 calls by v2" means precisely

Narrower than it sounds, and worth being exact about. It means **the v2 engine's own transport has
never made a call at all** — not to production, and not to the sandbox either. The 14 captures were
made by v1's `curl`-based scripts. The transport built in slice 11 has been exercised only against
injected dialers, and it refuses to arm inside a test process by design.

That is the gap the pending three-call probe closes, and it is why the probe matters: it verifies
*the transport* as much as it refreshes the findings.

### Is production free?

**MiniHotel publishes no pricing for API access, and I could not verify cost.** What their
documentation does say, quoted exactly:

> "Production credentials will be provided upon completion of the staging and testing phase. Until
> then, please use the sandbox credentials specified on each API page"

> "Before moving to production, it's essential to ensure your IPs are whitelisted with us"

Three APIs are documented — ARI API, Content & Data API, Reverse API. No rate limits, no fees and
no partner-certification process are stated anywhere I could reach. Their developer and FAQ pages
return HTTP 403 to an automated fetch, so this is what the public documentation portal says and
nothing more. **Treat "is it free" as unanswered:** the absence of a published price usually means
it is a commercial conversation rather than a self-serve signup, but that is an inference and not a
fact.

### How credentials are obtained — and the part that matters more

**Sandbox:** nothing to request. The credentials are printed on MiniHotel's own API reference pages,
which is where v1's came from.

**Production:** complete the staging and testing phase, get your IPs whitelisted, and MiniHotel
issues them. That is a conversation with their technical support, not a form.

**But the important point is that we probably should not want production access, and certainly not
yet.** Three reasons:

1. **Production is a real hotel's live guest data.** This engine is read-only, permanently, but the
   correct target for *verifying controls* is the sandbox — refreshed. Nothing about a control's
   logic is better tested against real guests.
2. **Production credentials are per-property, and they are the property's to give.** When a real
   customer is onboarded, that hotel authorises access to its own data. It is not a key we obtain
   once and reuse — which is also why `TenantConfig` is per-property data and credentials come from
   the environment keyed by provider (F15).
3. **The exposure changes.** Real guest PII is a GDPR question rather than a style one (D6), R8
   applies to a live property rather than a shared sandbox, and IP whitelisting means the machine
   that runs it matters.

**The right sequence:** refresh the sandbox with the three calls already planned → build a pilot
with a real property → that property authorises production access. Step one is waiting on approval
today; step two is a commercial conversation, not an engineering one.

What production *would* eventually add for verification is worth naming, because it is not nothing:
real data volumes, real status codes in the wild — which would settle `OK4` and `WL` empirically
rather than by asking — and real error behaviour, which is still unobserved (issue #16 classified
failures by status code, which needed no observation; what their error *bodies* look like stays
unguessed until one is seen).

**Evidence:** `miniHotelLegacy/verify_api.py:37,59` and `probe_checkouts.py:37` for the hostnames;
`fixtures/minihotel/index.json` and `spec/providers/minihotel.json` for what the captures were taken
against. The quotations are from `minihotel.readme.io` fetched 2026-09-09. `minihotel.io/developers/`
and `minihotel.io/faq/` both returned HTTP 403 to an automated fetch and were **not** read — so the
pricing question is unanswered rather than answered "free". Nothing here was verified by making a
call.

**Status:** answered in part — `open — see docs/open-questions.md §1.9` for whether this should ever
touch a production PMS, and whose credentials those would be
