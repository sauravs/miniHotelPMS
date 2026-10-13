# Session handoff

**To resume, paste [the starting prompt](#the-starting-prompt--paste-exactly-this) into a fresh
session, exactly as written.** The longer block after it is the STATE block the prompt tells the
session to read. Do not paste that one. Everything either references is in the repository;
nothing depends on the previous conversation.

**Last updated:** 2026-10-13, after **#109 merged** (PR #112, `46413b4`).
**The owner's list (4, 1, #87's guard, 3, 2, 5) is DONE, and so is #109** (#87's option 2,
design P1-P6 approved as written, built end to end). **Nothing further is approved.** The next
session reports the state and asks the owner what is next - it starts no work on its own.
**v2 (slices 0–15) and v3 (slices 16–24) are both COMPLETE.** Criteria V1–V12 are all met
(`docs/plan-v3.md` §7); `prd.md` criterion 1 stays NOT MET on every capture (`sandbox2026` 2 of
11, refresh 1, covering capture 5). **No issue is open.** An item marked DONE has merged.

**The live probe** is a runbook now: [The probe](#the-probe--done-2026-10-10-v3-slice-23-kept-as-the-runbook-for-the-next-one).
Since slice 24 its credentials are per property: `HOTELCONTROLS_SANDBOX_MINIHOTEL_*`. **No live
call is approved.**

---

## The starting prompt — paste exactly this

v3 is complete, every follow-up on the owner's list is DONE, and #109 is DONE. Nothing is
approved next: this session reports and asks.

```
Continue miniHotelPMS after v3 and #109. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

Start-up, before anything else:
  git status && git branch --no-merged main     # LOCAL list: empty
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -o addopts=""    # 3378 passed, 3 skipped
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec        # PASSED - all 1098 checks
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.dump_api_fixtures --check   # 228 files
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.transcode_demopms --check   # 17 files
  .venv/bin/python -m coverage run -m pytest && .venv/bin/python -m coverage report   # 97%
  cd ui && npm ci && npm run typecheck && npm test && npm run e2e          # 249 Vitest, 26 Playwright
  gh issue list --state open                     # none
Those are main's numbers (46413b4 or a docs-only commit after it). Any that differs is a reason
to stop and find out why. Then read CLAUDE.md, docs/session-handoff.md (the STATE block),
docs/plan-v3.md (status table, §7), docs/open-questions.md.

WORKING AGREEMENT (owner): every item is a bug-workflow fix or a small PR of its own - a GitHub
issue first (what, reproduction, which gate, severity), then fix/NN-..., a failing test, the
fix, a PR "Fixes #NN", CI green on test (3.11) and test (3.13), squash-merge. After each item
ends end to end, REPORT and WAIT for the owner's go-ahead. Before starting anything new, write
the next session's starting prompt into docs/session-handoff.md as a docs-only PR. Recommend one
option at every decision.

GO-AHEAD: NONE. Report the start-up numbers to the owner and ask what is next. Do not start an
item, open an issue for new work, or make a live call without the owner's explicit yes.
Candidates the owner may choose from (none approved; recommend one when asked):
  - the deferred items below;
  - a wider occupancy horizon for ooo_room_protection - needs MiniHotel's agreed limits first
    (open question 2.6), then a version bump; NOT before;
  - criterion 1 stays NOT MET; anything aimed at it is the owner's call.

DONE, for the record: follow-ups 4, 1, #87-guard, 3, 2, 5 (see the STATE block), and #109
(PR #112, 2026-10-13): #87's option 2. Under mode `none` a collection is judged per record (FAIL
naming the record; else UNKNOWN if one could not be judged; else PASS only if the collection is
complete); population.reference_windows bounds the occupancy reference to today..today+7d; the
owner chose an explicit `absent` key for P4 (`room.closed_to at least "today" or absent`);
ooo_room_protection is version 4, still EXCLUDED 28 on every capture; 16 goldens declared.

Deferred - do NOT start these without the owner's explicit say-so: emailing guest tasks; a React
guest view; offering the refresh capture (sandbox2026refresh) in the demo.

Live calls: none approved. If one ever is, it needs the owner's yes to that exact call, printed
first with tools.probe --plan (credentials in the git-ignored .env as
HOTELCONTROLS_SANDBOX_MINIHOTEL_*). Never print, paste or commit a credential.

Rules that outrank everything: never widen a verdict; never edit a fixture to pass a test;
never hit the live API without the owner's yes to that call; no credential or third-party
personal data in a committed file.
```

## The STATE block — read by the session, not pasted

```
Continue building miniHotelPMS. Working directory: /Users/sauravs/Desktop/Work/miniHotelPMS

FIRST, before reading anything: run `git status` and `git branch --no-merged main`. Anything
listed is work that never reached main - push it and open a PR, or delete it on purpose, but do
not leave it. Two branches sat unpushed for three weeks before anyone looked (one held the fix
that became issue #44), and no CI can see a branch that was never pushed. None is expected:
slice 23's branch was squash-merged and deleted, and fixes #72, #74 and #76 before it.

Read these first, in order: CLAUDE.md, docs/plan-v3.md, docs/plan.md, docs/prd.md,
docs/architecture.md, docs/open-questions.md, docs/old-codebase-improve.md. They are the
specification and the execution trackers. docs/plan.md is the v2 build log (slices 0-15);
docs/plan-v3.md is authoritative for what is next (slices 16-24).

STATE: v2 IS COMPLETE (slices 0-15) AND v3 IS COMPLETE (slices 16-24, docs/plan-v3.md). Merged:
fix #48 (#52), slice 16 (#53), fix #54 (#55), slice 17 (#56), fix #57 (#58), slice 18 (#61),
slice 19 (#62), slice 20 (#63), slice 21 (#65), slice 22 (#68), fix #70 (#72), fix #73 (#74),
fix #75 (#76), slice 23 (the evidence refresh, #77), slice 24 (host auth + per-property
credentials, closing #22 and v3); after v3, follow-up 4's fixes #84 (#88), #85 (#89) and #86
(#90); for follow-up 1, fix #92 (#93), the covering capture (#94) and fix #71 (#95); fix #87
(#98); for follow-up 3, fix #100 (#101); for follow-up 2, fix #103 (#104); for follow-up 5,
fix #106 (#107); and fix #109 (#112), #87's option 2. Baseline on main at 46413b4: 3378 passed
/ 3 skipped (the v3 scope guard always skips: no slice/16-* .. slice/24-* branch remains), 1098
spec checks, 228 API goldens identical to a rebuild, 17 DemoPMS files identical to a rebuild,
spec lock current, 97% coverage. The React UI has 249 Vitest and 26 Playwright tests.
No issue is open. Nothing further is approved.

#109 IS DONE (2026-10-13, PR #112) - #87's option 2, design P1-P6 approved as written before any
code. evaluator/collections.py: under mode `none` a predicate reading a `collection` is judged
once per related record - FAIL naming the record, else UNKNOWN if one could not be judged, else
PASS only if the collection is complete for the question: the record's own dates its predicates
place the collection's dates against, from the day asked onward, must lie inside the window it
was fetched for; otherwise UNKNOWN naming the uncovered dates (an open-ended closure can FAIL,
never PASS). joins[entity] is read BEFORE related, so a refused reference or unreadable key is
UNKNOWN, never "no guests". A remote record whose key cannot be read is kept as UNPLACED (the
refresh capture has two: 007004312/313, 08..13 Jul, room number empty) and keeps a room UNKNOWN
if it would fall in its closure - found while building, recorded on #109. Evidence:
population.reference_windows (deployment half; spec/schema.py now honours an additionalProperties
schema, which it used to skip) resolved by the property clock, mapped by each adapter (DateRange /
window - the same request resource_occupancy_consistency asks); Bundle.windows (FetchedWindow:
start, end, asked_on) and Bundle.unplaced; the probe prints the windowed request. P4 needed a
checkpoint while building: clauses AND, the grammar has no OR, and `gte` on an absent end was a
TypeError - the OWNER CHOSE an explicit `absent` key (grammar `or absent` / `if present`; orderings
only, on a field whose absence is a fact; without it an ordering on an absence is UNKNOWN). The
runner resolves `today` / `today+Nd` in a predicate's value (runner.with_dates_resolved); an
unresolved one reaching the evaluator is UNKNOWN. Validator checks 8-11. ooo_room_protection
version 4: v3's two overlap predicates, `room.closed_to at least "today" or absent`, a 7-day
window. Proof on both providers with stand-in sources (tests/integration/
test_closed_room_never_passes.py); each piece of the fix was broken in turn and caught. 16
goldens declared (ooo_room_protection's runs and listings: version, digest, the occupancy lines'
refusal reason); no outcome moved, still EXCLUDED 28. A wider horizon is a version bump after
MiniHotel agrees limits (2.6).

#87'S GUARD IS DONE (2026-10-13, PR #98). ooo_room_protection version 2 placed
occupancy.reservation_id in a window of dates; as strings "007004344" < "2026-07-10", so every
real id fell outside and the room PASSed - and a collection's fields were the FIRST segment's.
Now: validator check 7 (`within` needs a date or datetime field, by canonical type; the compiler
is refused the same way); the evaluator answers UNKNOWN for a unit-less value in a window and for
any predicate reading a `collection` field (naming the record count); a contract test pins that
every known date carries a date unit; the rule is version 3 (locked): a segment starting in the
window, or the window opening during a segment. Reproduced with a STAND-IN source (the refresh
capture's documents, room 303 closed 10..20 Jul in memory, no fixture edited): version 2 PASSed
it with guest 007004367 inside. Worth knowing: since #71 the occupancy reference asks no window,
so replay refuses it on EVERY capture - on frozen evidence #87 was hidden, not prevented. Option
2 (judge every record of a collection, Kleene `none` across segments) needs that reference to ask
a window too; it is issue #109, design approved 2026-10-13 (P1-P6), built since (PR #112, see above).

FOLLOW-UP 1, #71, IS DONE (2026-10-11..13, PR #95). Replay picked the FIRST response of an
endpoint in a capture and compared only windows both questions name, so seven controls asking an
arrival or create window were answered from sandbox2026's departure window - part of a population
presented as the whole, behind three of criterion 1's five. Now both frozen sources answer only
from the response whose recorded question covers the ask, and refuse (a) a window never named,
(b) a wider window, (c) a recorded narrowing the run does not ask. Two live calls, EACH approved
by the owner at the time (2026-10-11 arrivals 2026-07-08..10-06 + prices, 385 bookings;
2026-10-13 created 2026-06-08..07-08, 150), are the covering capture sandbox2026cover =
sandbox2026's responses + those two, transcoded to demo2026cover (#94, after #92 let the probe
print the first call). The owner's A+B: the demo offers the covering capture beside sandbox2026,
whose default is unchanged. Criterion 1 per capture: sandbox2026 2 of 11 (the two checkout
controls; the seven others are refused), refresh 1 (occupancy), sandbox2026cover 5 from the right
evidence; NOT MET on each, both providers agreeing. 48 run goldens' answers moved, declared in
test_v1_no_answer_changed.py; 44 goldens are new (the cover runs, 18 MB on disk, ~330 KB
gzipped). Two traps worth remembering: the transcoder reads through the same replay, so a replay
bug can reproduce itself in a "byte-identical" DemoPMS rebuild (TestEachFileHoldsItsWholeSource
now compares each demo file with its source directly); and a test that reads a whole response
must ask the question the capture RECORDED, because an empty request is refused as "everything,
ever". Open question 1.4 changed: on the covering capture a decided rate-code list now MOVES
control 15 (example Tourist-BB: 15 PASS / 56 FAIL), so it must be a real property's.

FOLLOW-UP 4 AUDITED #75's SIXTEEN absent_means "false" FIELDS (2026-10-11; the table is on #75).
An absence read as known False is right for `exists` and wrong as a KEY: stringified, every
absence is the key "False". Three keys were fixed, each under its own issue, each latent (no
committed capture has an empty key, so no golden moved): #84 occupancy.reservation_id (two
id-less segments in one room were one reservation, never compared - a false PASS); #85
reservation.id (id-less bookings on one portal id counted as one - a false PASS - and a folio
call was sent for reservation False; `_count_lte` now treats an unreadable id as possibly
another reservation instead of dropping it); #86 the stay-to-room join (an absent key on both
sides matched; `reference.absent_key()` is never indexed or looked up; room.number -> unknown;
stay.room_number keeps "false" because four scopes EXCLUDE on it). #87 was found on the way (fixed
since, PR #98 - see above): ooo_room_protection asserts `occupancy.reservation_id within room.closed_from..
room.closed_to` on the first collected segment only, so a guest inside a closed window PASSes.
No evaluator code reads `Bundle.related`. Latent, because every room is EXCLUDED.

SLICE 24 CLOSED v3 (2026-10-11). The owner delegated every open point to the implementer ("pls u
decide as an expert"), recorded with each decision in docs/plan-v3.md's status table. D14 built:
the host authenticates, the engine verifies. hotelcontrols/web/auth.py checks a short-lived
HMAC-SHA256 tenant context (header X-HotelControls-Context) with hmac.compare_digest, its
audience, an expiry judged by the injected clock (at most 15 minutes ahead) and a served
property; App._authenticate is the ONE choke point and overwrites `property` before any route
runs. OFF unless HOTELCONTROLS_AUTH_SECRET is set (32+ characters) - then every golden is
byte-identical; HOTELCONTROLS_AUTH=1 with no usable secret refuses to start. Credentials are per
property (#22): HOTELCONTROLS_<PROPERTY>_<PROVIDER>_*, NO fallback - the sandbox's are
HOTELCONTROLS_SANDBOX_MINIHOTEL_*. ui/ signs with node:crypto behind a development sign-in that
says it is a stand-in; ui/test/fixtures/auth-vector.json pins the two signers to one string.
#71 was sequenced here and is now FIXED (PR #95, see FOLLOW-UP 1 above).

SLICE 23 REFRESHED THE EVIDENCE (2026-10-10). Four live calls, EACH approved by the owner at
the time: getRooms, getRoomTypes, RoomStatusInquiry 2026-07-08..15, and the 2026 reservation
window re-asked WITH room prices. They are a NEW capture, sandbox2026refresh (index records
captured_at 2026-10-10 and calls: 4; nothing borrowed from an older capture), transcoded to
demo2026refresh. The engine's capture lists were a must-not, so the demo does NOT offer it:
tests/e2e/test_refresh_capture.py builds it directly. Question 1.2: R12 still true (23 of 28),
R11 still true, no closed-date window still true, Bulk ARI not re-checked. #49: stay.rate_code
on 126 of 136 stays; control 15 still UNKNOWN because the sandbox's codes are not decided.
Criterion 1 PER CAPTURE: sandbox2026 5 of 11 (unchanged), sandbox2026refresh 4 of 11 -
occupancy concludes for the first time, the checkout controls stop at UNKNOWN for want of a
folio (none was re-taken). Both providers agree on all 11. On the way it found four defects,
each filed before it was fixed: #70 the probe's --run did not send what --plan printed (fixed,
#72); #73 the scrubber left the occupancy response's guest names (fixed, #74, re-scrubbing
4_RoomStatus.xml with the owner's approval); #75 an empty occupancy room number read as a known
False - a false FAIL, or a PASS on no room (fixed, #76); #71 replay compares windows only by
name, so an arrival-window question is answered from a departure-window capture unchecked -
three of criterion 1's concluding controls rested on it (fixed since, #95: the refresh now
concludes 1 of 11). The owner's .env (git-ignored) holds the sandbox account;
the auto-mode classifier asks before each live call.

THE OWNER'S WORKING AGREEMENT (2026-10-10): report after each slice ends end to end, and WAIT
for a go-ahead before opening the next one.

SLICE 22 BUILT GUEST SERVICES (#68). spec/guest/late_checkout.json is the APPROVED decision
table (the owner accepted the implementer's recommendation on all five points; two fixed the
draft: only checked_in reaches the time rules, and checked in after the departure date is
STAFF_REVIEW). 11 ordered rules, gaps first. hotelcontrols/guest/ is pure and refuses a table
that is not approved or whose rules differ from guest.RULES; the template digest is pinned to
its version in tests/unit/test_guest_template.py. The request is a reservation id + HH:MM (slice
21's reader); the policy is a guest_services.LATE_CHECKOUT block per tenant, typed by slice 21's
ParameterSchema - null on sandbox and demo, so they answer STAFF_REVIEW to everything. Evidence
is evidence.gather, unchanged, over a one-call departures window (yesterday..tomorrow). A
`decisions` table, tenant-scoped; one decision and one task per double submission (identity
includes received_on, the property's day); DENIED raises none. Guest tasks live in `actions`
with kind guest_request, and /queue and /api/actions list violations only. Routes: POST
/api/guest/requests, GET /api/guest/decisions[/<id>], /guest. NOT DONE, FLAGGED: no goldens
(done since, #100 - fixtures/api/guest/) and no React guest view (tools/dump_api_fixtures.py was outside the slice), guest tasks not emailed.

SLICE 21 MADE "NOT DECIDED" A STATE. spec/parameters.json types every tenant setting
(text_list, text_list_map, money, time_of_day, choice; required stated; NO defaults) and
TenantConfig.load refuses a wrong type, unit or currency by name. null = not decided: declared
(has_setting) but kept OUT of tenant.settings, which is what runner/run.py hands the evaluator,
so the evaluator's existing "has not supplied X" branch answers UNKNOWN naming it - no
evaluator change. The sandbox and demo state nominated_rate_codes and
rate_plan_permitted_room_types as null. The owner delegated that call to the implementer
("you decide as an expert"), who decided yes after showing the dry run: no count or outcome
moved; 24 reasons per 2026 capture now name the parameter (4 goldens, in DECLARED, pinned
against 7f384c4 by tests/integration/test_typed_parameters.py). Tenants state the currencies
their records show (EUR, ILS, USD), observed, not decided. FLAGGED, NOT FIXED: the comment at
hotelcontrols/evaluator/predicates.py:145-147 still says that branch means "never declared"; it
now also means "not decided". evaluator/ was a must-not for slice 21.

THE FINDINGS QUEUE EXISTS (slices 18-20). A FAIL of a REVIEWED control raises one task in the
`actions` table, keyed (property, control, policy version, record); UNKNOWN/EXCLUDED, a blocked
run and a run that concluded nothing raise none. Drafts raise none (their action block is
borrowed) - a call made in slice 18 and still awaiting the owner's confirm. A person moves a task
pending -> done | dismissed; a later PASS annotates and never closes. /queue and /api/actions
state each control's latest conclusion beside the tasks ("not an all-clear"). The demo store is
in memory unless --store PATH. Email (slice 19) is a Notifier protocol in the engine and an SMTP
backend in tools/notifiers/, wired only by `tools.serve --notify smtp`, behind
HOTELCONTROLS_NOTIFY=1 AND no test runner; an email never carries the verdict's reason. The
operational log (slice 20) is JSON lines from hotelcontrols/ops/, stamped by the injected clock;
the server attaches it to stderr (--log). FLAGGED: tools/serve.py was outside slice 20's
may-change line, so the compose launcher does not attach the log yet.

SINCE SLICE 17 EVERY STORE READ NAMES ITS PROPERTY: RunStore.load(run_id, *, tenant_id) and
RunStore.history(control_id, *, tenant_id). Links to /api/runs/<id> and /history/<id> carry
?property=. Drafts live in <drafts>/<property>/ir/. tests/unit/test_tenant_scoped_store.py fails
any SQL in store/ that touches a table in schema.sql without `tenant_id = ?` after its WHERE -
new tables (actions, decisions) are covered automatically. The plan-v3 status table holds the latest numbers;
a number that differs from it is a reason to stop and find out why.

TWO GUARDS RUN ON EVERY PUSH SINCE SLICE 16. tests/unit/test_v3_slice_scope.py fails a
slice/16-* .. slice/24-* branch that changes a path its plan-v3 §5 "May change" line does not
list (and an existing file where a slice promised new files only). If it fails: STOP and ask the
owner, never widen the table. tests/integration/test_v1_no_answer_changed.py compares verdicts,
counts and coverage of all 88 run goldens with 7f384c4 (V1); a declared change goes in its
DECLARED dict with the PR that made it.

EDITING A RULE MAKES A NEW VERSION. Change an IR's verdict-bearing content -> bump "version" ->
python3 -m tools.lock_spec. validate_spec fails an edit without a bump; every run names
policy_version + policy_digest; a run stored before slice 16 reads "version not recorded".

v3 IS COMPLETE (slice 24 closed it on 2026-10-11 and deleted docs/v3-implementation-brief.md;
read it with `git show bfd09a0:docs/v3-implementation-brief.md`). DONE: fix #48, slices 16
versioning, 17 tenant-scoped store, 18 findings queue, 19 email (two locks), 20 operational log,
21 typed hotel parameters with "not decided", 22 LATE_CHECKOUT (structured, advisory, no model),
23 the evidence refresh, 24 authentication at the host + credentials per property. No v3 slice
remains; what is open is listed in the starting prompt above and in plan-v3's status table.

SLICE 15 ADDED A SECOND SCREEN, AND THE ENGINE DID NOT MOVE. ui/ is a Next.js + React +
TypeScript CLIENT of the engine's JSON API (decision D11). The engine's own server-rendered
pages stay and still ship. On every slice/15-* branch a test failed if any engine file but
web/app.py changed. The UI renders from fixtures/api/ in its tests - the API's own answers,
GENERATED by tools/dump_api_fixtures.py and byte-checked by the engine's suite - so it never
needs the engine running and never triggers a run. Three traps it is built around:
  - a run that concluded nothing STILL CARRIES counts; the tile gate is coverage.concluded;
  - money is a string with its currency ("-490.75 ILS"); never parse it;
  - GET /api/run/ spends provider calls and writes a row; the UI runs only on a POST
    (a button), then re-reads /runs/<run_id> for free.
The rules that matter most about ui/ are enforced by the REQUIRED Python suite
(tests/unit/test_ui_hygiene.py, test_canonical_boundary.py walks ui/ too). The ui CI job
is deliberately NOT required, so npm can never block an engine fix.

SLICE 13 ADDED A MODEL, AND IT IS NARROWER THAN IT SOUNDS. `/compose` turns prose into a
RESTRICTED SENTENCE, which the same deterministic grammar and the same validator then turn
into a rule (decision D10). The model drafts TEXT. It never produces IR, never touches the
evidence layer or the evaluator, and NO VERDICT DEPENDS ON A MODEL CALL - a composed control
carries confidence == 1.0 and source == "grammar", because the parse was exact whatever
drafted the text it parsed.

Every model backend lives in tools/proposers/, OUTSIDE the engine, and is injected by
tools/serve.py. hotelcontrols/ still imports only the standard library: both AST guards -
test_stdlib_only.py and test_compiler_grammar.py's network guard - PASSED WITHOUT BEING
EDITED. Do not move a backend into the engine to "tidy up"; the guards will fail, and that
is the alarm working.

Default backend is a model on the operator's own machine (Ollama, free, offline, stdlib
urllib). A hosted one is opt-in and paid. `--llm stub` needs nothing installed and is the
only backend any test wires. The whole front end is OFF unless started via tools/serve.py:
`python3 -m hotelcontrols.web.server` behaves exactly as it always has. The React UI's
/compose follows the engine it points at: switched off is stated, never hidden.

COMPOSED CONTROLS ARE DRAFTS. They land in spec/drafts/, are badged unreviewed, and are
EXCLUDED from the criterion-1 figure below. Do not count one. Promotion is a deliberate
`git mv` into spec/ir/ plus `python3 -m tools.validate_spec`.

STILL UNVERIFIED: no live model call has ever been made from this repository. Nothing was
installed and no key was set when slice 13 shipped, so the first `--llm local` run is the
first real test of the Ollama round-trip itself. Everything either side of it is tested.
ELEVEN OF THE TWELVE SUCCESS CRITERIA ARE MET. Criterion 1 is recorded as NOT MET - 5 of 11
controls reach a PASS or a FAIL where the PRD asks for 8 - with each of the six shortfalls
traced to a fact about the property or the provider in docs/plan.md. DO NOT relax it.

THE PROBE WAS v3 SLICE 23, AND IT IS DONE (2026-10-10). A future refresh follows the same
runbook - "The probe" in docs/session-handoff.md: print ONE call with tools.probe --plan, get
the owner's yes to THAT call, send it with the same arguments plus --run --yes (one call, once,
no retry), scrub into a new file, add a new capture label, transcode. DO NOT run --run without
the owner saying yes to that specific call, each time (decision D3).

DO NOT BUILD WHAT v3 DISPOSED OF. docs/plan-v3.md section 4 gives every StayOps gap a
disposition with its reason. Mews is OUT (owner). Writing to a PMS is REJECTED (owner, 1.10).
G4, the payment-guarantee control, is BLOCKED even in its narrowed card-on-file form: all 228
captured cards are the placeholder Number="****", 216 of them expiring 2021-01, so it would PASS
everything (#48, MiniHotel question 2.8). A scheduler daemon and webhooks are DEFERRED/BLOCKED
for named reasons. Free text as evidence (1.5) stays the most dangerous thing that could be
built.

Keep working the same way:
  - TDD. Failing test first, written from the specification rather than from the code you
    intend to write. Every test names the IR clause, success criterion or risk id it protects.
  - One branch per slice (slice/NN-name) -> push -> PR -> CI must pass -> squash-merge.
    Bugs found outside the current slice get a GitHub issue FIRST, then fix/NN-desc, then a
    PR closing it. Update the slice table in docs/plan.md as you go.
  - Run: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.validate_spec
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.transcode_demopms --check
         PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tools.dump_api_fixtures --check
         cd ui && npm ci && npm run typecheck && npm test && npm run e2e
  - Zero runtime dependencies IN THE ENGINE. pytest and coverage are dev-only and
    hotelcontrols/ may never import them. ui/ has three runtime packages, pinned exactly,
    and adding one means editing a test on purpose. Coverage floor is 90%; raise it by
    adding real tests, never by lowering it.
  - A change to an API payload is a contract change: rebuild fixtures/api/ and READ the diff.
    The React UI's tests render from those files.
  - High comment density, explaining WHY and citing the risk id (R1, R7, R9, R12, R13, A5).
  - Never widen a verdict. Missing evidence is UNKNOWN. This outranks every other instruction.
  - Never edit a fixture to make a test pass, and never invent one to reach a nicer outcome.
    fixtures/demopms/ is GENERATED - change tools/transcode_demopms.py and rebuild.
  - Do not call the MiniHotel sandbox without asking me first, each time (decision D3).

Work through the remaining slices, reporting after each merge and WAITING for my go-ahead
before opening the next. Ask me at the brief's checkpoint (slice 24's brief check) and when a
decision is genuinely mine.
Before ending the session, update docs/session-handoff.md and the plan-v3 status table.
```

---

## What a fresh session needs to know that the docs do not spell out

### Decisions already taken — do not re-litigate

Recorded as D1–D11 in `docs/open-questions.md` §0. In short: all 10 dry-run controls made
executable (11 IRs after splitting control 6); stdlib-only runtime with pytest as a dev
dependency; live sandbox calls allowed but approved individually; a fictional JSON `DemoPMS` as
the second provider; a deterministic grammar compiler with an LLM adapter behind the same
validation gate; public repo with pseudonymised fixtures; PR-per-slice with a CI gate; control 6
split into `checkout_money_owed` and `checkout_unrefunded_credit`; **D9 — the model adapter is a
seam exercised against a stub, not a wired model**; **D10 — a model may draft a *sentence*, never a
rule**; and **D11 — a second, React surface, as an addition rather than a rewrite**, with compose
as its one owner-approved write path.

### What slice 22 built, in one paragraph

**Guest services, `LATE_CHECKOUT` (#68).** The decision table was approved before any code, and
`hotelcontrols/guest/template.py` refuses one that is not approved or whose rule ids, order or
decisions differ from `guest.RULES`. `decide(request, policy, evidence, today)` is pure. LC1 collects
every gap and answers `STAFF_REVIEW` naming all of them, so no later rule can run on a guess.
`look_up` hands the template's per-provider population to `evidence.gather` unchanged (one call,
departures yesterday..tomorrow). Every lookup failure is a gap: not found, window not captured,
budget spent, duplicate ids, no query. The fee is repeated `Money.plus`. `store.save_decision`
writes the decision and its task in one transaction, the task through slice 18's natural-key
insert. Real evidence used by the tests (sandbox2026, as of 2026-07-08): `007004343` checked in
and departing today, `007004334` cancelled, `007004348` checked out, `007004338` departing
tomorrow, `007004258` `OK4`. Seen failing: a planted unscoped `SELECT` on `decisions` (3 tests
red), and a planted model two imports away from `guest/`.

### What slice 21 built, in one paragraph

**Typed parameters, with "not decided" (#65).** `hotelcontrols/spec/parameters.py` and
`spec/parameters.json`: five types (`text_list`, `text_list_map`, `money`, `time_of_day`,
`choice`), `required` stated per parameter, and **no defaults** (a `default` key is refused).
`TenantConfig.load` types every setting and refuses each wrong value by name, all at once. `null`
is the only spelling of *not decided*. `TenantConfig.__post_init__` moves it into `undecided` and
out of `settings`, so the evaluator's existing "has not supplied" branch answers. That is why there
was no evaluator change, and a test pins the one runner line the mechanism depends on. The money,
time and choice types exist for slice 22, which declares its parameters in this vocabulary from
`spec/guest/` and may not change this layer. The declared change moved no count. Seen failing:
a planted `TenantConfig` keeping `None` in `settings` turned 16 tests red.

### What slices 18, 19 and 20 built, in three paragraphs

**Slice 18, the findings queue (#61).** `hotelcontrols/actions/records.py` is pure: `findings_from(run,
ir)` turns a run into tasks using the IR's own `action` block (severity, audience), read for the
first time. Only a FAIL raises one. The `actions` table enforces the natural key with a `UNIQUE`
constraint, is tenant-owned under slice 17's guard (seen failing on a planted unscoped `SELECT`),
and `make_run_id` is untouched. The web layer raises tasks after saving a run; `runner/` is
untouched. Issue #59 was resolved there: the mapping is proven on 007004348 (medium/finance, both
providers), money owed's 0 FAIL -> 0 tasks is stated as a fact at 32 instants, and its high/finance
mapping is proven on a constructed run. React has `/queue` too.

**Slice 19, email (#62).** `actions/notify.py` holds the `Notifier` protocol and `dispatch`, scoped to the
run's own FAILs. `tools/notifiers/smtp.py` is the only `smtplib` import in the repository, requires
verified STARTTLS, and refuses unless `HOTELCONTROLS_NOTIFY=1` and no test runner is loaded. Routes are
`HOTELCONTROLS_NOTIFY_<AUDIENCE>`, no default; a missing one leaves the task unsent *saying so*. One
email per task per channel through a claimed marker on the task. An email carries record id,
control, amount with currency and a link - never the verdict's reason, and a failure note never
carries an address. `tests/guest_details.py` collects every guest detail in the 2026 captures for
the no-PII tests.

**Slice 20, the operational log (#63).** `hotelcontrols/ops/log.py`: JSON lines through stdlib
`logging`, one per request, run and dispatch, each carrying tenant_id, run_id, control_id,
policy_version and provider, stamped by the injected clock - the formatter never writes the
`LogRecord`'s own time. No blocked reason, delivery note, address or query string is copied.
`evaluator/` and `providers/` import no logging.

### What slice 15 built, in one paragraph

`ui/` — Next.js 16, React 19, TypeScript, three runtime packages pinned exactly — is a client of
the JSON API and nothing more. Pages: the index (readiness per provider, the evidence picker,
drafts kept apart), the ask page (a form; the **Run** button is a POST Server Action that runs once
and redirects), `/runs/<run_id>` (a free re-read: verdicts, readiness and the F7 plan line), history
(gated on `concluded` exactly like a run), and compose (the only client component). Every request
goes through `ui/lib/api.ts`; the engine's own stylesheet is served on the UI's origin so both
screens share one set of criterion-2 rules; badge words come from `/api/outcomes`, never typed in
TypeScript; `ui/proxy.ts` sets a nonce CSP. On the engine side, `web/app.py` gained read-only routes
(`/api/controls`, `/properties`, `/history/<id>`, `/drafts`, `/outcomes`, `/plan/<id>`) and compose as
JSON. Found and fixed along the way, each with a guard: issue #35 (counts shown for a run that
concluded nothing, on the engine's own history page), the root `runs/` ignore rule silently
dropping two directories, Next's default 404 and error pages breaking the CSP, a prerendered 404
with no nonce, and a build-time rewrite that pinned the engine's address.

### What slice 13 built, in one paragraph

A third way into the compiler, one step earlier than the other two. `compiler/sentences.py`
holds a `SentenceProposer` protocol and `normalise()`, which asks an INJECTED proposer for a
sentence and hands it to `compile_sentence` - the same function `tools/validate_spec.py` has
used on the eleven shipped controls since slice 9. The sentence is shown in an editable box
before anything compiles, so what runs is what a person committed to rather than what a model
said. A proposer that cannot write the rule without inventing hotel policy asks a QUESTION
instead, and a question gets no button to run anything (§18). The system prompt is GENERATED
from spec/canonical_fields.json, the grammar's own OPERATOR_PHRASES and six shipped sentences,
so it cannot drift from the language it describes - a hand-written prompt would be a second
copy of the operator table that fails silently the day somebody adds an operator. Web: two new
routes behind a second entry point, `handle_post(path, body)`, so `handle(path)` stays a pure
function of a string and every docstring about that stays true. CSP is unchanged and the page
loads no JavaScript.

### What slices 9, 10 and 11 built, in three paragraphs

**Slice 9, the compiler.** `hotelcontrols/compiler/` — a restricted-English sentence compiles to
an IR; the IR goes through `spec.validate`, unchanged and unbypassed. The model seam is one
method, `propose(sentence) -> dict`, and its refusals are compared against `spec.validate` called
directly on the same document, message for message. Each control carries **two** sentences: the
prose a person wrote, and the controlled form. **The grammar parses 0 of the 11 prose sentences
and 11 of 11 restricted forms**, and a test fails if the first number rises — a lexicon that knew
"still owes money" would be an eleven-entry phrase book. A sentence cannot supply a
`population.provider_query` without naming a PMS, so the document splits: sentence owns the rule,
a *deployment* dict owns the query, trigger, freshness and action.

**Slice 10, the demo.** `hotelcontrols/web/` — `handle(path) -> (status, content_type, body)` is a
pure function of the path, so the whole demo is asserted as strings. UNKNOWN is told apart from
FAIL by wording (asserted with every tag stripped), border style and hue. A run that concluded
nothing, and a blocked run, show **no count tiles**. `as_of` defaults to the instant the capture
declares it describes.

**Slice 11, the transport.** `hotelcontrols/providers/transport/` is built, tested and **off**.
Two locks: an environment variable, and a refusal to arm while a test runner is loaded — because
an environment variable alone is a lock a test opens in one line. Exactly one file in the engine
imports an outbound HTTP client. `providers/minihotel/live.py` holds the request forms,
**transcribed from the calls that produced the captures**, never from documentation; `BulkARI` is
refused because its request was never recorded. `python3 -m tools.probe --plan` prints the
endpoint, the resolved window, the stage, the cost against the property's budget and the exact
request body, with `<user>` and `<password>` where the credentials go — so the thing being
approved (decision D3) is the thing that would happen.

### Success criterion 1 is recorded as NOT MET, and stays that way

5 of 11 controls reach a PASS or FAIL on the covering capture `sandbox2026cover`; the PRD asks for
8. Since #71 (2026-10-13) it is measured per capture: `sandbox2026` 2 of 11, the refresh 1, the
covering capture 5, the only one asked the controls' own questions. **Do not relax the criterion.** The six
shortfalls are traced one by one in `docs/plan.md`, and none is a defect in the engine. It used to
say three would move on a conversation. **Measured 2026-10-09, it is one** (`OK4`/`WL`). The two
rate-code controls also need a capture taken with room prices (#49, v3 slice 23).

It was 6 until issue #9 was fixed: `resource_occupancy_consistency` had been reaching two PASSes
about July 2026 from occupancy segments captured in August 2024, because the frozen source's
window guard checked three filter names instead of every window. **That is the shape of defect
this project exists to catch, and the number went down rather than the guard going away.**

### The probe — done 2026-10-10 (v3 slice 23), kept as the runbook for the next one

**Status: done.** Four calls, each approved by the owner at the time, captured as
`sandbox2026refresh`; what they found is in `docs/open-questions.md` 1.2. What follows is how it
was done, for whoever refreshes the evidence next. On this machine the four credentials live in
a git-ignored `.env` the owner wrote; each call ran as
`set -a; . ./.env; set +a; HOTELCONTROLS_LIVE=1 SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/python -m tools.probe --run --yes <the approved arguments>`.
`SSL_CERT_FILE` is there because this python.org build ships no CA bundle (v1 hit the same), and
it keeps certificate checking ON.

**Print it first, always, one call at a time:**

```bash
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity --endpoint getRooms
python3 -m tools.probe --plan --property sandbox --control room_assignment_type_validity --endpoint getRoomTypes
python3 -m tools.probe --plan --property sandbox --control resource_occupancy_consistency
python3 -m tools.probe --plan --property sandbox --reask 9_departures_2026-07.xml --with IncludeRoomPrices
```

`--plan` makes **no calls at all** — a test asserts that by making `FrozenSource.fetch` raise and
running the whole plan anyway. It prints the endpoint, the resolved window, the stage, the cost
against the property's budget, and the **exact request body**, with `<user>` and `<password>` where
the credentials go. That is the artefact decision D3 approves: the thing being approved is the
thing that happens. Since #70 that is tested: `--run` sends exactly the distinct requests the same
arguments print, each once (no transport retry), and refuses a plan it cannot send as printed.

**The three calls, and what each settles** (open question 1.2):

| call | what it settles |
| --- | --- |
| `getRooms` | Whether 23 of 28 rooms still report adult capacity `0` (R12 — the entire argument for `zero_is_unknown`); whether rooms 9900/9901/9902 still carry an undefined type (R11); and **whether any room now has a closed-date window set**, which is why `ooo_room_protection` and `room_assignment_active_room` currently exclude every record |
| `getRoomTypes` | The other half of R11 — are the codes still the nine we have |
| `RoomStatusInquiry` | A **7-day** window, deliberately small (R8). The only occupancy capture is stuck at one week of August 2024, which is why `resource_occupancy_consistency` is blocked on both evidence sets |

**To run it, once the owner has said yes to this specific probe:**

```bash
export HOTELCONTROLS_LIVE=1
# Per PROPERTY since v3 slice 24 (#22): HOTELCONTROLS_<PROPERTY>_<PROVIDER>_*, no fallback.
export HOTELCONTROLS_SANDBOX_MINIHOTEL_BASE_URL=...      # the sandbox host
export HOTELCONTROLS_SANDBOX_MINIHOTEL_USER=...
export HOTELCONTROLS_SANDBOX_MINIHOTEL_PASSWORD=...
export HOTELCONTROLS_SANDBOX_MINIHOTEL_HOTEL=...
# the SAME arguments as the plan that was approved, plus --run --yes. One call per command.
python3 -m tools.probe --run --yes --property sandbox --control room_assignment_type_validity --endpoint getRooms
```

The recording is dated the day the call is made (`observed_at`, by the property's clock), and
`as_of` is the day the plan resolved its windows against.

There are no defaults for any of those and there will not be any (F15). The transport refuses
without them and names the variable that is missing. **Never put a credential in a file in this
repository** — v1 hard-coded the vendor's published sandbox account in a file about to be pushed
public, which was defensible and made the habit dangerous.

**Afterwards, in this order:**

1. Responses land in `fixtures/minihotel/raw/`, which git ignores, each with the request that
   produced it. **Run `python3 -m tools.scrub_fixtures` before committing anything derived from
   them** — a live response carries guest names, emails, phone numbers and free-text remarks, and
   this repository is public (D6, F15).
2. Compare against what the 2024 capture says and **update open question 1.2 with what was
   actually found**, whichever way it goes. The four findings there are currently marked
   *unverified since the system changed*, which is a different status from *verified* and a
   different status again from *wrong*.
3. If closed-date windows now exist, the occupancy **reference** request needs a window too — it
   carries none today, so `providers/minihotel/live.py` refuses it as the unbounded query R8
   forbids. Deliberately left: that control excludes all 28 rooms anyway while no window has ever
   been seen. It becomes worth fixing the moment one is.
4. The first real call is also the first observation of this vendor's **error** behaviour. Issue
   #16 classified failures by status code, which is standard HTTP and needed no observation; what
   their error *bodies* look like is still unknown and stays unguessed until one is seen.

---

### Checkpoints that need the project owner

| Before | Decision |
| --- | --- |
| ~~now~~ | ~~Approve `docs/plan-v3.md`~~ — **approved and merged 2026-10-09, PR #50** |
| ~~v3 slice 21~~ | ~~Confirm the declared change~~ — **held 2026-10-09**: dry run shown; the owner delegated the call to the implementer, who decided yes (`nominated_rate_codes` and `rate_plan_permitted_room_types` → `null` on sandbox and demo). Merged in #65 |
| any time | Confirm or overrule slice 18's call that **drafts raise no tasks** (a draft's severity and audience are borrowed from its template) |
| ~~any time~~ | ~~Whether the compose launcher (`tools.serve`) should attach the operational log too (`--log`), in a later slice whose scope allows `tools/serve.py`~~ — **yes: follow-up 2, fix #103** |
| ~~v3 slice 22~~ | ~~Approve the `LATE_CHECKOUT` decision table~~ — **approved and merged, #68** |
| ~~v3 slice 23~~ | ~~Approval of each probe call at the time~~ — **four calls approved one by one, 2026-10-10; merged** |
| ~~v3 slice 24~~ | ~~Brief check: is the `ui/` development login acceptable as a labelled stand-in?~~ — **decided 2026-10-11 by the implementer at the owner's delegation, on four conditions; merged, #79** |
| ~~any time~~ | ~~Issue #71: when to fix the replay window-name gap~~ — **dry run shown 2026-10-13; the owner chose A, then A+B. Merged, PR #95** |
| ~~any time~~ | ~~Issue #87: how to fix `ooo_room_protection`~~ — **decided 2026-10-13 at the owner's delegation: the type guard on `within` first, after #71; merged, PR #98. Option 2 (judge every record of a `collection`) stays open** |
| any time | Ask MiniHotel what `<CreditCard Number="****" ExpirationDate="202101"/>` means (question 2.8, #48). It is the only thing that can unblock G4 |
| ~~any time~~ | ~~**The cheapest open win:** nominated rate codes for control 15 (1.4).~~ **Corrected (#49):** a list alone changes nothing, because `stay.rate_code` is absent from every capture. It needs slice 23's capture **and** a real property's list |
| any time | Ask MiniHotel what `OK4` and `WL` mean (question 2.1). They cover 44 of the 217 reservations ever seen, and they are why the known duplicate pair resolves to UNKNOWN rather than to an answer |

### Things that will look like bugs and are not

**The queue page says "this queue is held in memory and is lost on restart".** Correct: the demo's
store is `:memory:` unless the server is started with `--store PATH`. It says so rather than imply a
persistence it lacks (brief §8.8).

**The queue is empty and says "not an all-clear".** Correct. A task is raised only by a VIOLATION of a
reviewed control in a run made against this store. The table below the tasks says what each
control's latest run concluded; the only FAIL in all captured evidence is 007004348.

**"Email is not wired here".** Correct by default. Only `tools.serve --notify smtp` wires a notifier,
and it still refuses until `HOTELCONTROLS_NOTIFY=1` is set outside a test process. In JSON, `email`
and each task's `delivery` exist only when a notifier is wired - absent is not "not sent".

**`required_reservation_fields` says the property "has not supplied 'nominated_rate_codes'", although
the rate code is missing too.** Correct since slice 21. Both are true; the evaluator checks the
hotel's setting before the record's rate code, and the missing rate code (#49) still shows on every
record's evidence row. Do not "fix" it by supplying a list for the sandbox: it would invent a
hotel's policy and move no count. `validate_spec` lists the undecided parameters per property, as a
note, not a failure.

**`tools.serve` prints no JSON log lines.** Known and flagged: slice 20 could not change
`tools/serve.py`. `python3 -m hotelcontrols.web.server` writes them to stderr (`--log`).

**`/compose` says "No proposer is wired".** Correct. The front end is opt-in. Start it with
`HOTELCONTROLS_COMPOSE=1 python3 -m tools.serve --llm stub`. The same is true of the React UI's
`/compose`: it shows whatever the engine it points at can do.

**`test_no_engine_file_changed_on_a_slice_15_branch` is skipped.** Correct off a `slice/15-*`
branch. It is the slice-15 promise, scoped to that slice so later slices can still change the
engine. On a slice-15 branch it runs, and fails rather than skips if it cannot find `origin/main`.

**The `ui` check is red but the PR can still merge.** Deliberate: it is not a required check. Read
it anyway. The rules that must never break are duplicated in the required Python suite.

**npm warns `EBADENGINE` for jsdom.** jsdom 30 wants Node 22.22.2 or later. The suite still runs on
older 22.x, and CI uses a current Node 22.

**The React page renders unstyled.** Check that `HOTELCONTROLS_API_URL` names a running engine. The
UI serves the engine's own stylesheet, fetched at run time; with no engine there is nothing to
serve.

**A proposer refuses with "refuses to arm inside a test process".** Correct, and deliberate.
That is lock 2. An environment variable alone is one `monkeypatch.setenv` away, so there are
two. The local backend is held to it as well: localhost is still a socket.

**A drafted sentence gets refused naming a field that does not exist.** Correct - that is
§17's gate, and it is the behaviour the whole design is for. Do not add the field to the
vocabulary to make the refusal go away; a field no provider can supply is a fact about the
vocabulary, not a bug.

- `ooo_room_protection` excludes all 28 rooms, and `room_assignment_active_room` all 111 stays.
  No room in this property has ever had a closed-date window set (open question 2.4). The
  coverage verdict reports this rather than showing a reassuring zero.
- `room_capacity_compliance` answers for nobody: 23 of 28 rooms report adult capacity `0`,
  which means *unconfigured*, not zero (R12). On DemoPMS the same rooms report `-1`, and the
  canonical answer is the same UNKNOWN.
- `rate_room_category_consistency` is UNKNOWN everywhere on both providers. A reservation's rate
  code and a price-list code are different key spaces (R13) — structurally unresolvable.
- `resource_occupancy_consistency` is **blocked** on both standard evidence sets, and concludes
  perfectly well asked on 14 August 2024. See issue #9 above.
- Neither aggregate control reaches FAIL. The property genuinely has no active duplicate and no
  double-booked room. **Do not manufacture one.**
- The two providers **disagree about scheduling, on purpose**: `resource_occupancy_consistency`
  is event-driven on MiniHotel and hourly on DemoPMS, because only one publishes
  `room.occupancy_updated`. Criterion 7 is about verdicts, and those are identical.
- The grammar refuses *"every reservation arriving within 24 hours must …"* — the shape the
  requirements doc uses. That is deliberate and is explained in the refusal itself: a window on
  arrival bounds the population, which is per-provider deployment data.
- `--run` on the probe refuses even with `HOTELCONTROLS_LIVE=1` and `--yes`, inside a test. That
  is lock 2 and it is deliberate. Outside a test it refuses too, at the missing credential — the
  only thing between here and a live call is real credentials, which is exactly what D3 wants.
- The demo's history is in-memory and empty when the server restarts. `RunStore(":memory:")`
  is the default; point it at a file to keep runs between sessions.
- Every run over the 2026 captures reports its evidence as *captured after the instant asked
  about*. That is true — the bytes were fetched in September for a question about July — and it
  is neither stale nor fresh.
- `miniHotelLegacy/` is git-ignored on purpose: it holds unscrubbed guest data and hard-coded
  sandbox credentials, and this repository is public.

### Where the interesting parts are

| | |
| --- | --- |
| `hotelcontrols/kernel/` | `Value`, `Money` (Decimal), `Outcome`, `Verdict`, `Clock`. Five guarantees enforced in constructors |
| `hotelcontrols/spec/ir.py` | The validation gate everything writes through — six checks beyond the schema |
| `hotelcontrols/compiler/grammar.py` | Restricted English → IR, and the refusals that make it safe |
| `hotelcontrols/compiler/model.py` | The model seam. One method in, the same gate out, no network |
| `hotelcontrols/providers/registry.py` | adapters discovered by import, so no module above one names a PMS |
| `hotelcontrols/providers/*/paths.py` | structured addressing per wire format — the fix for the regex fragility in finding F4 |
| `hotelcontrols/evidence/reference.py` | the join stage that took three controls from 111/111 UNKNOWN to 97–98% |
| `hotelcontrols/evaluator/population.py` | aggregate assertions, and the two R7 guards |
| `hotelcontrols/runner/coverage.py` | finding F5 — a run that concluded nothing says so |
| `hotelcontrols/runner/scheduling.py` | finding F7 — when a control runs, and whether its evidence was current |
| `hotelcontrols/web/render.py` | criteria 2, 3 and 8 on screen. `WORDING` is the monochrome half of criterion 2 |
| `hotelcontrols/web/server.py` | the only file that knows a socket exists. Serial on purpose — see the comment |
| `hotelcontrols/web/app.py` | every route, both surfaces' JSON, and compose's shared core (`_turn`, `_file_draft`) |
| `tools/dump_api_fixtures.py` | writes `fixtures/api/`, the React UI's contract. A payload change shows up here first |
| `ui/lib/api.ts` | the only module in the UI that talks to the engine. The expensive call is findable |
| `ui/components/RunView.tsx` | the three states of a run, gated on `coverage.concluded` — never on whether counts exist |
| `ui/test/parity.test.tsx` | every run payload: no record dropped, duplicated or mis-grouped; every evidence row verbatim |
| `tests/unit/test_ui_hygiene.py` | what the React UI may never do, enforced by the required suite |
| `hotelcontrols/providers/transport/http.py` | the two locks, and the only outbound client in the engine |
| `hotelcontrols/providers/minihotel/live.py` | the request forms, transcribed from the calls that produced the captures |
| `tools/probe.py` | `--plan` prints what would be asked and makes no calls. This is what D3 approves |
| `tests/contract/` | one suite over every registered provider. Adding a PMS means running it, not writing it |
| `tests/integration/test_compiler_roundtrip.py` | every shipped sentence recompiled, clause for clause, then run |
| `tools/transcode_demopms.py` | the demo fixtures are generated from the vendor captures, gaps included |
| `tools/scrub_fixtures.py` | must run before any capture is committed |
