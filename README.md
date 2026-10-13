# miniHotelPMS — Hotel Control Rule Engine

A **PMS-agnostic engine for hotel governance controls.** A hotel states a rule in plain English; the
engine compiles it to a representation that names no PMS, resolves the evidence it needs from
whichever property management system the hotel runs, and answers with an auditable trail.

```
  "A reservation cannot be closed with an outstanding balance."
                          ↓
              PMS-neutral Control IR
                          ↓
     evidence resolved from MiniHotel · DemoPMS · (Mews)
                          ↓
     PASS · FAIL · UNKNOWN · EXCLUDED  + the fields that produced it
```

## Why UNKNOWN matters

Most hotel controls read *"X must not happen **unless approved**"* — and property management systems
generally record no acting user, no reason code and no audit trail. The approval half is often
unanswerable.

So the engine has four outcomes, not two:

| | |
| --- | --- |
| **PASS** | Everything required is known, and the rule holds |
| **FAIL** | Everything required is known, and the rule is violated |
| **UNKNOWN** | Not enough evidence — with the reason, and the fields that are missing |
| **EXCLUDED** | The control does not apply here. Not an answer; the control has no opinion |

A system that guesses manufactures confidence, which is worse than answering nothing. UNKNOWN also
turns a limitation into a product path: *"connect your housekeeping system to enable this control."*

## Status

**v2 and v3 are both complete.** v2 is the engine: twelve slices, then compose (13), a UI/UX pass
(14) and a React UI (15). **v3** (slices 16–24, [`docs/plan-v3.md`](docs/plan-v3.md)) is what happens
after a verdict. Every stored answer names the version of the rule that produced it. One hotel
cannot read another's results. A violation becomes one task in a findings queue, optionally emailed
behind two locks. The operational log says what ran and what it cost. A hotel setting can be *not
decided*, which is different from *none*. One guest service, late checkout, is decided by a table
the owner approved. The evidence was refreshed by six owner-approved live calls. The host
authenticates and the engine verifies a signed tenant context. All twelve of v3's own criteria
(V1–V12) are met.

