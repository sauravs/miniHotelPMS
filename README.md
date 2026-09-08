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

**v2 is specified and about to be built.** v1 is preserved in `miniHotelLegacy/` — four silos, 152
passing tests, one control working end to end. Reviewing it produced 12 things worth keeping and 20
findings worth fixing; the headline is that only 1 of its 10 controls ever reaches a PASS or a FAIL.

Start with **[`docs/plan.md`](docs/plan.md)** for where the build is, or
**[`CLAUDE.md`](CLAUDE.md)** for a two-minute orientation.

## Documentation

| | |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | Orientation, conventions, and the seven facts that will bite you |
| [`docs/prd.md`](docs/prd.md) | What we are building and the twelve criteria that decide whether we did |
| [`docs/architecture.md`](docs/architecture.md) | Eight layers, their interfaces, what each hides |
| [`docs/plan.md`](docs/plan.md) | Twelve TDD slices with test gates |
| [`docs/context.md`](docs/context.md) | How we got here, and every decision with its reason |
| [`docs/old-codebase-improve.md`](docs/old-codebase-improve.md) | The v1 review |
| [`docs/open-questions.md`](docs/open-questions.md) | Everything we know we do not know |
| [`docs/QA.md`](docs/QA.md) | Running Q&A transcript |

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
```

`PYTHONDONTWRITEBYTECODE=1` is a correctness gate, not hygiene: an edit that changes neither a
file's size nor its mtime-second leaves a stale `.pyc` valid, so the suite runs the old code and
reports a green that means nothing. That happened twice during v1.

**No test touches the network** — `tests/unit/test_stdlib_only.py` enforces it by walking the source
tree and asserting the engine contains no outbound HTTP client at all.

## A note on the data

Fixtures are real responses captured from MiniHotel's public sandbox, then **pseudonymised**: guest
names, email addresses, phone numbers and free-text remarks are replaced with stable fakes. Every
structural quirk — date formats, currency splits, unset-means-zero, status codes — is preserved
exactly, because those quirks are the entire point of the fixtures.

No credentials are stored in this repository.
