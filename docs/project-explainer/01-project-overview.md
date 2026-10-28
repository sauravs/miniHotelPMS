# 1 · Project Overview — the whole thing, in plain English

> **Who this is for:** anyone who wants to understand what this project *is* before understanding
> how it *works*. No code is shown until §7, and even then only to point at it.

---

## 1. Start with the hotel, not the software

A hotel group owns four hotels — three small boutique properties and one flagship, the large
well-known one the brand is built around. Somewhere in a compliance binder there is a list of rules
that are supposed to always hold:

> *"A guest cannot check out while still owing money."*
> *"A room that is out of service must not have anyone arriving into it."*
> *"Two live bookings must never share the same Booking.com confirmation number."*

Nobody disputes these rules. The problem is **nobody can tell you whether they held yesterday.**

Today the answer is one of three things, all bad:

1. **A night manager checks by hand**, at 2am, on the properties they remember to check.
2. **A monthly spreadsheet**, assembled after the money has already left.
3. **Nobody checks at all**, and the group finds out when a guest complains or an auditor asks.

So the product is easy to state: **a machine that continuously checks the compliance binder and
tells you, with receipts, which rules held and which did not.**

Three things make that much harder than it sounds, and only the first is obvious.

### Obstacle 1 — the four hotels run different software

The three boutique properties run **MiniHotel**. The flagship runs **Mews**. Both are Property
Management Systems — a PMS is the software that actually holds the bookings, the rooms and the
money, and every hotel has one.

Nobody plans a mixed estate like this; it accumulates. The flagship has the most rooms, the most
staff and the most revenue, so at some point it was worth putting on a more capable system, while
the small ones stayed on something cheaper. That is the normal shape of a hotel group.

**The two systems describe the same facts and agree on nothing.** Here is one real reservation —
`007004348`, captured from a live sandbox and used throughout this project — as each system returns
it.

MiniHotel answers in **XML**:

```xml
<Booking Minihotel_reservation_id="007004348" createDateTime="07/07/2026" Status="OUT">
  <RoomStays><RoomStay roomNumber="301" roomTypeID="Twin" mealStatus="BB"/></RoomStays>
  <PrimaryGuest><Name givenName="Dmitri" surname="Almeida"/></PrimaryGuest>
  <ResGlobalInfo>
    <Timespan arrival="06/07/2026" departure="07/07/2026"/>
    <Total AmountAfterTaxes="124.00" CurrencyCode="USD"/>
  </ResGlobalInfo>
</Booking>
```

The other system answers in **JSON**:

```json
{ "booking_ref": "007004348",  "state": "DEPARTED",
  "arrival":   { "date": "06 Jul 2026", "time": "14:00" },
  "departure": { "date": "07 Jul 2026" },
  "total":     { "amount": "124.00", "currency": "USD" },
  "guest":     { "first_name": "Dmitri", "last_name": "Almeida" },
  "stays":   [ { "room_no": "301", "room_class": "Twin", "board": "BB" } ] }
```

Dmitri Almeida, room 301, a Twin room, 124 USD, arrived 6 July, departed 7 July. **Identical facts.
Not one identical label.** Five differences matter, and they get worse as you go down:

| | MiniHotel | The other system | Why it matters |
| --- | --- | --- | --- |
| **The format** | XML — `<angle brackets>` | JSON — `{braces}` | Not a small difference. Code that reads one cannot read the other *at all* |
| **What a booking is called** | `Booking` | `booking` | To a computer, capital `B` and small `b` are different words. Code hunting for the wrong one finds nothing — and "no reservations found" looks exactly like a quiet hotel |
| **Where the departure date lives** | `Booking` → `ResGlobalInfo` → `Timespan` → `@departure`<br>*four levels deep, in an attribute* | `booking.departure`<br>*one level down* | The same question — *when did they leave?* — needs completely different directions for finding the answer |
| **How a date is written** | `07/07/2026` | `07 Jul 2026` | And the nasty part: MiniHotel uses **three** date formats inside its own API — `07/07/2026` on bookings, `20260707` on folio lines, `2026-07-07` on availability. You cannot write one date reader even for one vendor |
| **Where the money is** | `Balance/TotalDebit` — and the **currency is stored somewhere else entirely** | `ledger.balance.amount`, with `currency` beside it | This row can lose real money. See below |

That last row is worth looking at properly, because it is the one that bites hardest. On this
booking MiniHotel reports:

```xml
<Total AmountAfterTaxes="124.00" CurrencyCode="USD"/>      the reservation:  124 USD
<Currency>ILS</Currency> <TotalDebit>-490.75</TotalDebit>   the folio:     -490.75 ILS
```

Two different currencies, on one booking, with the amount and its currency sitting in separate
parts of the response — and **no exchange rate anywhere in the API**. The other system keeps them
together, as `{"amount": "-490.75", "currency": "ILS"}`. Miss that and you compare 124 against
−490.75 and get a confident, meaningless answer.

### Why this is a design problem and not a plumbing problem

The **rule** — *"no checkout with money owed"* — is the same sentence at all four hotels. The
**plumbing** underneath is different at each. So where you write the rule decides everything.

It is the difference between two recipes:

> ❌ *"Add what's in the third drawer down, left of the sink."*
>
> ✅ *"Add one tablespoon of salt."*

The first recipe works in exactly one kitchen. The second works in every kitchen, because each cook
already knows where their own salt is.

A rule that says **"read `Balance/TotalDebit`"** is the first recipe. It runs at the three MiniHotel
properties and is meaningless at the flagship — so you would write a second version for Mews, a
third for the next system, and until you do, those hotels are simply not being checked. One rule
becomes four rules, three of which do not exist yet.

