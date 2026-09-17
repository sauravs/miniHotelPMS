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

### v2 — everything else in this repository

Twelve slices, each a branch → PR → green CI → squash-merge. Measured today:

```
1,610 tests passing, offline, in about 10 seconds
1,080 spec-validation checks passing
zero runtime dependencies
11 controls, 2 providers, 8 layers
11 of 12 success criteria met
```

### The honest scorecard

Criterion 1 asked that **at least 8 of the 11 controls reach a PASS or a FAIL** on captured
evidence. Here is what actually happens when you run all eleven against the 2026 capture — output
produced by running the engine, not copied from a document:

| Control | Result | Concludes? |
| --- | --- | --- |
| `checkout_money_owed` | 2 PASS | ✅ |
| `checkout_unrefunded_credit` | 1 PASS, **1 FAIL** | ✅ |
| `duplicate_channel_reservation` | 4 PASS, 10 UNKNOWN, 26 EXCLUDED | ✅ |
| `inactive_room_future_stay` | 27 PASS, 13 UNKNOWN, 71 EXCLUDED | ✅ |
| `room_assignment_type_validity` | 27 PASS, 13 UNKNOWN, 71 EXCLUDED | ✅ |
| `resource_occupancy_consistency` | **BLOCKED** — no occupancy capture covers this week | ❌ |
| `ooo_room_protection` | 28 EXCLUDED | ❌ |
| `room_assignment_active_room` | 111 EXCLUDED | ❌ |
| `room_capacity_compliance` | 40 UNKNOWN, 71 EXCLUDED | ❌ |
| `rate_room_category_consistency` | 40 UNKNOWN, 71 EXCLUDED | ❌ |
| `required_reservation_fields` | 37 UNKNOWN, 71 EXCLUDED | ❌ |

**5 of 11. The criterion is recorded as NOT MET**, in `docs/plan.md`, with the arithmetic.

That is the point. Every one of the six shortfalls traces to a fact about *this property* or *this
vendor*, not to a bug:

- **No room in this hotel has ever had an out-of-service window set.** So two controls correctly
  apply to nobody. Reporting "compliant" would be reporting a clean bill of health for a mechanism
  nobody has ever seen working — which is exactly what v1 did.
- **23 of 28 rooms report capacity `0`**, meaning unconfigured. Reading those as real zeroes would
  produce a wall of false FAILs.
- **A rate code and a price-list code are different key spaces** in MiniHotel, so no endpoint can
  resolve the mapping at all.
- **This property has nominated no rate codes**, so the "required fields on rate X" control applies
  to no reservation.

**Three of those six would move on a conversation, not on code.** One sentence from the hotel naming
its rate codes. One sentence from the vendor explaining what the status codes `OK4` and `WL` mean —
which would resolve **44 of the 217 reservations this project has ever seen, one in five.** One
rate-plan mapping supplied by the hotel.

> A number that went **down** when a bug was fixed is the most trustworthy number in this document.
> `resource_occupancy_consistency` used to count towards criterion 1 — it was answering questions
> about July 2026 using occupancy data captured in August 2024. Issue #9 fixed that. The score fell
> from 6 to 5 and the guard stayed.

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
| "We tell you what your PMS can answer" | Integration roadmap driven by customer demand, not by guessing | `runner/readiness.py` | Rendered per control per provider on the index page: *"MiniHotel 4/5 fields · DemoPMS 5/5"* |
| "It runs anywhere" | A demo with an install step is a demo that fails in the meeting | Standard library only: `xml.etree`, `decimal`, `sqlite3`, `http.server`, `zoneinfo`, `json` | `tests/unit/test_stdlib_only.py` walks the tree and asserts the engine contains no outbound HTTP client at all |
| "No test can touch the network" | A suite that needs someone else's server up is not a suite | `providers/transport/` is opt-in, off by default | **Two locks:** an environment variable *and* a refusal to arm while a test runner is loaded. The test that sets the variable is still refused |

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
| **Mews** | Credentials do not exist and may not for months | A directory under `providers/`, a map in `spec/providers/`, a tenant file. Nothing above the provider layer changes — the slice-7 diff is the evidence |
| **A running scheduler** | The scheduling *decision* is the hard part and is built and tested as a pure function | A loop that calls `next_evaluation()` |
| **Webhook ingestion** | IRs already declare their events; nothing subscribes | An HTTP endpoint and a subscription |
| **Writing to a PMS** | Read-only, permanently. The hotel types *controls*, not commands | Not planned. Ever |
| **Authentication / multi-user** | Single-operator local demo | Standard work, deliberately deferred |
| **Free text as evidence** | VIP status and manager approvals exist only as Hebrew free text in a remarks field. Whether that counts is [open question 1.5](../open-questions.md) | An extractor that returns a value **only with the exact quotation it relied on**, and UNKNOWN whenever the text is ambiguous |
| **A rule-editor UI** | `/compose` is a chat box, not an editor — it files **drafts** and promoting one is manual. There is no screen for editing a shipped control | A form over the compiler, plus a versioning story (§19 of the brief) |
| **A model anywhere near a verdict** | Decision D10 wired a model to *draft a sentence* (see §10 below). Nothing it produces reaches the evidence layer or the evaluator, and no verdict depends on a model call | Not planned. This one stays out |

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
  always has. The compose window needs `python3 -m tools.serve --llm …`.
- **No model client lives in the engine.** Every backend is in `tools/proposers/` and is *injected*.
  `hotelcontrols/` still imports only the standard library, and the two AST guards that enforce
  that passed **without being edited**.
- **A composed rule is a draft.** It lands in `spec/drafts/`, badged `draft · unreviewed`, and is
  **not counted** in the 5-of-11 figure above. Promoting it is a deliberate manual step.

And it will **ask rather than guess**. Type *"corporate rates must belong to an approved company"*
and it answers with a question — *which rate codes count as corporate?* — because only the hotel
knows that. §18 again: a model can interpret language, but it cannot invent hotel policy.

---

## 11. Where to go next

| You want to… | Read |
| --- | --- |
| Find your way around the repository | [02-file-structure.md](02-file-structure.md) |
| See the layers, the flow and the logic as diagrams | [03-code-architecture.md](03-code-architecture.md) |
| Understand the traps in the real API, and see one record traced end-to-end | [04-edge-cases.md](04-edge-cases.md) |
| Read the falsifiable contract | [`docs/prd.md`](../prd.md) |
| Know why any decision was taken | [`docs/context.md`](../context.md) |
| Know what is still unresolved | [`docs/open-questions.md`](../open-questions.md) |
| Read the compose decision in full | [`docs/open-questions.md`](../open-questions.md) — decision D10 |
