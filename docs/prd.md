# PRD — Hotel Control Rule Engine, v2

> v1 lives in `miniHotelLegacy/`. It proved the architecture and shipped one working control.
> This document specifies what v2 must be, and it is written to be **falsifiable**: every success
> criterion below is a thing that either happens on screen or does not.

---

## 1. Problem

Hotel groups run governance controls — *"no checkout with an open balance"*, *"no reservation on an
out-of-service room"*, *"no duplicate OTA booking"*. Today these are checked by hand, per property,
or not at all.

Three things make this hard, and only the first is obvious:

1. **The checks are the same everywhere; the systems underneath are not.** A group may run
   MiniHotel at three boutique properties and Mews at the flagship, and still want one answer.
2. **Most controls are written as *"X must not happen **unless approved***", and no PMS records the
   approval.** MiniHotel exposes no acting user, no reason codes, no audit trail. A system that
   guesses at the approval half manufactures confidence, which is worse than answering nothing.
3. **Evidence costs money and goodwill.** A folio takes one API call per reservation and there is no
   bulk endpoint. An unbounded control is an unbounded number of calls against someone else's
   server, and the vendor has asked not to be hammered.

## 2. What we are building

A control engine that sits **above** the PMS.

```
  hotel writes a rule in English
            ↓  compiler
  PMS-neutral Control IR  ── validated against a canonical vocabulary
            ↓  evidence layer
  evidence resolved from whichever PMS the property runs, within a call budget
            ↓  evaluator
  PASS · FAIL · UNKNOWN · EXCLUDED, each carrying the evidence that produced it
            ↓
  a page, an API, a run history, and a readiness report per control
```

The rule never names a PMS. A mapping layer translates canonical field names per provider, so one
control runs everywhere and **a new PMS is a new mapping file, not a change to any rule**.

## 3. Who it is for

| User | Needs |
| --- | --- |
| Group finance / internal audit | Continuous assurance that controls hold, with an auditable trail per violation and a history to trend |
| Property front-office manager | A short, trustworthy list of things to fix today — and silence when there is nothing |
| Commercial / integrations | To know which controls a given PMS can actually answer, so integrations are driven by customer demand rather than roadmap guesswork |

## 4. Why UNKNOWN is a first-class result

This is the product's central design commitment and it is inherited unchanged from v1.

The engine returns **three answers and one non-answer**:

| | Meaning |
| --- | --- |
| **PASS** | Everything required is known and the rule holds |
| **FAIL** | Everything required is known and the rule is violated |
| **UNKNOWN** | We do not have enough evidence to say. Carries a reason and the fields that are missing |
| **EXCLUDED** | The control does not apply to this record. Not an answer — the control has no opinion |

`EXCLUDED` is separate from `PASS` on purpose: a run over a hundred reservations where ninety were
out of scope must not report *"90 passed"*. A compliance number inflated with records nobody checked
is worse than no number.

UNKNOWN turns a limitation into a product path — *"connect your housekeeping system to enable this
control"* — and it is the reason §7's readiness report exists.

**The rule that outranks every other requirement in this document: never widen a verdict.** If
evidence is missing, the answer is UNKNOWN. Turning an UNKNOWN into a PASS to make a test go green,
a number look better, or a demo look complete defeats the entire product.

---

## 5. What v2 must do that v1 did not

v1 met all seven of its own success criteria. This section exists because those criteria measured
one control, and the review in `old-codebase-improve.md` measured all ten.

**Measured baseline: of the ten controls v1 ships, exactly one ever produces a PASS or a FAIL.**
Two are blocked, one excludes 100% of records, and six return UNKNOWN for 100% of records. Every one
of those failures traces to one of three capabilities that were scoped out of the demo.

| Gap | Consequence measured in v1 | v2 requirement |
| --- | --- | --- |
| No **reference stage** (join a record to property-wide data) | 3 controls return 111 UNKNOWN out of 111 records | Declarative reference sets, fetched once per run, joined by canonical key |
| No **cross-record evaluation** | Duplicate detection returns 0 answers while the fixtures contain a known real duplicate pair | Population-level assertions: `count_lte`, `aggregate`, and interval operators |
| No **record projection** for composite entities | 2 controls blocked against every evidence set | Records assembled by declared projection, or blocked *per control* with a named reason |
| No signal that a control **concluded nothing** | 28 EXCLUDED / 0 FAIL renders identically to a clean bill of health | Every run carries a coverage verdict; `evaluated == 0` is reported as such, never as four zeroes |
| No **natural-language stage** | Stage 1 of the specified six-stage pipeline absent | Deterministic grammar compiler, with an LLM adapter behind the same validation gate |
| No **readiness report** | Nothing tells a customer which controls their PMS can answer | `readiness(control, provider)` in the API and on the page |
| **One provider** | The PMS-agnostic thesis is asserted, never executed | A second provider, offline, speaking a different wire format |
| Regex-over-raw-XML mapping | Reordering two XML attributes silently turns a known date into UNKNOWN | Structured parsing; attribute order and entity escaping cannot affect a verdict |
| `float` money, naive local dates | Latent: a reconciliation control cannot be trusted to the cent | `Decimal` money; all dates resolved through a property clock |