A rule that says **"read `folio.balance_due`"** is the second recipe. `folio.balance_due` names no
PMS; it is a neutral word this project made up. You write the rule once, and each system gets a
small translation table saying where *its* balance lives.

Those translation tables are real files you can go and read: `spec/providers/minihotel.json` and
`spec/providers/demopms.json`. The list of neutral words is `spec/canonical_fields.json` — 53 of
them. And the rule that a control may **never** mention `TotalDebit` is what this codebase calls
the **canonical boundary**, which §7 comes back to.

### Obstacle 2 — most rules have a half nobody records

Read the compliance binder carefully and almost every rule has an escape clause:

> *"A reservation cannot be closed with an outstanding balance **unless an approved exception
> exists**."*

The first half is answerable — the balance is a number in the system. The second half usually is
not: MiniHotel exposes **no acting user, no reason codes, no audit trail.** There is nowhere in the
API that records "the duty manager approved this."

This is the single most important fact about the product. A system that guesses at the approval
half — that decides "well, probably nobody approved it, call it a violation" — **manufactures
confidence.** It generates a queue of accusations that a front-office manager will disprove three
times and then stop reading forever.

### Obstacle 3 — looking costs money

Checking a guest's balance takes **one API call per reservation**. There is no bulk endpoint. If a
control is written carelessly and asks about every reservation in the system, it makes thousands of
calls against a server the hotel group does not own, belonging to a vendor who has explicitly asked
integrators not to hammer it.

> **In one line:** the rules are the same everywhere, the systems are not, the evidence is often
> missing, and looking has a price.

---

## 2. The idea, as an analogy

### The building inspector who only reports what they actually saw

Imagine hiring a building inspector for a group of buildings. A **bad** inspector walks in, cannot find
the fire-door certificate, assumes it does not exist, and writes **VIOLATION**. You spend a week
proving them wrong. Next time, you ignore their report.

A **good** inspector writes three different things:

- **"Fire doors: compliant"** — I looked, I found the certificate, it is valid. *(PASS)*
- **"Fire doors: non-compliant"** — I looked, I found the certificate, it expired in March. *(FAIL)*
- **"Fire doors: cannot certify — the certificate is held by your managing agent, whom I have no
  access to. Give me access and I will answer this."** *(UNKNOWN)*

And a fourth, quieter one:

- **"Fire doors: not applicable — this building has no fire doors."** *(EXCLUDED)*

That third answer is the entire product. **UNKNOWN is not a failure of the inspector; it is the
inspector being honest about the limits of what they were shown** — and it comes with an
actionable next step ("give me access to the managing agent"), which turns a limitation into a
sales conversation: *"connect your housekeeping system and this control starts answering."*

The fourth answer matters just as much, and for a subtler reason. If you fold "not applicable" into
"compliant," a report over 100 buildings where 90 had no fire doors reads **"90 passed."** That
number is worse than no number, because it is a compliance figure inflated with buildings nobody
inspected.

### The translator at the negotiating table

The rule is written once, in a neutral working language — never in MiniHotel's dialect and never in
Mews's. Each PMS gets an **interpreter** who translates in both directions.

```
        THE RULE (neutral)                        THE INTERPRETERS
  "reservation.status is checked_out"    ┌──→  MiniHotel: read Booking@Status, then
  "folio.balance_due at most 0"          │              map this hotel's code "OUT"
                                         │
                                         └──→  DemoPMS:  read booking.state, then
                                                        map this hotel's code "DEPARTED"
```

**Adding a ninth property on a ninth PMS means hiring a ninth interpreter. It does not mean
rewriting the rule.** In this codebase that promise has a name — the *canonical boundary* — and it
is not a matter of discipline: a test greps the entire source tree for 28 PMS-specific identifiers
and fails the build if any appears above the interpreter layer. It is strict enough that it has
caught the word "XML" in a comment.

### The taxi meter

Every API call is a fare. Before the trip starts, the engine declares where it is going and what
that will cost:

> "This control asks about reservations that departed in the last 24 hours. That is **1 call** to
> get the list, plus **1 call per reservation** to get each balance."

If the meter is about to exceed the budget, the run **stops and says so.** It does not quietly
check the first hundred and report "no violations found" — because *"I checked 100 of 4,000 and
found nothing"* and *"nothing is wrong"* are different sentences, and only one of them is true.

### The DVD player and the discs

The engine is a **player**. The eleven controls are **discs** — JSON files in `spec/ir/` that the
engine reads at runtime.

Nothing in the engine's source code knows what "the checkout balance control" is. It is one file
among eleven. **A twelfth control is a new file, not a new branch.** This is tested: a control that
has never existed is compiled from an English sentence, dropped into a temporary directory, and run
end-to-end on both providers *without a single import being touched.*

---

## 3. The three source documents, and what each one demanded

Everything in this repository traces back to three inputs from the project owner.

### `initial_requirement.md` — the original ask

> *"These are a few hotel rules that hotels like to check against various systems they are using.
> Look at only MiniHotel. The first task is to figure out how many of them can be verified using
> the APIs they give... create a spreadsheet of rules and the required APIs."*

That produced `miniHotelLegacy/MiniHotel_Controls_API_Feasibility.xlsx`. Scope was: *investigate
and report.*

### `Hotel Controls.docx` — the twenty rules

A table with twenty governance controls. Each row is a name, a feasibility marker (🟢/🟡) for
MiniHotel and Mews, and one example rule written in an auditor's English:

