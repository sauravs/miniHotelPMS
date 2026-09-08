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
