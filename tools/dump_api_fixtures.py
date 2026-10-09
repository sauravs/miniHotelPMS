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
    store (trap 4 in the brief). Reading a file does neither.

WHAT IS WRITTEN - the path mirrors the route
--------------------------------------------
    controls.json  properties.json  drafts.json          the index's three requests
    outcomes.json                                         the four answers' words, one source
    readiness/<control>.json                              one per control
    run/<control>.<property>.<evidence>.json              the FULL matrix, live
    runs/<run_id>.json                                    every one of those, re-read from store
    history/<control>.json                                after the whole matrix has run
    compose/*.json                                        off, wired, and three kinds of turn

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
                run_ids.append(payload["run_id"])

    for run_id in run_ids:
        take("/api/runs/%s" % run_id, "runs/%s.json" % run_id)
    for control_id in controls:
        take("/api/history/%s" % control_id, "history/%s.json" % control_id)

    built.update(_compose())
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