---

## 6. Scope

### In scope

- **Eleven controls, all executable**, covering source controls 1a–1c, 1d, 2, 4, 6 (split in two),
  9, 13, 14, 15 and 20 from `Hotel Controls.docx`. "Executable" means the engine reaches a real
  verdict or states a specific, named reason why it cannot — never a silent nothing.
- **Two providers**: MiniHotel (XML over HTTP, real captured fixtures) and DemoPMS (JSON, fictional,
  offline) — the second existing to make the portability claim testable.
- **The full six-stage pipeline** from `control_rule_architecture.docx` §17, including stage 1.
- **Execution semantics**: trigger classification and freshness computed as pure functions.
- **Persistence**: run history in SQLite, re-readable without spending a provider call.
- **A web surface**: server-rendered, no JavaScript, every verdict traceable to its fields.
- **An opt-in transport** with rate limiting, retry and a fixture record mode — off by default and
  unreachable from a test.

### Explicitly out of scope

Named here so nobody mistakes thin for unfinished.

- **Mews** — designed for, mapped for when credentials exist, not verified. DemoPMS stands in.
- **Writing to a PMS.** The hotel types controls, not commands. Read-only, permanently.
- **A running scheduler daemon.** The scheduling *decision* is built and tested; the loop is not.
- **Authentication and multi-user access.** Single-operator demo.
- **Webhook ingestion.** The IR declares its events; nothing subscribes yet.
- **Reading unstructured free text as evidence** — see open question 3.
- **A rule editor UI.** Controls arrive as sentences through the compiler or as IR files.

---

## 7. Success criteria

Each is a test, an observable behaviour, or a number. None is a matter of opinion.

| # | Criterion | How it is proven |
| --- | --- | --- |
| 1 | **At least 8 of the 11 controls reach a PASS or a FAIL on captured evidence**, and every control that does not names its specific blocker on screen | A test that runs all controls × all evidence sets and asserts the outcome distribution |
| 2 | All four outcomes are reachable from **captured** evidence, and UNKNOWN is distinguishable from FAIL by hue, border **and** wording | End-to-end test plus a rendering test that strips colour |
| 3 | Every verdict traces to the fields that produced it — name, value, unit, provenance, and the reason for any gap | `Verdict` cannot be constructed without evidence; asserted structurally |
| 4 | **A run over N records never exceeds `1 + R + N` provider calls**, where R is the number of reference sets — asserted by counting invocations, not assumed | Call-count tests at the evidence layer and again end-to-end |
| 5 | **No PMS identifier appears above the provider layer** — no endpoint, field path, wire format or vendor name | A grep test over the source tree, strict enough to catch prose |
| 6 | **A twelfth control is a spec change, not a code change** | A control added in a test fixture directory runs end-to-end with no import touched |
| 7 | **The same IR yields the same verdicts through two providers** over the same logical hotel | A portability test across MiniHotel and DemoPMS fixtures |
| 8 | **A run that concluded nothing says so.** A run where `PASS + FAIL == 0` never renders as a clean result | Rendering test on the 100%-excluded case |
| 9 | **A restricted-English sentence compiles to a valid IR**, and an unsupported sentence is rejected naming the missing vocabulary | Compiler tests, offline, no model in the loop |
| 10 | **Readiness is reported per control per provider** — "MiniHotel 4/5 fields · DemoPMS 5/5" | API and page test |
| 11 | **The whole system runs offline with no runtime dependencies beyond the standard library**, and no test can reach the network | CI runs with networking asserted unused; transport is opt-in via environment only |
| 12 | **Every slice is green in CI before the next opens** | GitHub Actions required on every PR |

### Anti-criteria — things that would mean we failed even if everything above passes

- A verdict of PASS produced from evidence that was not actually established.
- A number on screen without its unit or its currency.
- A control that silently applies to zero records and reports success.
- A test that passes because a fixture was edited to match the code.
- An UNKNOWN without a reason a hotel could act on.

---

## 8. How we know what is possible

Every capability claim traces to a **live sandbox response saved as a fixture**, not to
documentation. In v1, documentation review got 4 of 12 risks wrong, and two further claims survived
review until the actual records were counted. That method is inherited: **if the documentation and a
captured response disagree, the response wins.**

Of the 20 controls in `Hotel Controls.docx` against MiniHotel: 6 are confidently buildable today,
3 more once a single unverified mechanism is confirmed on a real property, 9 need a policy decision
about the approval half, and 2 are structurally blocked by entities the API does not expose. v2 does
not change those numbers — it makes the buildable ones actually work, and makes the unbuildable ones
say precisely what is missing.
