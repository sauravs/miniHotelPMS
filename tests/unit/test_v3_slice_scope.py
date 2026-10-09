# -*- coding: utf-8 -*-
"""
v3's scope guard: each slice changes what its plan says it may, and nothing else.

Slice 15 proved that "no core logic may break" can be a test rather than a promise
(`test_slice15_engine_untouched.py`). v3 has nine slices, each with its own **may change** and
**must not change** line in `docs/plan-v3.md` §5, so the promise is per slice and so is this
guard. The table below IS those lines, copied - one row per slice, permitted paths only. A path
a slice does not list is a path it may not touch.

WHY AN ALLOW-LIST RATHER THAN A LIST OF PROTECTED PACKAGES
-----------------------------------------------------------
Slice 15's guard protected the engine and let everything else through. That was right for a
slice whose whole risk was the engine. v3's slices are spread across the engine, the tools, the
spec and the evidence, and the dangerous edit is as often in `spec/ir/` (a rule, changed
without touching a line of Python) or a captured fixture (evidence, changed to fit) as in a
package. So the default here is NO: a slice may touch the paths its row lists, plus the tests
that prove it and the documents that describe it, and a change anywhere else fails the branch.

"NEW FILES ONLY"
----------------
Several rows permit a directory only for ADDITIONS - the golden payloads of a slice that adds
routes, or a new capture. An existing golden that changes there is an answer that changed, which
is exactly what the slice promised not to do. So the guard reads the KIND of each change, not
just the path: a modified or deleted file under a new-files-only prefix is a violation.

WHEN IT RUNS
------------
On a `slice/NN-*` branch whose number has a row here (16-24). In CI the branch comes from
`GITHUB_HEAD_REF`, because a pull request is checked out as a detached merge commit. When it
runs and cannot find `origin/main` it FAILS rather than skips: a guard that stands down when
its input is missing is not a guard. It compares against the merge base INCLUDING the working
tree and untracked files, so the mistake is caught at the desk rather than at push.

IF IT FAILS
-----------
Stop and ask the owner (the implementation brief, §0). Do not widen the row to make it pass -
editing the guard to admit an edit the plan forbids is the one change this file exists to make
visible.
"""
import os
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

ANY, NEW = "any", "new"

# Every slice may change the tests that prove it and the documents that describe it. Each PR
# updates the plan-v3 status row, and a slice that adds an interface updates architecture.md.
ALWAYS = ("tests/", "docs/", "CLAUDE.md", "README.md")

