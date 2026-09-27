# StayOps — Controls & Guest Services

**What we are building, and why.** A plain-language brief for anyone who needs to understand this
product quickly — a manager, a new joiner, a prospective customer, a salesperson.

> Describes the **intent** set out in the three StayOps design documents (Product & Architecture
> Design v1.0, Technical Design & Coding Specification v1.1, Developer Implementation Package v1.0).
> It says nothing about how much is built today — that comparison is a separate report, so this one
> does not go out of date every week.

---

## 1. The problem

Every hotel runs on rules. *Don't put an arriving guest in a room that's out of order. Don't take a
booking without a payment guarantee. Don't put three people in a room that sleeps two. Late checkout
is free until 2 PM, then it costs money, and after 4 PM a manager has to say yes.* These rules are
real, they are specific to each hotel, and they matter — they are how the hotel protects its revenue,
its guests and its reputation. And almost all of them live in a binder, in a training session, or in
the head of whoever has worked there longest. **Nobody systematically checks whether the hotel is
actually following its own rules, and nobody can answer the same guest question the same way twice.**
StayOps exists to fix both halves of that.

---

## 2. Who this is for

Four real people, with four different problems:

| Person | What they need | What they do today |
| --- | --- | --- |
| **Operations manager** | To know, this morning, whether the hotel is complying with its own standards | Spot-checks a handful of bookings, or trusts that it's fine |
| **Finance / audit** | To find money left on the table before it's gone — guests who checked out owing, guests who overpaid and were never refunded | Finds it weeks later in a reconciliation, or not at all |
| **Front-desk agent** | A confident answer when a guest asks for something the policy half-covers | Guesses, asks a manager, or quotes a price a colleague wouldn't have |
| **Guest** | A yes or a no, now, with the price attached | Waits, gets an inconsistent answer, or is told to ask again at checkout |

A capability with no named user is the thing that gets built and never used. These four are the test.

---

## 3. The two halves

StayOps does two things. They share almost all of their machinery and none of their shape.

### Half A — Hotel Controls: *"Is the hotel following its own rules?"*

The hotel writes a rule in plain English:

> **"Out-of-order rooms should never have arriving reservations."**

StayOps then checks the hotel's live operational data — continuously, on a schedule, or on demand —
and reports every case where the rule is broken:

> **Violation.** Reservation 12345 arrives on 19 September and is assigned to room 101.
> Room 101 is out of order.
> *The rule says arriving reservations must not be assigned to out-of-order rooms.*

The operations manager gets a short list of things to fix today, each with the specific facts behind
it, so it can be trusted without being re-checked by hand. Four more rules in the same family: every
arrival within 24 hours must have a valid payment guarantee; no room may hold more guests than it
sleeps; every arriving reservation must have a phone number; and no future booking may sit on a room
that has been deactivated.

### Half B — Guest Service Rules: *"A guest just asked for something — what should we do?"*

The hotel writes its policy in plain English:

> **"Guests can have late checkout until 2 PM for free. Between 2 PM and 4 PM, charge $25 per hour.
> Anything after 4 PM needs manager approval."**

A guest asks:

> **"Can I check out at 3 PM tomorrow?"**

StayOps works out what was asked (late checkout, 3 PM), finds the hotel's policy, applies it, and
answers:

> **Approved, with a fee.** Late checkout until 3:00 PM is available for an additional $25.

3 PM is later than the free cutoff of 2 PM but no later than the 4 PM limit, so it is allowed and it
costs money. Every guest asking the same question gets the same answer at the same price, whoever is
on the desk — and the hotel can change the policy without retraining anyone. Four more in the same
family: early check-in, room upgrades, simple requests like extra towels, and maintenance reports
(*"the AC isn't working"*), which get classified, prioritised and routed rather than approved.

### Why they belong in one product

The first half is *"check this against the rules."* The second is *"decide this against the rules."*
Both need the same three things: the hotel's rules written down in a form a machine can apply, the
hotel's real data fetched reliably, and a decision made the same way every time. Build that once and
both halves fall out of it.

---

## 4. Why this can't just be one integration

Here is the commercial heart of the product, and it is easy to miss.

