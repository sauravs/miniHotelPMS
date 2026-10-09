# -*- coding: utf-8 -*-
"""
Criterion V1 (plan-v3 §7): no v2 answer changes, unless a slice declares it.

At the end of v3, the verdicts, counts and coverage inside all 88 run goldens must equal those
at `7f384c4`, the commit v3 was planned on. Every v3 slice PR runs this comparison; making it a
test rather than a script someone remembers to run means it runs on every push as well.

What it compares, and what it deliberately does not. A run payload is allowed to GAIN keys - a
declared contract change, like slice 16's `policy_version` and `policy_digest` - and run ids,
readiness and wording may move for reasons the slice names. What may not move without a
declaration is the ANSWER: which records were judged, what each was judged, why, on what
evidence, and how the run's coverage reads. Those are the three keys below.

A declared change is an entry in DECLARED, naming the PR that made it. Slice 21 is the only one
the plan foresees (`required_reservation_fields` on the sandbox, if `null` changes a reason).
"""
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = "7f384c4"
ANSWER_KEYS = ("verdicts", "counts", "coverage")

# golden path under fixtures/api/ -> the PR that declared its answer changed, and why.
_SLICE_21 = ("slice 21: nominated_rate_codes [] -> null (not decided), plan-v3 §3.2, #49. No "
             "count or outcome moved; 24 reasons now name the undecided parameter instead of the "
             "absent rate code. Pinned exactly by tests/integration/test_typed_parameters.py")
DECLARED: dict[str, str] = {
    "run/required_reservation_fields.sandbox.sandbox2026.json": _SLICE_21,
    "run/required_reservation_fields.demo.demo2026.json": _SLICE_21,
    "runs/c7be275548a09e40.json": _SLICE_21,          # the sandbox run, re-read from the store
    "runs/4270ab5ef6c1068c.json": _SLICE_21,          # the demo run, re-read from the store
}


def _git(*args: str) -> str:
    return subprocess.run(("git",) + args, cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def _baseline_goldens() -> list[str]:
    try:
        listing = _git("ls-tree", "-r", "--name-only", BASELINE, "fixtures/api/")
    except subprocess.CalledProcessError as exc:
        pytest.fail("V1 cannot find the baseline commit %s (%s). In CI the checkout needs "
                    "fetch-depth: 0." % (BASELINE, exc.stderr.strip()))
    return sorted(path.split("fixtures/api/", 1)[1] for path in listing.split()
                  if path.startswith(("fixtures/api/run/", "fixtures/api/runs/")))


BASELINE_RUNS = _baseline_goldens()


def test_the_baseline_has_all_88_run_goldens():
    assert len(BASELINE_RUNS) == 88


@pytest.mark.parametrize("name", BASELINE_RUNS)
def test_no_answer_changed_since_the_v3_baseline(name):
    current_path = ROOT / "fixtures" / "api" / name
    assert current_path.is_file(), "%s existed at %s and is gone" % (name, BASELINE)
    then = json.loads(_git("show", "%s:fixtures/api/%s" % (BASELINE, name)))
    now = json.loads(current_path.read_text(encoding="utf-8"))
    for key in ANSWER_KEYS:
        if name in DECLARED:
            continue
        assert now.get(key) == then.get(key), (
            "%s: %r changed since %s. If it is deliberate, declare it in DECLARED with its PR, "
            "and show the diff to the owner (plan-v3 §7, V1)." % (name, key, BASELINE))
