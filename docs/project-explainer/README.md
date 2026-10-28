# Project Explainer

Four documents that take you from *"what is this company selling?"* to *"which line of code
decides that?"* in about an hour, without needing to read the twelve documents in `docs/` first.
A fifth compares this engine, feature by feature, with the StayOps requirements and with a second
implementation of them.

They are **standalone**. Everything you need is here; links point outward only when you want the
long version.

## Reading path

| # | Document | What you get | Time |
| --- | --- | --- | --- |
| 1 | [01-project-overview.md](01-project-overview.md) | The business case in plain English, with analogies. What a hotel asked for, why it is hard, and how each business idea became a piece of code. **No code required to read it.** | ~10 min |
| 2 | [02-file-structure.md](02-file-structure.md) | Every folder and every file: what it is, why it exists, who imports it, and what breaks if it is wrong. | ~10 min |
| 3 | [03-code-architecture.md](03-code-architecture.md) | The eight layers, the request lifecycle, the control flow, the data shapes, and the decision logic — as diagrams. | ~20 min |
| 4 | [04-edge-cases.md](04-edge-cases.md) | **Part A:** the seven facts about the real API that shaped the whole design. **Part B:** one real reservation traced field-by-field from raw XML to the pixel on screen. | ~15 min |
| 5 | [05-stayops-poc-comparison.md](05-stayops-poc-comparison.md) | The three StayOps requirement documents, the POC in `ruleEngineAnishLegacy/` and this engine, one row per StayOps feature: who covers it, who does not, and the written reason. A comparison, not a plan. | ~20 min |

Composing a control from prose — the chat window, and why the model drafts a *sentence* rather than
a rule — is [01-project-overview.md §10](01-project-overview.md). The decision behind it is **D10**
in [`docs/open-questions.md`](../open-questions.md).

There are **two screens** over the same engine: the engine's own server-rendered pages, and a React
UI under `ui/` that is a client of its JSON API. Why there are two, and what the second one is not
allowed to do, is [01-project-overview.md §9](01-project-overview.md#9-two-screens-over-one-engine--the-react-ui).

What happened **after** a verdict, which is most of v3 (the findings queue, email, guest
decisions, signed tenant contexts, rule versions), is
[01-project-overview.md §11](01-project-overview.md#11-v3--from-a-verdict-to-a-task-a-person-can-act-on).

If you have five minutes and not an hour, read §1 and §2 of
[01-project-overview.md](01-project-overview.md) and the first diagram in
[03-code-architecture.md](03-code-architecture.md).

## What is true as of this writing

Measured, not quoted. Every number below was produced by running the command beside it, on
**2026-10-13**, on `main` after v3 and issue #109. The other four documents refer to this table
rather than repeating its numbers. If one of them disagrees with it, this table is the one that was
measured.

| | | Measured by |
| --- | --- | --- |
| Tests | **3,378 passing, 3 skipped**, offline, in about a minute. 3,381 collected: unit 1,704 · integration 1,333 · contract 94 · e2e 250 | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q` |
| React UI tests | **249** component tests and **26** real-browser tests, of its own | `cd ui && npm test && npm run e2e` |
| Coverage | **97.6%** of the engine's lines and branches (the floor is 90%) | `coverage run -m pytest && coverage report --precision=2` |
| Spec validation | **1,098 checks passing** | `python3 -m tools.validate_spec` |
| Golden API payloads | **228**, identical to a rebuild. The React UI's contract | `python3 -m tools.dump_api_fixtures --check` |
| DemoPMS files | **17**, identical to a rebuild from the MiniHotel captures | `python3 -m tools.transcode_demopms --check` |
| Runtime dependencies | **Zero in the engine.** Python standard library only. The model backends, the email backend and the React UI all live outside it | `tests/unit/test_stdlib_only.py` |
| Controls shipped | **11**, as data files in `spec/ir/`, each versioned and locked. Composed ones go to `spec/drafts/` and are never counted | `ls spec/ir` |
| Guest templates | **1**, `LATE_CHECKOUT`, a decision table the owner approved | `ls spec/guest` |
| Providers | **2**: MiniHotel (XML, real captures) and DemoPMS (JSON, generated) | `providers/registry.py` |
| Captures | **4** per provider: `sandbox2024`, `sandbox2026`, `sandbox2026refresh`, `sandbox2026cover` (and `demo…` for each). 20 MiniHotel responses in all | `fixtures/minihotel/index.json` |
| Success criteria (v2) | **11 of 12 met.** Criterion 1 is **NOT MET on every capture**: 2 of 11 controls conclude on `sandbox2026`, 1 on the refresh, 5 on the covering capture. The PRD asks for 8 | `tests/e2e/test_runs.py`, `tests/e2e/test_refresh_capture.py` |
| Success criteria (v3) | **V1–V12, all met** | `docs/plan-v3.md` §7 |
| Screens | **2.** The engine's own pages (no JavaScript) and the React UI in `ui/`, both over one JSON API | |

## The one-sentence version

> A hotel writes a governance rule in plain English; the engine compiles it into a rule that names
> no property-management system, fetches only the evidence that rule needs from whichever system
> the hotel actually runs, and answers **PASS / FAIL / UNKNOWN / EXCLUDED** — always attaching the
> exact fields that produced the answer, and never guessing when the evidence is missing.

## Where these fit among the existing docs

```
CLAUDE.md                    ← 2-minute orientation for a coding session
README.md                    ← the pitch
ui/README.md                 ← the React UI: how it is built and tested, and every dependency justified
spec/drafts/README.md        ← how a composed draft is promoted to a shipped control
docs/
  project-explainer/         ← YOU ARE HERE. Business → code, for a newcomer; 05 compares StayOps, the POC and us
  prd.md                     ← the contract: what we build, 12 falsifiable criteria
  context.md                 ← the history: how we got here, every decision + why
  architecture.md            ← the design: 8 layers, interfaces, what each hides
  plan.md                    ← the v2 build log: slices 0–15, test gates, the criterion-1 arithmetic
  plan-v3.md                 ← v3: every StayOps gap's disposition, slices 16–24, criteria V1–V12
  open-questions.md          ← what we know we don't know, and what the engine does meanwhile
  session-handoff.md         ← the starting prompt for the next coding session, and the state since 2026-10-09
  old-codebase-improve.md    ← the v1 post-mortem: 12 keeps, 20 fixes. A historical record
  QA.md                      ← running transcript with the project owner, append-only
  stayOps_Cotrols_Rule_Engine_V2.md  ← the StayOps documents' intent, in plain language. Not a status report
  stayops-gap-analysis.md    ← StayOps' requirements against what existed on 2026-09-28. The input to v3
```