Every hotel runs a different Property Management System — the software holding its bookings, rooms
and guests — and each names the same real-world thing differently. A room taken out of service is
`Out Of Order` in one system and `OOO` in another; one calls the field `RoomStatus`, another `State`.

So the naïve build — write the rule against one system's field names — produces a rule that works at
exactly one hotel. Sell to a second hotel on a different system and you write it again. Ten hotels,
three systems, five rules each, and you maintain a hundred and fifty slightly different things that
all drift apart.

StayOps is built the other way round. There is **one internal vocabulary** — a room's status is
always `OUT_OF_ORDER`, whatever the hotel's system calls it — and a small translator per system,
called an **adapter**, whose only job is to convert that system's language into the shared one. The
rule never learns which system the hotel runs.

```
   The hotel's rule          "out-of-order rooms must have no arrivals"
          │
   Shared vocabulary         room.status = OUT_OF_ORDER
          │
   Adapter per system        "Out Of Order"  ·  "OOO"  ·  whatever the next one says
```

**The commercial consequence: the second hotel on a system we already speak is configuration, not a
rebuild. And a brand-new system is one adapter, after which every existing rule runs on it
unchanged.** That is the whole reason the architecture is shaped the way it is, and it is the thing
to protect above all else.

---

## 5. Why the hotel writes English and not code

Two reasons, and the second is the business one.

A hotel cannot be asked to write its rules in a syntax. The person who knows this property gives
late checkout free until 2 PM is a duty manager, not a developer, and a system that demands otherwise
simply does not get the rules.

And the alternative — a consultant configures each rule for each customer — does not scale. It makes
every sale a project, every rule a line item and every customer a slightly different version of the
product to support. The hotel typing its own rule in its own words is what makes this a product
rather than a consultancy.

There is a safeguard that matters here: **the hotel is always shown what StayOps understood, in
plain language, before anything is switched on.** Plain English is convenient and ambiguous, so the
hotel confirms the interpretation — *free until 2:00 PM, paid 2:00–4:00 PM at $25/hour, manager
approval after 4:00 PM* — and only then activates it. The interpretation is never hidden.

---

## 6. Why a language model must not decide the answer

StayOps uses AI, and it is important to be precise about where.

**The model translates. It does not decide.** It takes *"OOO rooms should never have arriving
reservations"* and works out that the hotel means a specific, supported rule about room status and
arriving bookings. That is a language problem, and it is what language models are genuinely good at.

What the model never does is look at a booking and pronounce on whether the hotel broke its rule, or
look at a guest's request and decide whether to approve it. Those decisions are made by fixed logic:
given the same rule and the same facts, the answer is always the same, and anyone can follow the
arithmetic.

The reason is liability. These verdicts go in front of a finance team, an auditor and sometimes a
guest being charged money, and *"the system thought so"* is not a defence. Three properties are
non-negotiable: **reproducible** (ask the same question about the same day next year, get the same
answer), **explainable** (every verdict shows the facts that produced it and where each came from),
and **consistent** (two identical guest requests cannot get different prices).

A system that confidently guesses is worse than one that admits it does not know, because a wrong
answer delivered confidently gets acted on. Which brings us to the next point.

---

## 7. Why "we don't know" has to be a real answer

Most hotel rules are not *"X must never happen."* They are *"X must not happen **unless someone
approved it**."* Don't move a guest to a better room for free — *unless a manager authorised it.*
Don't let a booking through without a guarantee — *unless it's a comp.*

And hotel systems very often do not record the approval. There is no field for it, no audit trail, no
record of who decided what. So for a large share of real rules, the honest answer is not yes or no.
It is: **we can see the thing that happened; we cannot see whether it was authorised.**

StayOps therefore has a third answer — *unknown* — that carries a reason and names exactly what is
missing. It never guesses in either direction. This matters three ways:

1. **It protects the number.** A compliance report that quietly counts unverifiable cases as passes
   is worse than no report, because it will be believed.
2. **It turns a limitation into a product path.** *"This rule needs housekeeping status, which your
   PMS doesn't publish — connect your housekeeping system and it starts working"* is a roadmap the
   customer can act on, and a sales conversation.
3. **It can ship as a work queue.** *"Here are the twelve bookings where a human must confirm an
   approval existed"* is useful even when *"here are the twelve violations"* is unavailable.