Measured on 2026-10-13: **3,378 tests pass** (3 skipped), 97.6% coverage, 1,098 spec checks, 228
golden API payloads identical to a rebuild. The engine runs offline and is green on Python 3.11 and
3.13. **Eleven of v2's twelve success criteria are met**; the twelfth is recorded as *not met* with
its arithmetic, which is the point of writing them down. The full table, with the command behind
each number, is in [`docs/project-explainer/README.md`](docs/project-explainer/README.md#what-is-true-as-of-this-writing).

The claim the architecture rests on is checked rather than asserted: **the same rule, over the same
hotel, through two completely different PMS wire formats, produces the same verdicts** — and adding
the second one changed nothing above the provider layer.

**Criterion 1 is not met on any capture.** The PRD asks for 8 of the 11 controls to reach a PASS or
a FAIL. On the covering capture `sandbox2026cover`, the only one that recorded every question the
controls ask, **5** do. On `sandbox2026`, the demo's default, **2** do, because a capture answers
only the questions it recorded (issue #71). On the 2026-10-10 refresh, **1** does. Every one of the
six shortfalls traces to a fact about the property or the provider rather than to a defect in the
engine. No room in this property has ever had an out-of-service window set. 23 of 28 rooms report
their capacity as unconfigured. A rate code and a price-list code are different key spaces. The
hotel has not decided its rate codes. One of the six would move on a sentence from the vendor
alone; the rate-code pair needs a real hotel's decision as well. The full assessment is in
[`docs/plan.md`](docs/plan.md). v1 met all seven of its own criteria while nine of its ten controls
answered nothing at all, and that is the mistake this number exists to avoid.

## Two screens over one engine

Every answer can be read on two surfaces. Both are clients of the same JSON API, and both show a
verdict with the fields that produced it.

| | The audit surface | The product surface |
| --- | --- | --- |
| Where | Served by the engine itself, `http://127.0.0.1:8765/` | `ui/`, a Next.js + TypeScript app, `http://127.0.0.1:3000/` |
| Built with | Server-rendered HTML, **no JavaScript**, standard library only | React 19. Three runtime packages, pinned exactly |
| Why it exists | Offline, printable, zero-dependency: what an auditor can trust | Converges with the larger JavaScript product this will be patched into |

The React UI is an **addition, not a rewrite**. No engine file changed to make room for it, and a
test enforced that on every slice-15 branch. Delete `ui/` and the engine still ships, audits and
demos. Because the engine's tests say nothing about a second client, the UI's own suite re-proves
the criteria that matter on screen:
- UNKNOWN is told apart from FAIL by hue, border **and** wording;
- every value appears with its unit;
- a run that concluded nothing shows no counts;
- readiness is reported per provider.

The rules that matter most about `ui/` are also checked by the engine's **required** suite: money is
never parsed, no PMS name appears, no HTML is injected, and one module makes every request.

## Two ways a control gets in

A control is a **JSON file in `spec/ir/`** — which is what makes a twelfth control a config change
rather than a code change. Since slice 13 it can also arrive as **prose**:

```
prose → [model] → restricted English → [grammar] → IR → [validate] → run
                   ↑ you read and edit   ↑ deterministic, confidence 1.0
```

The model drafts a **sentence**, never the rule. The deterministic grammar that has compiled the
eleven shipped controls since slice 9 still builds the IR, the same validator still accepts or
refuses it, and a wrong field name is refused **by name**. A composed rule is filed as a *draft* and
is not counted among the eleven. The default backend is a model on your own machine — free, offline,
and no dependency; a hosted one is opt-in. **No verdict depends on a model call**, and no model
client exists inside the engine.

Try it:

```bash
python3 -m pytest -q                          # 3,378 tests, offline, no dependencies
python3 -m hotelcontrols.web.server           # the demo at http://127.0.0.1:8765/
python3 -m tools.probe --plan                 # what a live probe would ask. Makes no calls
cd ui && npm ci && npm run build && npm start # the React UI at http://127.0.0.1:3000/

HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub    # + /compose, no model needed
HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm local   # + /compose, backed by Ollama
HOTELCONTROLS_AUTH_SECRET=<32+ chars> python3 -m hotelcontrols.web.server   # signed tenant contexts required (ui/README.md)
```

v1 is preserved in `miniHotelLegacy/` — four silos, 152 passing tests, one control working end to
end. Reviewing it produced 12 things worth keeping and 20 findings worth fixing; the headline is
that only 1 of its 10 controls ever reaches a PASS or a FAIL.

Start with **[`docs/plan-v3.md`](docs/plan-v3.md)** for where the build is, or
**[`CLAUDE.md`](CLAUDE.md)** for a two-minute orientation.

## Documentation

| | |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Orientation, conventions, and the seven facts that will bite you |
| [`docs/project-explainer/`](docs/project-explainer/) | Business case → code, for a newcomer: overview, file map, architecture diagrams, and one record traced end to end. Its README holds the measured numbers |
| [`docs/prd.md`](docs/prd.md) | What we are building and the twelve criteria that decide whether we did |
| [`docs/architecture.md`](docs/architecture.md) | Eight layers, their interfaces, what each hides |
| [`docs/plan.md`](docs/plan.md) | The v2 build log: every TDD slice with its test gates, slices 0 to 15, and criterion 1's arithmetic |
| [`docs/plan-v3.md`](docs/plan-v3.md) | v3: every StayOps gap's disposition, slices 16 to 24, every fix since, and criteria V1–V12 |
| [`docs/context.md`](docs/context.md) | How we got here, and every decision with its reason |
| [`docs/open-questions.md`](docs/open-questions.md) | Everything we know we do not know, and what the engine does meanwhile |
| [`docs/session-handoff.md`](docs/session-handoff.md) | The starting prompt for the next coding session, and the state since 2026-10-09 |
| [`docs/old-codebase-improve.md`](docs/old-codebase-improve.md) | The v1 review |
| [`docs/stayOps_Cotrols_Rule_Engine_V2.md`](docs/stayOps_Cotrols_Rule_Engine_V2.md) · [`docs/stayops-gap-analysis.md`](docs/stayops-gap-analysis.md) | The wider StayOps product's intent, and its requirements against what existed on 2026-09-28: v3's input |
| [`docs/poc-comparison-brief.md`](docs/poc-comparison-brief.md) | A brief for a comparison with a second implementation, never started |
| [`docs/QA.md`](docs/QA.md) | Running Q&A transcript |
| [`ui/README.md`](ui/README.md) | The React UI: how it is built, how it is tested, and why each dependency is there |

## Running it

The engine requires **Python 3.11+ and nothing else** — there is no install step and no runtime
dependency:

```bash
python3 -m hotelcontrols.web.server                # the demo at http://127.0.0.1:8765/
```

Running the **tests** needs the two development tools, which the engine itself never imports:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q    # the suite, fully offline
.venv/bin/python -m coverage run -m pytest && .venv/bin/python -m coverage report
python3 -m tools.validate_spec                             # spec and fixture validation
python3 -m tools.transcode_demopms --check                 # the demo fixtures are up to date
```

The **React UI** is optional and separate. It needs Node 22.22.2 or later, and talks to whichever
engine `HOTELCONTROLS_API_URL` names (default `http://127.0.0.1:8765`):

```bash
cd ui && npm ci                       # exactly the locked versions
npm test                              # component tests + the parity harness, from golden payloads
npx playwright install chromium && npm run e2e   # computed styles, keyboard, accessibility
npm run build && npm start            # the UI at http://127.0.0.1:3000/, engine running first
```

Its tests never start the engine. They render from `fixtures/api/`, the JSON API's responses
generated by `python3 -m tools.dump_api_fixtures` and checked byte-for-byte by the engine's suite.

`PYTHONDONTWRITEBYTECODE=1` is a correctness gate, not hygiene: an edit that changes neither a
file's size nor its mtime-second leaves a stale `.pyc` valid, so the suite runs the old code and
reports a green that means nothing. That happened twice during v1.

**No test touches the network, or a model** — `tests/unit/test_stdlib_only.py` walks the source tree
and asserts the engine contains no outbound HTTP client at all, and
`tests/unit/test_proposers_refuse_in_tests.py` asserts the same about model backends: they live
outside the engine, and both refuse to arm inside a test process even with their environment
variable set.

## A note on the data

`fixtures/minihotel/` holds real responses captured from MiniHotel's public sandbox, then
**pseudonymised**: guest names, email addresses, phone numbers and free-text remarks are replaced
with stable fakes. Every structural quirk — date formats, currency splits, unset-means-zero, status
codes — is preserved exactly, because those quirks are the entire point of the fixtures. They form
four named **captures**: `sandbox2024`, `sandbox2026` (the demo's default), `sandbox2026refresh`
(v3's four-call refresh) and `sandbox2026cover` (#71's two calls). Each one answers only the
questions it actually recorded.

`fixtures/demopms/` is the **same hotel in a different wire format**, generated from those captures
by `tools/transcode_demopms.py` rather than written by hand — including the gaps. The folios nobody
captured are still missing, the statuses nobody can name are still unnameable, and the 23 rooms with
no configured capacity are still unconfigured. A demo hotel that knew more than the real one would
make the two-provider test pass by being a different hotel. Runs over it report
`evidence_is_synthetic`, because a run over records this repository produced must say so.

`fixtures/api/` holds the JSON API's answers for the full matrix: every control, property and
capture, plus history, readiness, the compose window's states and the guest routes' decisions.
They are **generated, never edited**. They are the contract the React UI is built against, so a
change that alters a payload shows up as a failing rebuild here rather than as a broken screen
later.

Nothing in this repository is invented to reach a nicer answer, and no credentials are stored here.
