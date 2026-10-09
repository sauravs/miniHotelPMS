# -*- coding: utf-8 -*-
"""
THE SPEC LOCK - which version of each rule is which, so a version number cannot lie.

    policy_digest(raw)    -> "sha256:..."     the rule's verdict-bearing content, hashed
    read_lock(spec_dir)   -> {control_id: (version, digest)}
    lock_problems(spec_dir) -> [Problem]      a rule edited without a bump, or one that went back
    unlocked(spec_dir)    -> [control_id]     new or bumped, and not yet recorded
    build_lock(spec_dir)  -> dict             the lock as it should now read; refuses a launder

Every IR has carried `"version": 2` since v2, and nothing read it. A version that a person keeps
by hand is a version that can lie: edit a predicate, forget the bump, and every verdict stored
under the old rule and under the new one claims the same "v2". An auditor asking "under which
rule did this FAIL?" would get an answer, confidently, that is wrong. So the version is paired
with a DIGEST of what the rule actually says, and `spec/ir.lock.json` records the pair for every
reviewed control. `tools/validate_spec.py` fails when the content moved and the version did not;
`tools/lock_spec.py` regenerates the lock and refuses to record an edit under an unchanged
version. Editing a policy makes v3 because a check says so, not because somebody remembered.

WHAT IS HASHED is plan-v3 §5's list: what decides a verdict, and the sentences a reader sees
beside one. Prose that explains a predicate (`note`), the schedule, freshness, the action block
and the caveats decide no verdict, so rewording them needs no new version - a check that demands
a bump for a typo is a check people learn to override.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from .errors import Problem, SpecError
from .registry import SPEC_DIR

LOCK_FILE = "ir.lock.json"

# plan-v3 §5, slice 16: population, references, scope, exceptions, assertion, required evidence,
# unknown conditions - and the sentences shown beside a verdict. `entity` is here because it
# decides which records are judged at all; a rule moved from reservations to stays is not the
# same rule.
VERDICT_BEARING = ("entity", "population", "references", "scope", "exceptions", "assertion",
                   "required_evidence", "unknown_conditions",
                   "name", "natural_language", "restricted_language")


def policy_digest(raw: dict[str, Any]) -> str:
    """The rule's verdict-bearing content, as a self-describing SHA-256.

    Canonical JSON - sorted keys, fixed separators - so key order and indentation are not the
    rule. A digest that moved when somebody re-indented a file would demand a version for
    nothing. `note` keys are dropped at every depth: they explain a predicate, they do not
    decide one, which is also why `validate_spec` leaves them out when it recompiles a sentence.
    """
    content = {key: _without_notes(raw[key]) for key in VERDICT_BEARING if key in raw}
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without_notes(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_notes(v) for k, v in value.items() if k != "note"}
    if isinstance(value, list):
        return [_without_notes(item) for item in value]
    return value


# --------------------------------------------------------------------------- reading
def read_lock(spec_dir: pathlib.Path | str = SPEC_DIR) -> dict[str, tuple[int, str]]:
    """The recorded `(version, digest)` per control. A spec root with no lock has none locked.

    A drafts directory, or a temporary spec root a test builds, has no lock - and that means
    "nothing has been recorded yet", not "something is wrong". The repository's own lock is
    required by the suite (`test_the_shipped_lock_is_current`), not by this function.
    """
    path = pathlib.Path(spec_dir) / LOCK_FILE
    if not path.is_file():
        return {}
    controls = json.loads(path.read_text(encoding="utf-8")).get("controls", {})
    return {control_id: (int(entry["version"]), str(entry["digest"]))
            for control_id, entry in controls.items()}


def _current(spec_dir: pathlib.Path | str) -> dict[str, tuple[int, str]]:
    """Every reviewed control's `(version, digest)` as the files on disk say it now."""
    from .ir import available, load        # here, not at module level: ir imports this module
    return {control_id: (ir.version, ir.digest)
            for control_id, ir in ((c, load(c, spec_dir)) for c in available(spec_dir))}


# --------------------------------------------------------------------------- judging
def lock_problems(spec_dir: pathlib.Path | str = SPEC_DIR) -> list[Problem]:
    """Every control whose version no longer tells the truth about its content.

    Two ways to lie. The content moved and the version did not: every verdict under the edited
    rule would claim the reviewed one's number. Or the version went BACKWARDS: a number that was
    once v3 and is now v2 makes "judged under v2" ambiguous between two rules.

    A version AHEAD of the lock is not a problem here - that is a bump waiting to be recorded,
    reported by `unlocked` and enforced by the suite's lock check before it can merge.
    """
    locked = read_lock(spec_dir)
    problems: list[Problem] = []
    for control_id, (version, digest) in _current(spec_dir).items():
        if control_id not in locked:
            continue
        was_version, was_digest = locked[control_id]
        where = "control %s" % control_id
        if version < was_version:
            problems.append(Problem(
                where, "its version went backwards, from %d to %d - two different rules would "
                       "both answer to v%d" % (was_version, version, version)))
        elif version == was_version and digest != was_digest:
            problems.append(Problem(
                where, "its verdict-bearing content changed without a version bump - it is "
                       "still v%d, so every verdict under the edited rule would claim the "
                       "reviewed v%d's name. Bump `version`, then run `python3 -m "
                       "tools.lock_spec`" % (version, version)))
    return problems


def unlocked(spec_dir: pathlib.Path | str = SPEC_DIR) -> list[str]:
    """Controls that are new, or bumped, and not yet recorded in the lock - in id order."""
    locked = read_lock(spec_dir)
    return [control_id for control_id, (version, _digest) in _current(spec_dir).items()
            if control_id not in locked or version > locked[control_id][0]]


def build_lock(spec_dir: pathlib.Path | str = SPEC_DIR) -> dict[str, Any]:
    """The lock as it should now read. Refuses rather than record a lie.

    Regenerating the lock over an edit that kept its version would write the new rule down
    under the old number - the exact thing the lock exists to stop - so the tool that writes
    it is held to the same rule as the check that reads it.
    """
    problems = lock_problems(spec_dir)
    if problems:
        raise SpecError("refusing to lock: %s" % "; ".join(str(p) for p in problems))
    return {
        "about": ("Generated by `python3 -m tools.lock_spec` - never edited by hand. Each "
                  "reviewed control's version and the SHA-256 of its verdict-bearing content "
                  "(hotelcontrols/spec/lock.py). `tools.validate_spec` fails when a rule's "
                  "content changes and its version does not."),
        "controls": {control_id: {"version": version, "digest": digest}
                     for control_id, (version, digest) in sorted(_current(spec_dir).items())},
    }


def render_lock(lock: dict[str, Any]) -> str:
    """The lock file's exact text, so writing it and checking it cannot disagree."""
    return json.dumps(lock, indent=2, ensure_ascii=False) + "\n"