Likewise, on the guest side, a request the policy does not clearly cover is routed to staff rather
than resolved with a guess. Handing a borderline case to a person is a correct outcome, not a
failure.

---

## 8. Glossary

The seven words that appear everywhere. Read this section if you read nothing else.

| Term | What it means |
| --- | --- |
| **PMS** | Property Management System — the software a hotel runs its bookings, rooms and guests on. Different hotels run different ones. |
| **Control** | A rule the hotel wants continuously checked. *"Out-of-order rooms must have no arriving reservations."* Produces violations. |
| **Policy** | A rule the hotel wants applied to guest requests. *"Late checkout free until 2 PM, then $25/hour."* Produces decisions. |
| **Template** | The reusable shape of a rule, shared by all customers — *late checkout*, *room capacity*. Each hotel fills in its own numbers. Hotel A's free-until is 2 PM, Hotel B's is 1 PM; there is only one late-checkout template. |
| **Evidence** | The specific facts a rule needs, fetched from the hotel's systems — this booking's arrival date, this room's status. Every verdict is shown with the evidence behind it, including where each fact came from. |
| **Canonical** | The shared internal vocabulary, the same for every hotel and every PMS. A room's status is `OUT_OF_ORDER` here, whatever the hotel's own system calls it. |
| **Adapter** | The small translator for one PMS: converts that system's data into the canonical vocabulary. Adding a PMS means writing an adapter, not rewriting any rule. |
| **Tenant** | One customer on the shared platform. Every hotel uses the same application; each one's data, rules, credentials and results are kept strictly separate, and no hotel can ever see another's. |
| **Violation** | One record that breaks one control, with the evidence attached. |
| **Decision** | The answer to one guest request: approved, approved with a fee, declined, or sent to staff. |

---

## 9. What is deliberately not in scope

The documents are as clear about the boundary as about the ambition, and a reader needs both.

**Included in the first release:** two PMSs (one live, one architecturally prepared), five hotel
controls, five guest-service rules, plain-English authoring, one shared platform with each customer's
data isolated, scheduled and on-demand checking, results with their evidence, and simple
notifications.

**Explicitly excluded** — each considered and ruled out on purpose, because it adds complexity
without helping prove that customers want the product:

- **A general-purpose rule language.** No customer scripting, no *"if the guest has stayed three
  times and occupancy is above 80% and the GM isn't working, give them a free upgrade."* Supported
  templates with typed settings only. Anything else is a programming language wearing a product's
  clothes.
- **A workflow builder, autonomous agents, predictive models, anomaly detection.**
- **A universal hotel data model.** The internal vocabulary grows only when a real rule needs a new
  fact — never speculatively.
- **A large integration catalogue.** Housekeeping, point-of-sale and maintenance systems get
  connected when a customer wants a rule needing them. Integrations are pulled by demand, never built
  on spec — StayOps is not trying to become a data platform.
- **AI-generated code, and AI-made verdicts.** See §6.
- **Anything customer-specific in the shared logic.** Differences belong in the adapter, the
  mapping, the hotel's settings and the rule's parameters — never in a branch of code written for one
  hotel.

The stated development philosophy is worth repeating almost verbatim: build **one** hotel, **one**
PMS, **one** rule, **one** violation, end to end, before generalising anything. Then five and five,
then a second hotel, then a second PMS. The goal is not the most sophisticated policy engine — it is
proving that hotels will hand over their operating rules and let software apply them.

### Two things the documents leave genuinely open

Stated plainly rather than papered over, because both change what gets built:

1. **Does StayOps *act*, or does it *advise*?** The guest-service examples include creating a service
   request, raising a maintenance ticket and applying a $25 charge. Whether StayOps performs those in
   the hotel's systems, or decides and hands a staff member the task, is not settled — and it is the
   difference between a system that only reads hotel data and one that writes to it. A decision, not
   a detail.
2. **The exact vocabulary of a guest decision.** The documents variously list four and five outcomes
   under slightly different names. The concepts agree — *yes*, *yes with a charge*, *no*, *ask a
   human*, *not available* — but the set needs fixing before it is built into anything.

*Filename note: named exactly as requested, "Cotrols" included — say the word and it gets renamed.*