# docs/plan-v3.md §5, the **May change** line of each slice, as (path prefix, kind). A prefix
# ending in "/" is a directory; anything else names one file.
MAY_CHANGE = {
    16: (  # Policy versioning (G6b)
        ("hotelcontrols/spec/", ANY),            # the loader reads `version`
        ("hotelcontrols/runner/run.py", ANY),    # two fields on Run
        ("hotelcontrols/store/", ANY),
        ("hotelcontrols/web/", ANY),
        ("tools/validate_spec.py", ANY),
        ("tools/lock_spec.py", ANY),             # the new lock tool
        ("spec/ir.lock.json", ANY),              # new
        ("fixtures/api/", ANY),                  # rebuilt: a DECLARED contract change
        ("ui/", ANY),
    ),
    17: (  # Tenant-scoped store (G5, data half)
        ("hotelcontrols/store/", ANY),
        ("hotelcontrols/web/", ANY),
        ("tools/dump_api_fixtures.py", ANY),
        ("fixtures/api/", ANY),                  # history and drafts payloads, shown in the PR
        ("ui/", ANY),
    ),
    18: (  # Findings queue - advisory action records (G2(a), G8 queue, G10c)
        ("hotelcontrols/actions/", ANY),         # new
        ("hotelcontrols/store/", ANY),
        ("hotelcontrols/web/", ANY),
        ("tools/serve.py", ANY),
        ("tools/dump_api_fixtures.py", ANY),
        ("fixtures/api/", NEW),
        ("ui/", ANY),
    ),
    19: (  # Email, opt-in, behind two locks (G8 email)
        ("hotelcontrols/actions/", ANY),
        ("hotelcontrols/store/", ANY),
        ("hotelcontrols/web/", ANY),
        ("tools/notifiers/", ANY),               # new
        ("tools/serve.py", ANY),
        ("ui/", ANY),
    ),
    20: (  # Operational log (G14, narrowed)
        ("hotelcontrols/ops/", ANY),             # new
        ("hotelcontrols/runner/run.py", ANY),    # emit only
        ("hotelcontrols/web/", ANY),
        ("hotelcontrols/actions/", ANY),
    ),
    21: (  # Typed hotel parameters, with "not decided" (G6a, narrowed)
        ("spec/parameters.json", ANY),           # the parameter schema
        ("spec/tenants/", ANY),
        ("hotelcontrols/spec/", ANY),
        ("tools/validate_spec.py", ANY),
        ("fixtures/api/", ANY),                  # declared, and confirmed by the owner
    ),
    22: (  # Guest services: LATE_CHECKOUT (G1 narrowed, G3a, G2(a))
        ("hotelcontrols/guest/", ANY),           # new, pure
        ("spec/guest/", ANY),                    # the template and its decision table
        ("spec/tenants/", ANY),
        ("hotelcontrols/store/", ANY),
        ("hotelcontrols/actions/", ANY),
        ("hotelcontrols/web/", ANY),
        ("fixtures/api/", NEW),
        ("ui/", ANY),
    ),
    23: (  # Evidence refresh - an owner-approved probe. hotelcontrols/ not at all.
        ("fixtures/minihotel/index.json", ANY),
        ("fixtures/minihotel/", NEW),
        ("fixtures/demopms/index.json", ANY),
        ("fixtures/demopms/", NEW),
        ("fixtures/api/", NEW),
        ("spec/providers/", ANY),                # verified_against dates
    ),
    24: (  # Authentication at the host, credentials per property (G5 auth, G11, #22)
        ("hotelcontrols/web/", ANY),
        ("hotelcontrols/providers/transport/http.py", ANY),   # the credential key only
        ("tools/probe.py", ANY),
        ("ui/", ANY),
    ),
}

# A draft filed from the compose window during a local demo lands here untracked. It is a
# reader's working state, not a change to the spec, and it is never committed by a slice.
# `spec/drafts/ir/` until slice 17, and `spec/drafts/<property>/ir/` since drafts became per
# property. Only an UNTRACKED draft file is exempt - a committed one is still a change.
LOCAL_STATE = re.compile(r"^spec/drafts/(?:[^/]+/)?ir/[^/]+\.json$")

_SLICE_BRANCH = re.compile(r"^slice/(\d+)-")


