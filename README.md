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

**Slices 0–8 of 12 are built and merged** — the kernel, the spec layer, both providers, evidence
gathering, the evaluator, the runner, the contract suite and the execution model. 1086 tests, 95%
coverage, 1003 spec checks, offline, green on Python 3.11 and 3.13. The English compiler, the web UI
and the opt-in live transport are still to come.

The claim the architecture rests on is now checked rather than asserted: **the same rule, over the
same hotel, through two completely different PMS wire formats, produces the same verdicts** — and
adding the second one changed nothing above the provider layer.

v1 is preserved in `miniHotelLegacy/` — four silos, 152 passing tests, one control working end to
end. Reviewing it produced 12 things worth keeping and 20 findings worth fixing; the headline is
that only 1 of its 10 controls ever reaches a PASS or a FAIL.

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
python3 -m tools.transcode_demopms --check                 # the demo fixtures are up to date
```

`PYTHONDONTWRITEBYTECODE=1` is a correctness gate, not hygiene: an edit that changes neither a
file's size nor its mtime-second leaves a stale `.pyc` valid, so the suite runs the old code and
reports a green that means nothing. That happened twice during v1.

**No test touches the network** — `tests/unit/test_stdlib_only.py` enforces it by walking the source
tree and asserting the engine contains no outbound HTTP client at all.

## A note on the data

`fixtures/minihotel/` holds real responses captured from MiniHotel's public sandbox, then
**pseudonymised**: guest names, email addresses, phone numbers and free-text remarks are replaced
with stable fakes. Every structural quirk — date formats, currency splits, unset-means-zero, status
codes — is preserved exactly, because those quirks are the entire point of the fixtures.

`fixtures/demopms/` is the **same hotel in a different wire format**, generated from those captures
by `tools/transcode_demopms.py` rather than written by hand — including the gaps. The folios nobody
captured are still missing, the statuses nobody can name are still unnameable, and the 23 rooms with
no configured capacity are still unconfigured. A demo hotel that knew more than the real one would
make the two-provider test pass by being a different hotel. Runs over it report
`evidence_is_synthetic`, because a run over records this repository produced must say so.

Nothing in this repository is invented to reach a nicer answer, and no credentials are stored here.
