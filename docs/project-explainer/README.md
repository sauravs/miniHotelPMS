# Project Explainer

Four documents that take you from *"what is this company selling?"* to *"which line of code
decides that?"* in about an hour, without needing to read the eight documents in `docs/` first.

They are **standalone**. Everything you need is here; links point outward only when you want the
long version.

## Reading path

| # | Document | What you get | Time |
| --- | --- | --- | --- |
| 1 | [01-project-overview.md](01-project-overview.md) | The business case in plain English, with analogies. What a hotel asked for, why it is hard, and how each business idea became a piece of code. **No code required to read it.** | ~10 min |
| 2 | [02-file-structure.md](02-file-structure.md) | Every folder and every file: what it is, why it exists, who imports it, and what breaks if it is wrong. | ~10 min |
| 3 | [03-code-architecture.md](03-code-architecture.md) | The eight layers, the request lifecycle, the control flow, the data shapes, and the decision logic — as diagrams. | ~20 min |
| 4 | [04-edge-cases.md](04-edge-cases.md) | **Part A:** the seven facts about the real API that shaped the whole design. **Part B:** one real reservation traced field-by-field from raw XML to the pixel on screen. | ~15 min |

Composing a control from prose — the chat window, and why the model drafts a *sentence* rather than
a rule — is [01-project-overview.md §10](01-project-overview.md). The decision behind it is **D10**
in [`docs/open-questions.md`](../open-questions.md).

If you have five minutes and not an hour, read §1 and §2 of
[01-project-overview.md](01-project-overview.md) and the first diagram in
[03-code-architecture.md](03-code-architecture.md).

## What is true as of this writing

Measured, not quoted — every number below was produced by running the code on 2026-09-10.

| | |
| --- | --- |
| Tests | **1610 passing**, offline, in ~9 seconds |
| Spec validation | **1,080 checks passing** (`python3 -m tools.validate_spec`) |
| Runtime dependencies | **Zero.** Python standard library only — the optional compose backend lives outside the engine |
| Controls shipped | **11**, as data files in `spec/ir/` — plus any composed into `spec/drafts/` |
| Providers | **2** — MiniHotel (XML, real captures) and DemoPMS (JSON, generated) |
| Success criteria met | **11 of 12.** The twelfth is recorded as *not met* with its arithmetic |

## The one-sentence version

> A hotel writes a governance rule in plain English; the engine compiles it into a rule that names
> no property-management system, fetches only the evidence that rule needs from whichever system
> the hotel actually runs, and answers **PASS / FAIL / UNKNOWN / EXCLUDED** — always attaching the
> exact fields that produced the answer, and never guessing when the evidence is missing.

## Where these fit among the existing docs

```
CLAUDE.md                    ← 2-minute orientation for a coding session
README.md                    ← the pitch
docs/
  project-explainer/         ← YOU ARE HERE. Business → code, for a newcomer
  prd.md                     ← the contract: what we build, 12 falsifiable criteria
  context.md                 ← the history: how we got here, every decision + why
  architecture.md            ← the design: 8 layers, interfaces, what each hides
  plan.md                    ← the build log: 13 slices, test gates, honest scorecard
  open-questions.md          ← what we know we don't know
  old-codebase-improve.md    ← the v1 post-mortem: 12 keeps, 20 fixes
  QA.md                      ← running transcript with the project owner
```