| # | Control | Example rule |
| --- | --- | --- |
| 1 | Room assignment validity | *A reservation may only be assigned to an active room of an allowed room type.* |
| 2 | OOO / blocked room protection | *A room with an active OOO/block period must not have an arriving reservation.* |
| 4 | Room capacity compliance | *Guests assigned to a room may not exceed the configured occupancy capacity.* |
| 6 | Open balance at checkout | *A reservation cannot be closed with an outstanding balance unless an approved exception exists.* |
| 13 | Inactive room assigned to future stay | *No future reservation may reference an inactive/decommissioned room.* |
| 14 | Duplicate channel reservation | *Two active reservations must not share the same OTA/channel confirmation number.* |
| 15 | Required reservation fields | *Every reservation in rate category X must contain the required guest/company/payment information.* |
| 20 | Resource occupancy consistency | *A resource's occupancy state must be consistent with the reservations assigned to it.* |

The document speaks **auditor**. The API speaks **schema**. Translating between the two *is the
work* — and it is not mechanical. "Configured occupancy capacity" sounds like a number you look up.
It turns out 23 of the property's 28 rooms report that number as `0`, meaning *nobody ever
configured it* — which is a completely different fact from *"this room holds zero people."*

### `control_rule_architecture.docx` — the design brief

Twenty-five sections of design intent from the technical lead. It is the reason this codebase looks
the way it does. The clauses that bind:

| § | What the brief demanded | Where it lives now |
| --- | --- | --- |
| §1 | **The rule must not contain PMS-specific information.** Not `mews.reservation.paymentState == ...` | The canonical boundary, enforced by `tests/unit/test_canonical_boundary.py` |
| §2 | The customer types a sentence and immediately sees the compiled control **plus field availability** — *"MiniHotel: 4/4 fields available"* | `hotelcontrols/compiler/` + `runner/readiness.py`, and since slice 13 the text box itself at **`/compose`** — see §10 |
| §4, §22 | **Logic and execution are separate objects.** *"The logic doesn't care whether we check every 5 minutes or every hour"* | The IR's `assertion` vs its `execution` block |
| §5–§12, §23 | Four trigger classes (event / time-window / periodic / batch), plus a **freshness requirement** per control | `hotelcontrols/runner/scheduling.py`, as pure functions |
| §13 | Canonical field → per-provider *endpoint + path + transformation* | `spec/providers/minihotel.json`, `spec/providers/demopms.json` |
| §14 | **PASS / FAIL / UNKNOWN.** *"We must not fail the reservation"* for missing evidence | `hotelcontrols/kernel/outcome.py` — plus a fourth, EXCLUDED |
| §15–16 | **Readiness:** *"Control readiness: 1 of 2 evidence sources connected"* | `hotelcontrols/runner/readiness.py` |
| §17 | A six-stage pipeline. **Never LLM → executable JSON directly.** *"That's risky"* | `hotelcontrols/compiler/grammar.py` emits data; `spec.validate` is the gate. A model, when used, sits one step *before* stage 1 and drafts a **sentence** |
| §18 | Ambiguity must be **reported, never resolved.** *"LLM can interpret language, but it cannot invent hotel policy"* | The grammar refuses ambiguous operands by name, and a proposer that cannot commit **asks a question instead**, with no button to run anything |
| §20 | Every violation must be **explainable with an evidence table** | `Verdict` cannot be constructed without evidence — a structural guarantee |
| §24 | The compiler produces a **population query, not an IF statement** | `hotelcontrols/evidence/population.py` |

---

## 4. What was actually built (and what was measured)

There were two attempts. Both are in this repository, on purpose.

### v1 — `miniHotelLegacy/`

Four "silos," 152 passing tests, one control working end-to-end. It met **all seven of its own
success criteria.**

Then somebody ran all ten of its controls against all three of its evidence sets and counted.

> **Of the ten controls v1 shipped, exactly one ever produced a PASS or a FAIL.**
> Two were blocked. One excluded 100% of records. Six returned UNKNOWN for 100% of records.

Every success criterion was green. Nine tenths of the product answered nothing. That gap — between
*"all criteria met"* and *"the thing does not work"* — is the reason v2 exists and the reason its
scorecard is written the way it is.

### v2 — the engine

Twelve slices, then three more (compose, a UI/UX pass, and a React UI). Each was a branch → PR →
green CI → squash-merge. v2 closed on 2026-10-09 with 1,996 tests, eleven controls, two providers,
eight layers and two screens, and 11 of its 12 success criteria met.

### v3 — what happens after a verdict

