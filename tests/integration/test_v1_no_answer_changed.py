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
After v3, issue #71's fix declared 48 more (the owner's choice A+B, 2026-10-13): runs that were
answered from part of a population are now refused, saying which question the capture holds.
Issue #87's fix moved ooo_room_protection's eight again, by two evidence lines on every verdict.
B's 44 new goldens - the covering capture, offered beside sandbox2026 - have no baseline to move
from, so they need no declaration.
"""
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = "7f384c4"
ANSWER_KEYS = ("verdicts", "counts", "coverage")

# golden path under fixtures/api/ -> the PR that declared its answer changed, and why.
_SLICE_21 = ("PR #65, slice 21: nominated_rate_codes [] -> null (not decided), plan-v3 §3.2, #49. No "
             "count or outcome moved; 24 reasons now name the undecided parameter instead of the "
             "absent rate code. Pinned exactly by tests/integration/test_typed_parameters.py")
_FIX_71 = ("PR #95 for issue #71 (follow-up 1, step B), owner's choice A+B: replay answers only "
           "the question a response was recorded for. An arrival or create window asked of a "
           "departure-window capture is REFUSED instead of answered from part of the population "
           "(7 controls on 2026, every reservation control on 2024); the occupancy reference, "
           "which asks no window, no longer takes one 2024 week as all occupancy "
           "(ooo_room_protection: still EXCLUDED 28, the reason now names it). Criterion 1: "
           "sandbox2026 5 -> 2, the covering capture sandbox2026cover 5 of 11 from the right "
           "evidence. Pinned by "
           "tests/integration/test_replay_answers_only_its_question.py")
_FIX_87 = ("Then PR for issue #87 (the guard): ooo_room_protection version 3 reads occupancy.from "
           "and occupancy.to instead of placing occupancy.reservation_id in a window of dates, so "
           "every verdict carries those two evidence lines (unknown: the occupancy reference is "
           "refused on every capture since #71). No outcome, count, reason or coverage moved: "
           "still EXCLUDED 28. Pinned by tests/integration/test_closed_room_never_passes.py")
_FIX_71_THEN_87 = _FIX_71 + " " + _FIX_87
DECLARED: dict[str, str] = {
    "run/checkout_money_owed.demo.demo2024.json": _FIX_71,
    "run/checkout_money_owed.sandbox.sandbox2024.json": _FIX_71,
    "run/checkout_unrefunded_credit.demo.demo2024.json": _FIX_71,
    "run/checkout_unrefunded_credit.sandbox.sandbox2024.json": _FIX_71,
    "run/duplicate_channel_reservation.demo.demo2024.json": _FIX_71,
    "run/duplicate_channel_reservation.demo.demo2026.json": _FIX_71,
    "run/duplicate_channel_reservation.sandbox.sandbox2024.json": _FIX_71,
    "run/duplicate_channel_reservation.sandbox.sandbox2026.json": _FIX_71,
    "run/inactive_room_future_stay.demo.demo2026.json": _FIX_71,
    "run/inactive_room_future_stay.sandbox.sandbox2026.json": _FIX_71,
    "run/ooo_room_protection.demo.demo2024.json": _FIX_71_THEN_87,
    "run/ooo_room_protection.demo.demo2026.json": _FIX_71_THEN_87,
    "run/ooo_room_protection.sandbox.sandbox2024.json": _FIX_71_THEN_87,
    "run/ooo_room_protection.sandbox.sandbox2026.json": _FIX_71_THEN_87,
    "run/rate_room_category_consistency.demo.demo2026.json": _FIX_71,
    "run/rate_room_category_consistency.sandbox.sandbox2026.json": _FIX_71,
    "run/required_reservation_fields.demo.demo2026.json": _SLICE_21 + "; then " + _FIX_71,
    "run/required_reservation_fields.sandbox.sandbox2026.json": _SLICE_21 + "; then " + _FIX_71,
    "run/room_assignment_active_room.demo.demo2026.json": _FIX_71,
    "run/room_assignment_active_room.sandbox.sandbox2026.json": _FIX_71,
    "run/room_assignment_type_validity.demo.demo2026.json": _FIX_71,
    "run/room_assignment_type_validity.sandbox.sandbox2026.json": _FIX_71,
    "run/room_capacity_compliance.demo.demo2026.json": _FIX_71,
    "run/room_capacity_compliance.sandbox.sandbox2026.json": _FIX_71,
    "runs/0e6b91d1d03e9c8e.json": _FIX_71,  # room_capacity_compliance, sandbox2026
    "runs/1c9c18c57cdbc12e.json": _FIX_71,  # rate_room_category_consistency, demo2026
    "runs/2b562825a8d7539e.json": _FIX_71,  # rate_room_category_consistency, sandbox2026
    "runs/2d4c1326a1ec64bf.json": _FIX_71,  # duplicate_channel_reservation, sandbox2024
    "runs/4270ab5ef6c1068c.json": _SLICE_21 + "; then " + _FIX_71,  # required_reservation_fields, demo2026
    "runs/4b190a898ad36d4c.json": _FIX_71,  # checkout_money_owed, sandbox2024
    "runs/4f69986967c9515c.json": _FIX_71,  # room_assignment_type_validity, sandbox2026
    "runs/52baef0e86c2c46e.json": _FIX_71,  # room_assignment_active_room, demo2026
    "runs/57b270d6834371d7.json": _FIX_71,  # checkout_money_owed, demo2024
    "runs/5dbda5e62069da3a.json": _FIX_71_THEN_87,  # ooo_room_protection, demo2024
    "runs/63c1bc772fded4d3.json": _FIX_71,  # room_assignment_type_validity, demo2026
    "runs/66c0bcbc30f646f4.json": _FIX_71,  # room_assignment_active_room, sandbox2026
    "runs/71d70944aef8b185.json": _FIX_71,  # checkout_unrefunded_credit, demo2024
    "runs/7682f58b49194b12.json": _FIX_71,  # duplicate_channel_reservation, demo2026
    "runs/838b32f05820b6c0.json": _FIX_71_THEN_87,  # ooo_room_protection, demo2026
    "runs/a3302f0bfe75c3d3.json": _FIX_71,  # duplicate_channel_reservation, sandbox2026
    "runs/abf65d7e8e00e2ce.json": _FIX_71,  # inactive_room_future_stay, demo2026
    "runs/b92123bf3b9c654b.json": _FIX_71_THEN_87,  # ooo_room_protection, sandbox2024
    "runs/be64f79a551b5251.json": _FIX_71,  # checkout_unrefunded_credit, sandbox2024
    "runs/c6184f1a690effe3.json": _FIX_71,  # duplicate_channel_reservation, demo2024
    "runs/c7be275548a09e40.json": _SLICE_21 + "; then " + _FIX_71,  # required_reservation_fields, sandbox2026
    "runs/daa26af9ac128dd9.json": _FIX_71,  # inactive_room_future_stay, sandbox2026
    "runs/f150b88be31a62c7.json": _FIX_71_THEN_87,  # ooo_room_protection, sandbox2026
    "runs/f42793aadc7fd90a.json": _FIX_71,  # room_capacity_compliance, demo2026
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
