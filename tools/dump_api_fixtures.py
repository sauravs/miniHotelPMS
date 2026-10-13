# -*- coding: utf-8 -*-
"""
Write the JSON API's golden payloads to fixtures/api/ - the contract a second client is built on.

    python3 -m tools.dump_api_fixtures            rebuild fixtures/api/
    python3 -m tools.dump_api_fixtures --check    verify a rebuild changes nothing

WHY THESE EXIST
---------------
Slice 15 adds a React UI as a second client of the JSON API. Its test suite must run with no
Python process and no socket, exactly as this one does, so it renders from these files. Three
things follow from that, and each is the reason for a choice below:

  - THEY ARE GENERATED, NEVER EDITED, like fixtures/demopms/. A test asserts a rebuild is
    byte-identical, so a change to `render.py` that alters the payload shows up here, as a
    failing rebuild, rather than as a broken UI three weeks later.
  - THEY ARE THE RESPONSE BODY, VERBATIM, plus one trailing newline. Each file is what `handle`
    returned for the path its own location names; nothing is reformatted, sorted or pruned.
  - THE REACT SUITE NEVER TRIGGERS A RUN. `GET /api/run/` spends provider calls and writes the
    store (trap 4 in the slice-15 brief, now in git history at 2ab809d). Reading a file does neither.

WHAT IS WRITTEN - the path mirrors the route
--------------------------------------------
    controls.json  properties.json  drafts.json          the index's three requests
    outcomes.json                                         the four answers' words, one source
    readiness/<control>.json                              one per control
    run/<control>.<property>.<evidence>.json              the FULL matrix, live
    runs/<run_id>.json                                    every one of those, re-read from store
    history/<control>.<property>.json                     after the whole matrix has run
    actions/<property>.json                               the findings queue, after it too
    actions/empty.<property>.json                         an untouched store's queue

Since slice 17 a stored run and a history are read FOR a property, so `runs/` is fetched with
the property each run belongs to (the body is the same), and history is one file per control
per property - a history golden that listed two hotels' runs together was exactly the read the
slice exists to make impossible.

Since slice 18 a run of a reviewed control raises a task per FAIL, so the queue after the whole
matrix is the queue the evidence produces: one task per property, for the one FAIL anywhere in
the captures (007004348, unrefunded credit). The untouched store's queue is the state a client
must render as "not an all-clear" - every control not run. New files only: nothing that existed
before slice 18 changes.
    compose/*.json                                        off, wired, and three kinds of turn
    guest/requests/<property>.<reservation>.<HHMM>.json   POST /api/guest/requests, answered
    guest/requests/refused.json                           one request refused (400)
    guest/decisions.<property>.json                       GET /api/guest/decisions, after them
    guest/decisions.empty.<property>.json                 an untouched store's decisions
    guest/decisions/<decision_id>.json                    GET /api/guest/decisions/<id>, each

The guest routes (slice 22; issue #100). The shipped properties have decided no late-checkout
policy, so every request there is STAFF_REVIEW naming the six undecided parameters - true, and
written. A client built on that alone would never see the other three decisions, so two TEST
properties, ids beginning `test_`, carry D2 §49's policy in a throwaway copy of spec/, exactly
as `tests/integration/test_guest_requests.py` builds them. No policy is invented for a shipped
property, and nothing is written into spec/.

`run/` and `runs/` are both complete so that every `run_id` a history row names resolves to a
file - the same promise the live API makes. `drafts.json` is the unwired state (`App()` with no
drafts directory), because a draft is a reader's working state, not part of the evidence.

The matrix is DISCOVERED - every control, every property, every capture its provider replays -
so a third provider or a new capture joins it by existing.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "fixtures" / "api"


def build() -> dict[str, str]:
    """Every golden payload, keyed by its path under fixtures/api/."""
    # Imported here, not at module level, so `--help`-style use of this file never loads the
    # engine - the same shape as the other tools.
    from hotelcontrols.spec import available, available_tenants
    from hotelcontrols.web import App

    app = App()               # in-memory store, default spec, no proposer, no drafts
    built: dict[str, str] = {}

    def take(path: str, name: str) -> dict:
        status, content_type, body = app.handle(path)
        if status != 200 or not content_type.startswith("application/json"):
            raise SystemExit("%s answered %d %s - a golden payload must be a 200:\n%s"
                             % (path, status, content_type, body[:400]))
        built[name] = body + "\n"
        return json.loads(body)

    take("/api/controls", "controls.json")
    take("/api/properties", "properties.json")
    take("/api/drafts", "drafts.json")
    take("/api/outcomes", "outcomes.json")

    controls = available()
    for control_id in controls:
        take("/api/readiness/%s" % control_id, "readiness/%s.json" % control_id)

    run_ids = []
    for control_id in controls:
        for tenant_id in available_tenants():
            for capture in app.captures_for(tenant_id):
                payload = take("/api/run/%s?property=%s&evidence=%s"
                               % (control_id, tenant_id, capture),
                               "run/%s.%s.%s.json" % (control_id, tenant_id, capture))
                run_ids.append((payload["run_id"], tenant_id))

    for run_id, tenant_id in run_ids:
        take("/api/runs/%s?property=%s" % (run_id, tenant_id), "runs/%s.json" % run_id)
    for control_id in controls:
        for tenant_id in available_tenants():
            take("/api/history/%s?property=%s" % (control_id, tenant_id),
                 "history/%s.%s.json" % (control_id, tenant_id))
    for tenant_id in available_tenants():
        take("/api/actions?property=%s" % tenant_id, "actions/%s.json" % tenant_id)
        # A fresh app: nothing run, nothing raised, every control "not run here".
        status, _ct, body = App().handle("/api/actions?property=%s" % tenant_id)
        if status != 200:
            raise SystemExit("an untouched queue answered %d:\n%s" % (status, body[:400]))
        built["actions/empty.%s.json" % tenant_id] = body + "\n"

    built.update(_compose())
    built.update(_guest())
    return built


def _compose() -> dict[str, str]:
    """The compose window's payloads: switched off, switched on, and the three kinds of turn.

    The stub proposer is deterministic and the conversation id is FIXED, so these rebuild
    byte-identically. The drafts directory is a throwaway: a golden payload is never allowed to
    write into spec/drafts/.
    """
    import shutil
    import tempfile

    from hotelcontrols.spec.registry import SPEC_DIR
    from hotelcontrols.web import App
    from tools.proposers import StubProposer

    out: dict[str, str] = {}
    out["compose/off.json"] = App().handle("/api/compose").body + "\n"
    with tempfile.TemporaryDirectory() as scratch:
        drafts = pathlib.Path(scratch) / "drafts"
        (drafts / "ir").mkdir(parents=True)
        for name in ("canonical_fields.json", "ir_schema.json"):
            shutil.copy(SPEC_DIR / name, drafts / name)
        app = App(proposer=StubProposer(), draft_dir=drafts)
        out["compose/wired.json"] = app.handle("/api/compose").body + "\n"
        for name, prose in (("refused", "VIP+rooms+must+be+inspected"),
                            ("question", "corporate+rates+must+belong+to+an+approved+company"),
                            ("compiles", "every+reservation+must+record+a+guest+email")):
            status, _ct, body = app.handle_post(
                "/api/compose", "conversation=golden&prose=%s" % prose)
            if status != 200:
                raise SystemExit("compose turn %r answered %d:\n%s" % (name, status, body[:400]))
            out["compose/%s.json" % name] = body + "\n"
        status, _ct, body = app.handle_post(
            "/api/compose/accept", "sentence=rooms+should+be+nice&control_id=nice"
                                   "&template=checkout_money_owed")
        if status != 422:
            raise SystemExit("a refused accept answered %d, not 422" % status)
        out["compose/accept-refused.json"] = body + "\n"
    return out


# D2 §49's policy, the worked example the decision table was approved against. Given to TEST
# properties only: the shipped ones decide nothing, and inventing a policy for them would be
# the anti-criterion.
D2_49 = {"free_until": "14:00", "charge_from": "14:00", "approval_required_after": "16:00",
         "maximum_time": "18:00", "fee_per_hour": {"amount": "25.00", "currency": "USD"},
         "hour_rounding": "started_hour"}
# Test property -> the shipped tenant whose vocabulary (and so whose provider) it borrows.
GUEST_TEST_PROPERTIES = {"test_d2_49": "sandbox", "test_d2_49_demo": "demo"}
# The sandbox2026 capture's day, 2026-07-08, holds each kind of guest a rule distinguishes - the
# nine cases criterion 7 is asserted on for a decision. Between them, every decision and every
# rule family: both thresholds, past the maximum, cancelled, checked out, tomorrow, a status
# nobody has named (OK4 / PROV4), and a reservation that does not exist.
GUEST_CASES = (("007004343", "14:00"), ("007004343", "15:00"), ("007004343", "16:01"),
               ("007004343", "18:01"), ("007004334", "15:00"), ("007004348", "15:00"),
               ("007004338", "15:00"), ("007004258", "15:00"), ("999999999", "15:00"))
# A shipped property is asked the one request the slice was written for: 3 PM, checked in.
GUEST_SHIPPED_CASES = (("007004343", "15:00"),)


def _guest() -> dict[str, str]:
    """The guest routes' payloads, over the shipped properties and two labelled test ones."""
    import shutil
    import tempfile
    from urllib.parse import urlencode

    from hotelcontrols.spec import available_tenants
    from hotelcontrols.spec.registry import SPEC_DIR
    from hotelcontrols.web import App

    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as scratch:
        spec = pathlib.Path(scratch) / "spec"
        shutil.copytree(SPEC_DIR, spec, ignore=shutil.ignore_patterns("drafts"))
        for tenant_id, like in GUEST_TEST_PROPERTIES.items():
            raw = json.loads((spec / "tenants" / ("%s.json" % like)).read_text("utf-8"))
            raw["tenant_id"] = tenant_id
            raw["name"] = "TEST PROPERTY - %s's vocabulary, D2 §49's policy" % like
            raw["guest_services"] = {"LATE_CHECKOUT": D2_49}
            (spec / "tenants" / ("%s.json" % tenant_id)).write_text(json.dumps(raw), "utf-8")

        cases = {tenant_id: GUEST_SHIPPED_CASES for tenant_id in available_tenants()}
        cases.update({tenant_id: GUEST_CASES for tenant_id in GUEST_TEST_PROPERTIES})

        def get(app, path, name):
            status, content_type, body = app.handle(path)
            if status != 200 or not content_type.startswith("application/json"):
                raise SystemExit("%s answered %d %s:\n%s" % (path, status, content_type,
                                                             body[:400]))
            out[name] = body + "\n"
            return json.loads(body)

        for tenant_id in sorted(cases):
            get(App(spec_dir=spec), "/api/guest/decisions?property=%s" % tenant_id,
                "guest/decisions.empty.%s.json" % tenant_id)

        app = App(spec_dir=spec)        # one store: every property's decisions, kept apart
        for tenant_id in sorted(cases):
            for reservation_id, at in cases[tenant_id]:
                status, _ct, body = app.handle_post("/api/guest/requests", urlencode(
                    {"property": tenant_id, "reservation_id": reservation_id,
                     "requested_time": at}))
                if status != 201:
                    raise SystemExit("a guest request answered %d, not 201:\n%s"
                                     % (status, body[:400]))
                out["guest/requests/%s.%s.%s.json" % (tenant_id, reservation_id,
                                                      at.replace(":", ""))] = body + "\n"
            listing = get(app, "/api/guest/decisions?property=%s" % tenant_id,
                          "guest/decisions.%s.json" % tenant_id)
            for entry in listing["decisions"]:
                get(app, "/api/guest/decisions/%s?property=%s"
                    % (entry["decision_id"], tenant_id),
                    "guest/decisions/%s.json" % entry["decision_id"])

        status, _ct, body = app.handle_post("/api/guest/requests", urlencode(
            {"property": "sandbox", "reservation_id": "007004343"}))
        if status != 400:
            raise SystemExit("a request with no time answered %d, not 400" % status)
        out["guest/requests/refused.json"] = body + "\n"
    return out


def main(argv: list[str]) -> int:
    built = build()
    check = "--check" in argv

    differences = []
    for name, content in sorted(built.items()):
        path = TARGET_DIR / name
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        differences.append(name)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    present = (sorted(p.relative_to(TARGET_DIR).as_posix() for p in TARGET_DIR.rglob("*.json"))
               if TARGET_DIR.is_dir() else [])
    for name in (name for name in present if name not in built):
        differences.append("%s (no longer produced)" % name)
        if not check:
            (TARGET_DIR / name).unlink()

    if check and differences:
        print("STALE - %d file(s) differ from a rebuild:" % len(differences))
        for name in differences:
            print("   x %s" % name)
        print("Rebuild with: python3 -m tools.dump_api_fixtures")
        return 1

    print("%s %d file(s) in %s" % ("checked" if check else "wrote", len(built),
                                   TARGET_DIR.relative_to(ROOT)))
    if differences and not check:
        for name in differences:
            print("   ~ %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