Nine more slices (16–24), planned and built between 2026-10-09 and 2026-10-11, then a run of fixes
that closed on 2026-10-13. They are §11 below. Every number for the repository as it stands, with
the command that produced it, is in the [README's table](README.md#what-is-true-as-of-this-writing).
This document does not repeat those numbers.

### The honest scorecard

Criterion 1 asked that **at least 8 of the 11 controls reach a PASS or a FAIL** on captured
evidence. Here is what happens when you run all eleven against the **covering capture**,
`sandbox2026cover`: the hotel as of 8 July 2026, with every question the controls ask on record.
This is output produced by running the engine on 2026-10-13, not copied from a document:

| Control | Result | Concludes? |
| --- | --- | --- |
| `checkout_money_owed` | 2 PASS | ✅ |
| `checkout_unrefunded_credit` | 1 PASS, **1 FAIL** | ✅ |
| `duplicate_channel_reservation` | 8 PASS, 28 UNKNOWN, 114 EXCLUDED | ✅ |
| `inactive_room_future_stay` | 87 PASS, 41 UNKNOWN, 244 EXCLUDED | ✅ |
| `room_assignment_type_validity` | 87 PASS, 41 UNKNOWN, 244 EXCLUDED | ✅ |
| `resource_occupancy_consistency` | **BLOCKED**: this capture's occupancy covers a week of August 2024, not July 2026 | ❌ |
| `ooo_room_protection` | 28 EXCLUDED | ❌ |
| `room_assignment_active_room` | 372 EXCLUDED | ❌ |
| `room_capacity_compliance` | 128 UNKNOWN, 244 EXCLUDED | ❌ |
| `rate_room_category_consistency` | 128 UNKNOWN, 244 EXCLUDED | ❌ |
| `required_reservation_fields` | 141 UNKNOWN, 244 EXCLUDED | ❌ |

**5 of 11. The criterion is recorded as NOT MET**, in `docs/plan.md`, with the arithmetic.

It is measured **per capture**, because a capture can only answer the questions it recorded:

| Capture | Concludes | Which |
| --- | --- | --- |
| `sandbox2026`, the demo's default (captured 2026-09-08) | **2 of 11** | the two checkout controls. The seven that ask about arrivals or creations are **refused**, because this capture only ever asked about departures |
| `sandbox2026refresh` (captured 2026-10-10) | **1 of 11** | occupancy, for the first time (31 PASS, 4 UNKNOWN). The checkout controls stop at UNKNOWN, because no folio was re-taken |
| `sandbox2026cover` (captured 2026-10-13) | **5 of 11** | the table above. The only figure measured from the right evidence |

DemoPMS gives the same answer on every row.

That is the point. Every one of the six shortfalls traces to a fact about *this property* or *this
vendor*, not to a bug:

- **No room in this hotel has ever had an out-of-service window set.** It was checked again live
  on 2026-10-10. So two controls correctly apply to nobody. Reporting "compliant" would be
  reporting a clean bill of health for a mechanism nobody has ever seen working — which is exactly
  what v1 did.
- **23 of 28 rooms report capacity `0`**, meaning unconfigured. Still true on 2026-10-10. Reading
  those as real zeroes would produce a wall of false FAILs.
- **A rate code and a price-list code are different key spaces** in MiniHotel, so no endpoint can
  resolve the mapping at all.
- **This hotel has not decided which rate codes count.** Its setting says *not decided*, which is
  a different fact from *none*, so the "required fields on rate X" control answers UNKNOWN and names
  the missing decision. Nobody can honestly decide it for a vendor's test hotel, because on the
  covering capture a list **would** move the control. A trial list of one code, `Tourist-BB`, tried
  in memory and never committed, gives 15 PASS and 56 FAIL. That is exactly why the list must come
  from a real hotel.
- **The only July 2026 occupancy was captured separately**, in the refresh. Occupancy concludes
  there and is refused everywhere else.

**It was once written that three of those six would move on a conversation. Measured, one does**:
one sentence from the vendor explaining what the status codes `OK4` and `WL` mean. Those two codes
cover **77 of the 526 reservations this project has seen** (about one in seven; it was 44 of 217
before the 2026-10 captures). The two rate-code controls need a conversation *and* a capture with
room prices. The capture now exists. The conversation needs a real property.

> A number that went **down** when a bug was fixed is the most trustworthy number in this document,
> and it has happened twice. `resource_occupancy_consistency` used to count towards criterion 1,
> answering questions about July 2026 from occupancy captured in August 2024. Issue #9 fixed that,
> and the score fell from 6 to 5. Then issue #71 found that three more controls had been answering
> arrival questions from a capture that only recorded departures, so they saw part of their
> population and presented it as the whole. On that capture the score fell from 5 to 2. The 5 came
> back only when two new live calls, each approved by the owner, recorded the questions those
> controls actually ask.

---

## 5. Business idea → technical artefact

This is the mapping table. Every business commitment on the left is a real, findable thing on the
right.

| The business promise | Why it matters commercially | Where it lives in code | How it is *enforced* (not merely intended) |
| --- | --- | --- | --- |
| "One rule runs on any PMS" | A new customer on a new PMS is an integration, not a rebuild — this is the whole thesis | `hotelcontrols/providers/` — one adapter per PMS behind a shared `Provider` protocol | `tests/unit/test_canonical_boundary.py` greps the tree for 28 PMS identifiers from **both** providers and fails if one appears above the provider layer |
| "We never guess" | One fabricated violation costs you the front-office manager's trust permanently | `kernel/value.py` — a `Value` is `known` or `unknown(reason)`, and an unknown **raises** if you try to compare it | `Value.comparable_pair()` raises `UnknownValue`. The obvious `PASS if v == 0 else FAIL` cannot compile a wrong answer |
| "Not-applicable is not a pass" | A compliance number inflated with unchecked records is worse than no number | `kernel/outcome.py` — `EXCLUDED` is a distinct fourth outcome; `Outcome.is_answer` is False for it | `runner/coverage.py` computes `evaluated = PASS + FAIL`; a run with 0 renders as *"concluded nothing"* with no count tiles |
| "Every answer has receipts" | Audit is the product. An unexplained verdict is an anecdote | `kernel/verdict.py` — `Verdict(outcome, reason, evidence[])` | The constructor **raises `NotAuditable`** if evidence is empty or the reason is blank. You cannot build a verdict without proof |
| "We won't hammer your vendor" | The vendor asked. Goodwill is a dependency | `evidence/budget.py` — a `CallBudget` counting every invocation | Cost is asserted as `1 + R + N` by **counting invocations** in tests, not assumed. Exceeding it **raises and stops the run** rather than truncating |
| "Money is money" | A reconciliation control must be trustworthy to the cent | `kernel/money.py` — `Decimal` + a mandatory currency | Two amounts in different currencies **refuse to compare** (they raise). Floats are rejected at construction |
| "A hotel can state a rule in its own words" | §2 of the design brief, and the demo people actually ask for | `compiler/sentences.py` + `tools/proposers/` | The model drafts a **sentence**, which the deterministic grammar then compiles. A composed rule carries `confidence == 1.0` because the *parse* was exact; a bad field name is refused **by name** |
| "Adding a control is a config change" | Sales can promise a new control this week | `spec/ir/*.json` — read at runtime | A never-before-seen control is compiled from a sentence into a temp directory and run end-to-end on both providers, no import touched |
| "We tell you what your PMS can answer" | Integration roadmap driven by customer demand, not by guessing | `runner/readiness.py` | Rendered per control per provider on the index page of **both** screens: *"MiniHotel 4/5 fields · DemoPMS 5/5"* |
| "The answer reads the same on any screen" | A second screen that rounds a number, drops a currency or shows four zeroes is a second product with weaker promises | `ui/` (React), a client of the JSON API | The UI's own suite re-proves criteria 2, 3, 8 and 10. The engine's **required** suite bans parsed money, PMS names, injected HTML and requests outside one module anywhere in `ui/` |
| "It runs anywhere" | A demo with an install step is a demo that fails in the meeting | Standard library only: `xml.etree`, `decimal`, `sqlite3`, `http.server`, `zoneinfo`, `json` | `tests/unit/test_stdlib_only.py` walks the tree and asserts the engine contains no outbound HTTP client at all |
| "No test can touch the network" | A suite that needs someone else's server up is not a suite | `providers/transport/` is opt-in, off by default | **Two locks:** an environment variable *and* a refusal to arm while a test runner is loaded. The test that sets the variable is still refused |
| "Every answer names the rule that judged it" *(v3)* | An auditor will ask *"under which version of the rule did this FAIL?"* | `spec/ir.lock.json`, `hotelcontrols/spec/lock.py` | `validate_spec` fails a rule edited without a version bump. Every stored run carries the rule's version **and** a digest of its content |
| "One hotel never sees another's results" *(v3)* | A hotel group is several hotels, and each manager sees their own | `store/`, `web/auth.py` | A structural test fails any query on a hotel-owned table that does not name its hotel. With authentication on, a **signed** identity overwrites whatever hotel the URL asked for, before any page runs |
| "A violation becomes a task, never an action on the PMS" *(v3)* | Findings nobody acts on are a report, not a control | `actions/` | Only a FAIL raises a task, **once**, however often the control re-runs. A person marks it done or dismisses it. Nothing writes to a PMS, ever |
| "*Not decided* is not *none*" *(v3)* | A hotel that has not chosen its policy must not be judged as if it chose "nothing" | `spec/parameters.json` | A setting the hotel has not decided is UNKNOWN **naming it**. No setting has a default |
| "A guest request is decided by the hotel's table, not by a guess" *(v3)* | Staff act on the answer, and money moves | `guest/`, `spec/guest/late_checkout.json` | Any missing fact or undecided policy is *staff review* naming it, never *approved* or *denied*. No model is reachable from the package, checked over its imports |

---

## 6. How a question actually gets answered

Follow one question all the way through. The sentence a hotel types:

> *"A reservation cannot be closed while the hotel still owes the guest a refund."*

**Stage 1 — Compile.** The sentence becomes an *Intermediate Representation* (IR): structured data
naming only canonical fields. It never becomes executable code — §17 of the brief is explicit that
`LLM → executable JSON` is the risky path. What comes out is inert JSON that then has to survive
validation.

```
  entity:    reservation
  scope:     reservation.status equals "checked_out"
  assertion: folio.balance_due  gte 0
  evidence:  reservation.status, reservation.departure_date,
             folio.balance_due, folio.currency, reservation.currency
```

**Stage 2 — Validate.** Every field name is checked against `spec/canonical_fields.json`. A rule
referencing a field nobody declared is stopped **before it runs**, and the rejection names the
missing vocabulary. Fed the brief's own trick example — *"All VIP arrivals should have an assigned
room that is clean by 2 PM"* — the validator answers with the two canonical fields that do not
exist rather than producing a rule that runs and quietly answers about nothing.

**Stage 3 — Bound the population.** The IR carries a *population query*: "reservations that departed
in the last 24 hours, with status OUT." That is a **bound**, not a verdict — it decides who to look
at, never who passes. Cost declared up front: `1 + N`.

**Stage 4 — Gather evidence.** The interpreter for this property's PMS fetches the list (1 call),
then each folio (N calls), translating everything into canonical values:

```
  <TotalDebit>-490.75</TotalDebit>  +  <Currency>ILS</Currency>
                    ↓
          folio.balance_due = known(Money(-490.75, "ILS"))
```

**Stage 5 — Evaluate.** A pure function — no clock, no network, no PMS — applies the rule in a
fixed order:

```
  scope?       is this reservation checked out?     → EXCLUDED if not
  exception?   is it exempt?                        → EXCLUDED if so
  assertion?   is balance_due ≥ 0?                  → PASS / FAIL
```

At every step the answer may be *"cannot tell"* → **UNKNOWN**.

**Stage 6 — Answer, with receipts.**

```
  FAIL · reservation 007004348
  folio.balance_due is -490.75 ILS, which does not satisfy `gte 0`

  folio.balance_due           -490.75 ILS   ← pms:minihotel/GetReservationBalance
  reservation.status          checked_out   ← pms:minihotel/GetReservationKey
  reservation.departure_date  2026-07-07    ← pms:minihotel/GetReservationKey
  folio.currency              ILS           ← pms:minihotel/GetReservationBalance
  reservation.currency        USD           ← pms:minihotel/GetReservationKey
```

A real guest overpaid by 490.75 shekels and left. That is money the hotel owes back, sitting in a
closed folio where nobody will look for it.

**Stage 7 — a task, since v3.** That FAIL now also becomes **one** pending task in the findings
queue, addressed to *finance* at *medium* severity because that is what the rule declares, and
naming the rule's version. Running the control again does not make a second task. A person closes
it; the engine never does, and it never touches the PMS.

> **Run the identical rule through the completely different JSON provider and every verdict, every
> record id, and the call count are identical.** That is `tests/e2e/test_two_providers.py`, over 11
> controls × 3 dates. The full side-by-side proof is in
> [04-edge-cases.md](04-edge-cases.md) Part B.

Note the last two lines of the evidence table. The folio is in **ILS**; the reservation is in
**USD**; and MiniHotel publishes **no exchange rate anywhere.** Those two lines are carried purely
so a human can see the trap. The rule compares against literal **zero**, which means the same thing
in every currency — which is why this control is safe and why any future version comparing the two
amounts would be invalid without an external FX source.

---

## 7. Seven design commitments, and the failure each one prevents

Every one of these was bought with a specific mistake.

| # | Commitment | The failure it prevents |
| --- | --- | --- |
| 1 | **The canonical boundary is absolute.** Above the provider layer, no endpoint, field path, wire format or vendor name exists | The second PMS becomes a rewrite instead of an adapter. You find out eighteen months in, when a customer asks |
| 2 | **UNKNOWN is a first-class answer with a reason** | The queue fills with accusations the manager disproves, and stops being read. Also: *"connect your housekeeping system"* is a sales path; *"FAIL"* is a support ticket |
| 3 | **EXCLUDED is not PASS** | A run over 100 records where 90 were out of scope reports *"90 passed."* An inflated compliance number is worse than none |
| 4 | **Evidence costs money; the budget raises rather than truncates** | Checking the first 100 of 4,000 and reporting *"no violations"* — a lie assembled from a true statement |
| 5 | **Money carries its currency; a bare number is never money** | A reservation reporting 870 USD meeting its own folio's 3,262.50 ILS in a comparison. This *happened*, on a real record |
| 6 | **Fixtures are evidence and are never edited to make a test pass** | The test suite slowly becomes a description of the code instead of a check on it. v1's hand-written second fixture set drifted exactly this way |
| 7 | **Never widen a verdict** | Everything above. Turning an UNKNOWN into a PASS to make a test green, a number look better, or a demo look finished defeats the entire product. **This rule outranks every other rule in the repository** |

---

## 8. What is deliberately *not* built

Listed so nobody mistakes thin for unfinished. Each is recoverable without reworking what exists.

| Not built | Why | What it would take |
| --- | --- | --- |
| **Mews** | Out of scope by the owner's decision, and credentials do not exist | A directory under `providers/`, a map in `spec/providers/`, a tenant file. Nothing above the provider layer changes — the slice-7 diff is the evidence |
| **A running scheduler** | The scheduling *decision* is the hard part and is built and tested as a pure function | A loop that calls `next_evaluation()` |
| **Webhook ingestion** | IRs already declare their events; nothing subscribes | An HTTP endpoint and a subscription |
| **Writing to a PMS** | Read-only, permanently, and reaffirmed when v3 was planned: the product **advises**. A task is a record a person carries out | Not planned. Ever |
| **A user store, roles, an organisation level** | v3 built the *engine's* half of authentication: it verifies a signed statement of which hotel a request is about. **Who** may sign it is the host product's job (decision D14). The React UI's sign-in is a development stand-in and says so on its own page | The host product's login, signing the same context. The engine does not change |
| **A payment-guarantee control** (card on file) | Every card in every capture is the placeholder `****`: 902 card entries, 855 of them expiring January 2021 (it was 228 when v3 was planned). The control would pass every reservation ever seen (issue #48). **Blocked**, not deferred | One answer from MiniHotel about what that placeholder means |
| **Four of five guest templates**, emailing guest tasks, a React guest view | v3 built one template, `LATE_CHECKOUT`, end to end. The rest are deferred by the owner | Each a decision table the owner approves first |
| **Free text as evidence** | VIP status and manager approvals exist only as Hebrew free text in a remarks field. Whether that counts is [open question 1.5](../open-questions.md) | An extractor that returns a value **only with the exact quotation it relied on**, and UNKNOWN whenever the text is ambiguous |
| **A rule-editor UI** | `/compose` (on both screens) is a chat box, not an editor — it files **drafts** and promoting one is manual. There is no screen for editing a shipped control | A form over the compiler. The versioning such an editor needs exists since v3: an edited rule is a new version, recorded in a lock file |
| **A model anywhere near a verdict** | Decision D10 wired a model to *draft a sentence* (see §10 below). Nothing it produces reaches the evidence layer or the evaluator, and no verdict depends on a model call. v3 kept the same rule for guest requests: no model reads what a guest wrote | Not planned. This one stays out |

---

## 9. Two screens over one engine — the React UI

Since slice 15 there are two ways to *look* at an answer, and they are deliberately not equal.

```
                          the engine  (Python, standard library only)
                                │
               ┌────────────────┴─────────────────┐
               │                                  │
     its own pages                       the JSON API  /api/...
     server-rendered, no JavaScript               │
     http://127.0.0.1:8765/                ui/  (Next.js, React, TypeScript)
     THE AUDIT SURFACE                     http://127.0.0.1:3000/
                                           THE PRODUCT SURFACE
```

**Why a second screen at all.** Two honest reasons, neither of them "React is better". The project
owner reads React more fluently than Python, and a screen you can read is a screen you can trust
and change. And this engine will be patched into a larger product built in JavaScript and Next.js,
so a React screen converges with it where a bespoke Python one would diverge.

**Why the first screen stays.** It needs nothing installed, runs offline, prints, and is what proves
"no runtime dependencies" at the page level. An auditor can open it with nothing but Python.
Retiring it would be a separate, later decision, made on evidence.

**The analogy: a second dashboard on the same instrument panel.** The second dashboard can be
prettier, but it must show the same readings. If it rounds a number, drops a unit, or shows a
reassuring zero where the instrument said *no reading*, it is lying with better typography. So the
React UI is held to the same promises as the engine's own pages, and **re-proves them in its own
test suite**:

| The promise | How the React UI keeps it |
| --- | --- |
| UNKNOWN never looks like FAIL | Hue, border **and** wording. The wording is checked with all styling stripped; the border styles in a real browser |
| Every value keeps its unit | `-490.75 ILS` is rendered exactly as the engine wrote it, and parsing a value is banned outright |
| "Concluded nothing" never looks like a clean result | No count tiles unless the run actually concluded something, even though the counts are in the data |
| Readiness per provider | Every control shows each provider's ratio and names what to connect |
| Running costs money | A run happens only when someone presses **Run** (a POST), then the page re-reads the saved result for free. Reloading never re-runs |

**What it is not allowed to do.** It cannot change the engine. No engine file changed to make room
for it, enforced by a test on every slice-15 branch. It never names a PMS: the vendor name reaches it
only as data, displayed and never branched on. It never parses money and never injects HTML. Every
request goes through one module. It writes in exactly three places, and none of them is a PMS: the
compose window files a draft; the findings queue marks a task done or dismissed (v3); and, with
authentication on, the development sign-in starts a session (v3). Each of those rules is checked by
the engine's **required** test suite, not only by the UI's own.

Since v3 it has two more pages: **`/queue`**, the findings queue, and **`/login`**, the development
sign-in, which says on the page that it is a stand-in. The guest decisions have a page on the
engine's own screen (`/guest`) but not yet on this one, by the owner's choice.

**How it is tested without a server.** The engine writes its JSON answers for every control,
property and capture to `fixtures/api/`, and the UI's tests render from those files. No engine
process, no socket, and no run is ever triggered by a test. A change to the engine that alters an
answer fails as a stale rebuild immediately, rather than as a broken screen weeks later.

---

## 10. Composing a control from prose — decision D10

Since 2026-09-16 there is a second way in. `/compose` is a chat window: you describe a rule in your
own words, and a model rewrites it as a **restricted sentence** — which you can read and edit —
before the same deterministic grammar and the same validator turn it into a rule.

```
prose → [model] → restricted English → [GrammarCompiler] → IR → [spec.validate] → run
                   ↑ you see and fix     ↑ deterministic, confidence 1.0
```

**The model never produces the rule.** It produces text. That distinction is the whole design, and
it buys three things:

1. **You can check it.** A sentence is reviewable in a way raw JSON is not.
2. **Nothing new decides anything.** A wrong field name is a sentence the grammar refuses *by
   name* — §17's gate doing exactly its job. A composed control still carries `confidence == 1.0`,
   because the *parse* was exact whatever drafted the text.
3. **A free model is good enough.** Rewriting a sentence into a template is something a 7B model
   running on your laptop does reliably; emitting a valid six-key nested IR is not. "Free to run"
   was a requirement, and asking for less is what met it.

| Backend | What | Cost |
| --- | --- | --- |
| `local` | Ollama on your machine, standard library only | **free** — the default |
| `claude` | `claude-haiku-4-5` | ~¼¢ per attempt |
| `stub` | fixed replies, no model, nothing to install | free |

Three things it deliberately does **not** do:

- **It is off unless you start it.** `python3 -m hotelcontrols.web.server` behaves exactly as it
  always has. The compose window needs `python3 -m tools.serve --llm …`. The React UI's `/compose`
  follows the engine: it says *"No proposer is wired"* when the engine has none, and offers the
  window only when it does.
- **No model client lives in the engine.** Every backend is in `tools/proposers/` and is *injected*.
  `hotelcontrols/` still imports only the standard library, and the two AST guards that enforce
  that passed **without being edited**.
- **A composed rule is a draft.** It lands in `spec/drafts/`, badged `draft · unreviewed`, and is
  **not counted** in the criterion-1 figure above. Promoting it is a deliberate manual step, and
  it raises no task in the findings queue while it is a draft.

And it will **ask rather than guess**. Type *"corporate rates must belong to an approved company"*
and it answers with a question — *which rate codes count as corporate?* — because only the hotel
knows that. §18 again: a model can interpret language, but it cannot invent hotel policy.

---

## 11. v3 — from a verdict to a task a person can act on

v2 could tell a hotel which of its rules held. It could not do anything with the answer. It did
not record which version of a rule had said so. It kept no list of what needed doing and told
nobody. It served one hotel at a time, and it had nothing to say to a guest.

v3 added those things, in nine slices built between 2026-10-09 and 2026-10-11. Its starting point
was a gap analysis against three design documents for a wider product, **StayOps**, which a
manager supplied. Every gap was given a disposition: built, narrowed, deferred, blocked, or
rejected. Each one had to pass a single rule before it was built:

> **A gap is taken only if it can be built without widening a verdict, without crossing the
> canonical boundary, and without changing an answer the engine already gives — or, where it must
> change one, the change is named and shown in a reviewed diff.**

That rule overturned the plan before any code was written. The item rated cheapest and safest, a
twelfth control checking *"a card is on file before arrival"*, turned out to be the most dangerous
on the list. Every card in the captures is the placeholder `****`, so the control would have passed
every reservation ever seen. It is **blocked** until the vendor explains the placeholder.

### What the nine slices added

| Slice | What it adds, in one sentence | Why it matters, as an analogy |
| --- | --- | --- |
| 16 · Rule versions | Every stored answer names the version of the rule that produced it, and a rule edited without a new version number is refused | A court cites the law **as it read on the day**. "It failed under rule 6" is not an audit trail if rule 6 was edited last week |
| 17 · One hotel's results are its own | Every stored result belongs to one hotel, and the code cannot ask for one without saying which | Separate filing cabinets rather than one cabinet with a polite note on each drawer. A test fails any query that forgets the hotel |
| 18 · The findings queue | A violation becomes **one** task for the right team, with the severity the rule declares. A person marks it done or dismisses it | A work order, not an alarm. Re-running the control five times still gives one task. A later pass annotates the task and never closes it, because only a person knows the money was refunded |
| 19 · Email | The team is told about a new task, once, if the operator has switched email on | Behind **two** locks, like the PMS connection: a switch, and a refusal to send anything while a test is running. An email carries the record id, the control, the amount with its currency and a link. Never a guest's details, and never the verdict's reasoning |
| 20 · The operational log | One line per request, run and email, saying what ran, for whom, and what it cost | A ship's log rather than a diary: dated by the hotel's clock, and never holding a password, a guest or a staff address |
| 21 · *Not decided* is a state | Each hotel setting has a declared type. A setting the hotel has not decided is written *not decided*, and a control that needs it answers UNKNOWN **naming** it | An empty list could mean "we chose none" or "nobody asked us". In an exemption rule, the second reading would have accused every guest the hotel meant to exempt |
| 22 · Late checkout | A guest asks to leave at 3 pm. The hotel's own approved table answers *approved*, *approved with a fee*, *denied*, *unavailable*, or *staff review*, naming the rule it followed. On a test hotel with a decided policy, 3 pm costs `25.00 USD`, as money | The guest-services twin of UNKNOWN is **staff review**: any missing fact or undecided policy goes to a person, never to a guess. The two shipped hotels have decided no policy, so they answer *staff review* to everything, and say why |
| 23 · An evidence refresh | Four live calls, each approved by the owner at the time, captured as a new body of evidence beside the old | Re-checked rather than assumed. 23 of 28 rooms still report capacity 0, and still no room has a closed window. Occupancy for July 2026 now exists, so that control answered for the first time |
| 24 · Who is asking | The product in front of the engine signs a short-lived statement, *"this request is about hotel P"*. The engine checks the signature and ignores whatever hotel the address asked for. Each hotel has its own PMS credentials | A wristband checked at the door, rather than a name written on a form. The engine never stores a password, and the vendor's sandbox credentials are named per hotel with no fallback |

### After v3: the fixes that made the numbers honest

Using v3 found three defects. Each one made an answer look **more** confident than its evidence
allowed. Each was filed as an issue before it was fixed, and each fix made a number fall or held it
where it was.

- **A capture answered a question it was never asked** (issue #71). The vendor's July capture
  recorded *departures*. Seven controls ask about *arrivals* or *creations*, and replay answered
  them from the departures anyway, because it compared windows only by name. Three controls
  concluded about part of their population and presented it as the whole. Now a capture answers
  only the question it recorded, and refuses any other. Two new live calls, each approved by the
  owner, recorded the questions the controls actually ask. The result is the **covering capture**,
  which the demo offers beside the original.
- **An empty field was read as the word "False"** (issues #75, #84, #85, #86). Two bookings with
  no room number were judged to be in the same room, a room called "False", so they clashed. A
  booking with no id was counted as one reservation called "False". Now an empty identity is
  *unknown*, and two unknowns are never treated as a match.
- **A room with many guests was judged by its first guest** (issues #87, #109). The
  out-of-service control looked at only the first guest in a closed room. For a while it compared a
  reservation number against a date. Now every guest in the room is judged, and the room passes only
  if the evidence it fetched covers the closure from today onwards. The occupancy question asks a bounded seven-day
  window, because MiniHotel asks integrators not to query wide ranges. A closure with no end can
  fail, but it can never pass.

None of the three changed a verdict on any capture today, apart from the ones #71 corrected, and
every changed answer is declared by name in the regression test that guards v2's answers. Every room
is still out of scope for the out-of-service control, because no room has ever had a closed window.
The fixes matter for the day one does.

## 12. Where to go next

| You want to… | Read |
| --- | --- |
| Find your way around the repository | [02-file-structure.md](02-file-structure.md) |
| Run, test or change the React UI | [`ui/README.md`](../../ui/README.md) |
| See the layers, the flow and the logic as diagrams | [03-code-architecture.md](03-code-architecture.md) |
| Understand the traps in the real API, and see one record traced end-to-end | [04-edge-cases.md](04-edge-cases.md) |
| See which StayOps features the POC and this engine each cover, and why not where not | [05-stayops-poc-comparison.md](05-stayops-poc-comparison.md) |
| Read the falsifiable contract | [`docs/prd.md`](../prd.md) |
| Read v3's plan, every slice's record and criteria V1–V12 | [`docs/plan-v3.md`](../plan-v3.md) |
| Know what changed most recently, and what is approved next | [`docs/session-handoff.md`](../session-handoff.md) |
| Know why any decision was taken | [`docs/context.md`](../context.md) |
| Know what is still unresolved | [`docs/open-questions.md`](../open-questions.md) |
| Read the compose decision in full | [`docs/open-questions.md`](../open-questions.md) — decision D10 |