def _git(*args: str) -> str:
    return subprocess.run(("git",) + args, cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def _branch() -> str:
    return os.environ.get("GITHUB_HEAD_REF") or _git("rev-parse", "--abbrev-ref", "HEAD").strip()


def slice_of(branch: str) -> int | None:
    """The v3 slice a branch builds, or None if it is not a v3 slice branch."""
    match = _SLICE_BRANCH.match(branch or "")
    if match is None:
        return None
    number = int(match.group(1))
    return number if number in MAY_CHANGE else None


def violations(slice_number: int, changes, untracked=()) -> list[str]:
    """Every change this slice may not make. Pure, so the rule itself can be tested.

    `changes` is `(status, path)` pairs as `git diff --name-status --no-renames` gives them:
    A added, M modified, D deleted (and T for a type change). Untracked files are additions.
    """
    rows = MAY_CHANGE[slice_number]
    found = []
    for status, path in sorted(set(changes) | {("A", p) for p in untracked}):
        if path.startswith(ALWAYS):
            continue
        if status == "A" and path in untracked and LOCAL_STATE.match(path):
            continue
        if not any(_permits(prefix, kind, status, path) for prefix, kind in rows):
            found.append("%s %s" % (status, path))
    return found


def _permits(prefix: str, kind: str, status: str, path: str) -> bool:
    matches = path.startswith(prefix) if prefix.endswith("/") else path == prefix
    return matches and (kind == ANY or status == "A")


def _changed_since_main() -> tuple[list[tuple[str, str]], list[str]]:
    try:
        base = _git("merge-base", "origin/main", "HEAD").strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.fail("v3 scope guard cannot find origin/main to compare against (%s). In CI the "
                    "checkout needs fetch-depth: 0." % exc)
    # Against the merge base and the WORKING TREE, not HEAD: an uncommitted edit to the kernel
    # is the same mistake as a committed one, caught earlier. `--no-renames`, so a file moved
    # out of a protected directory is reported as the deletion it is.
    changes = []
    for line in _git("diff", "--name-status", "--no-renames", base).splitlines():
        status, path = line.split("\t", 1)
        changes.append((status[0], path))
    untracked = _git("ls-files", "--others", "--exclude-standard").split()
    return changes, untracked


@pytest.mark.skipif(slice_of(_branch()) is None,
                    reason="the v3 scope guard belongs to slice/16-* .. slice/24-* branches only")
def test_this_slice_changes_only_what_its_plan_permits():
    """plan-v3 §1: "a scope guard per slice", proven per PR rather than promised."""
    number = slice_of(_branch())
    changes, untracked = _changed_since_main()
    broken = violations(number, changes, untracked)
    assert not broken, (
        "SLICE %d CHANGED A PATH ITS PLAN DOES NOT PERMIT - stop and ask the owner "
        "(docs/plan-v3.md §5, slice %d, 'May change'):\n  %s"
        % (number, number, "\n  ".join(broken)))


# ---------------------------------------------------------------------------------------
# The rule itself, tested on any branch, so the guard cannot rot into a test that always passes.
class TestTheGuardRule:

    def test_the_table_has_a_row_for_every_v3_slice_and_no_other(self):
        assert sorted(MAY_CHANGE) == list(range(16, 25))

    @pytest.mark.parametrize("branch, number", [
        ("slice/16-policy-versioning", 16), ("slice/24-host-auth", 24),
        ("slice/15-react-ui", None), ("slice/25-something", None),
        ("fix/48-card-presence-not-established", None), ("main", None), ("", None),
    ])
    def test_only_a_v3_slice_branch_is_guarded(self, branch, number):
        assert slice_of(branch) == number

    @pytest.mark.parametrize("number", sorted(MAY_CHANGE))
    @pytest.mark.parametrize("path", [
        "hotelcontrols/kernel/value.py", "hotelcontrols/evaluator/record.py",
        "hotelcontrols/evidence/gather.py", "hotelcontrols/compiler/grammar.py",
        "hotelcontrols/providers/minihotel/adapter.py",
        "spec/ir/checkout_money_owed.json", "spec/canonical_fields.json",
        "fixtures/minihotel/9_departures_2026-07.xml", "fixtures/demopms/bookings_2026-07.json",
        "pyproject.toml", "requirements-dev.txt", ".github/workflows/ci.yml",
    ])
    def test_what_no_v3_slice_may_change_is_refused_on_every_slice(self, number, path):
        """The kernel, the evaluator, the evidence layer, the compiler, the adapters, every
        rule, the vocabulary and every existing capture: no v3 slice lists any of them. Nor
        the dependency pins or CI - a slice that needs one of those is a slice to ask about."""
        assert violations(number, [("M", path)]) == ["M %s" % path]

    @pytest.mark.parametrize("number", sorted(MAY_CHANGE))
    def test_tests_and_documents_are_always_permitted(self, number):
        assert violations(number, [("M", "tests/unit/test_x.py"), ("A", "docs/new.md"),
                                   ("M", "CLAUDE.md"), ("M", "README.md")]) == []

    def test_a_new_file_inside_a_forbidden_package_is_caught(self):
        assert violations(16, [], untracked=["hotelcontrols/kernel/new.py"]) == [
            "A hotelcontrols/kernel/new.py"]

    def test_slice_16_may_add_the_lock_and_change_the_loader_but_not_a_rule(self):
        assert violations(16, [("A", "spec/ir.lock.json"), ("M", "hotelcontrols/spec/ir.py"),
                               ("M", "hotelcontrols/runner/run.py"),
                               ("A", "tools/lock_spec.py"),
                               ("M", "fixtures/api/run/x.sandbox.sandbox2026.json")]) == []
        assert violations(16, [("M", "spec/ir/checkout_money_owed.json"),
                               ("M", "hotelcontrols/runner/coverage.py")]) == [
            "M hotelcontrols/runner/coverage.py", "M spec/ir/checkout_money_owed.json"]

    def test_slice_17_may_not_touch_the_runner_or_the_spec(self):
        assert violations(17, [("M", "hotelcontrols/runner/run.py"),
                               ("M", "hotelcontrols/spec/ir.py")]) == [
            "M hotelcontrols/runner/run.py", "M hotelcontrols/spec/ir.py"]

    @pytest.mark.parametrize("number", [18, 22, 23])
    def test_new_files_only_means_an_existing_golden_may_not_change(self, number):
        """An existing golden that changes on a slice that promised new files only is an
        answer that changed. Adding one is the slice's job; editing or deleting one is not."""
        golden = "fixtures/api/run/checkout_money_owed.sandbox.sandbox2026.json"
        assert violations(number, [("A", "fixtures/api/actions/x.json")]) == []
        assert violations(number, [("M", golden), ("D", golden)]) == [
            "D %s" % golden, "M %s" % golden]

    def test_slice_18_does_not_let_a_run_create_actions(self):
        """plan-v3 §5: the layer above the run creates action records; runner/ is a must-not."""
        assert violations(18, [("M", "hotelcontrols/runner/run.py")]) == [
            "M hotelcontrols/runner/run.py"]

    def test_slice_20_may_emit_from_the_runner_but_never_log_from_the_evaluator(self):
        assert violations(20, [("M", "hotelcontrols/runner/run.py"),
                               ("A", "hotelcontrols/ops/log.py")]) == []
        assert violations(20, [("M", "hotelcontrols/evaluator/record.py")]) == [
            "M hotelcontrols/evaluator/record.py"]

    def test_slice_21_may_change_tenant_settings_but_not_a_rule(self):
        assert violations(21, [("M", "spec/tenants/sandbox.json"),
                               ("A", "spec/parameters.json")]) == []
        assert violations(21, [("M", "spec/ir/required_reservation_fields.json")]) == [
            "M spec/ir/required_reservation_fields.json"]

    def test_slice_23_adds_a_capture_and_never_edits_one_nor_the_engine(self):
        assert violations(23, [("A", "fixtures/minihotel/11_getRooms_2026.xml"),
                               ("M", "fixtures/minihotel/index.json"),
                               ("A", "fixtures/demopms/rooms_2026.json"),
                               ("M", "fixtures/demopms/index.json"),
                               ("M", "spec/providers/minihotel.json")]) == []
        assert violations(23, [("M", "fixtures/minihotel/2_getRooms_all.xml"),
                               ("M", "hotelcontrols/web/app.py")]) == [
            "M fixtures/minihotel/2_getRooms_all.xml", "M hotelcontrols/web/app.py"]

    def test_slice_24_may_change_the_credential_key_but_not_the_store(self):
        assert violations(24, [("M", "hotelcontrols/providers/transport/http.py"),
                               ("A", "hotelcontrols/web/auth.py")]) == []
        assert violations(24, [("M", "hotelcontrols/store/sqlite.py"),
                               ("M", "hotelcontrols/providers/transport/retry.py")]) == [
            "M hotelcontrols/providers/transport/retry.py", "M hotelcontrols/store/sqlite.py"]

    @pytest.mark.parametrize("draft", ["spec/drafts/ir/my_rule.json",
                                       "spec/drafts/sandbox/ir/my_rule.json"])
    def test_a_draft_filed_during_a_demo_is_local_state_but_a_committed_one_is_not(self, draft):
        """Both layouts: before slice 17 and since (drafts per property)."""
        assert violations(17, [], untracked=[draft]) == []
        assert violations(17, [("A", draft)]) == ["A %s" % draft]

    def test_only_a_draft_file_is_local_state_not_anything_under_spec_drafts(self):
        stray = ["spec/drafts/notes.py", "spec/drafts/sandbox/ir/deeper/x.json",
                 "spec/drafts/sandbox/canonical_fields.json"]
        assert violations(17, [], untracked=stray) == ["A %s" % p for p in sorted(stray)]
