# -*- coding: utf-8 -*-
"""
Slice 16 (G6b): which version of a rule judged a record, and a rule cannot be edited quietly.

Every IR has said `"version": 2` since v2, and nothing read it (plan-v3 §2). A version number
that a person maintains by hand is a number that can lie: edit a predicate, forget the bump,
and every stored verdict under the old rule and the new one claims the same "v2". So the
version is checked against a DIGEST of the rule's verdict-bearing content, recorded in a lock
file a tool generates (`spec/ir.lock.json`), and `tools.validate_spec` fails when the content
moved and the version did not. "Editing a policy makes v3" becomes mechanical, not remembered.

What counts as verdict-bearing is the plan's list: the population, references, scope,
exceptions, assertion, required evidence and unknown conditions - and the sentences shown beside
a verdict. Prose that explains a predicate (`note`), the schedule, freshness, the action block
and the caveats do not decide any verdict, so editing them needs no new version.

Every test here protects criterion V3 (plan-v3 §7) unless it says otherwise.
"""
import copy
import json
import pathlib
import shutil

import pytest

from hotelcontrols.spec import SpecError, available, load
from hotelcontrols.spec import lock as spec_lock
from tools import lock_spec, validate_spec

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"
CONTROL = "checkout_money_owed"


# --------------------------------------------------------------------------- helpers
def _copy_spec(tmp_path) -> pathlib.Path:
    """A whole spec root in a temporary directory, so a test can edit a rule safely."""
    target = tmp_path / "spec"
    shutil.copytree(SPEC, target, symlinks=True, ignore=shutil.ignore_patterns("drafts"))
    return target


def _edit(spec: pathlib.Path, control_id: str, change) -> None:
    path = spec / "ir" / ("%s.json" % control_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    change(raw)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def _raise_the_threshold(raw) -> None:
    """ONE predicate changed - money owed now tolerates 10 - with the sentence beside it kept
    true, so the only thing wrong with the rule afterwards is its version."""
    raw["assertion"]["predicates"][0]["value"] = 10
    raw["restricted_language"] = raw["restricted_language"].replace("at most 0", "at most 10")


def _bump(raw) -> None:
    raw["version"] += 1


def _validate(spec: pathlib.Path, capsys) -> tuple[int, str]:
    code = validate_spec.main(["--spec", str(spec)])
    return code, capsys.readouterr().out


# --------------------------------------------------------------------------- the loader
class TestTheLoaderReadsTheVersion:

    def test_every_shipped_control_says_which_version_it_is(self):
        """plan-v3 §2: every IR says `"version": 2` and no loader read it until now."""
        for control_id in available():
            assert load(control_id).version == 2, control_id

    def test_the_digest_is_a_named_hash_of_the_rule(self):
        digest = load(CONTROL).digest
        assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64

    def test_the_same_rule_has_the_same_digest_however_its_file_is_laid_out(self):
        """Key order and whitespace are not the rule. A digest that moved when somebody
        re-indented a file would demand a version bump for nothing - and a check that cries
        wolf is a check people learn to override."""
        raw = load(CONTROL).raw
        shuffled = dict(reversed(list(copy.deepcopy(raw).items())))
        assert spec_lock.policy_digest(shuffled) == spec_lock.policy_digest(raw)


class TestWhatIsVerdictBearing:

    @pytest.mark.parametrize("key", spec_lock.VERDICT_BEARING)
    def test_changing_any_verdict_bearing_part_changes_the_digest(self, key):
        raw = copy.deepcopy(load(CONTROL).raw)
        before = spec_lock.policy_digest(raw)
        raw[key] = {"changed": key} if not isinstance(raw.get(key), str) else raw[key] + " (edited)"
        assert spec_lock.policy_digest(raw) != before, key

    def test_the_plan_s_list_is_what_is_hashed(self):
        """plan-v3 §5, slice 16: population, references, scope, exceptions, assertion,
        required evidence, unknown conditions, and the sentences shown beside a verdict."""
        assert set(spec_lock.VERDICT_BEARING) == {
            "entity", "population", "references", "scope", "exceptions", "assertion",
            "required_evidence", "unknown_conditions",
            "name", "natural_language", "restricted_language"}

    @pytest.mark.parametrize("change", [
        lambda raw: raw["caveats"].append("one more caveat"),
        lambda raw: raw["execution"].update(rationale="reworded"),
        lambda raw: raw["freshness_requirement"].update(rationale="reworded"),
        lambda raw: raw["action"].update(severity="low"),
        lambda raw: raw["assertion"]["predicates"][0].update(note="a reworded explanation"),
        lambda raw: raw["required_evidence"][0].update(note="why this field is needed"),
        lambda raw: raw.update(source_control="6b"),
    ], ids=["caveats", "execution", "freshness", "action", "assertion-note", "evidence-note",
            "source_control"])
    def test_prose_and_operations_that_decide_no_verdict_need_no_new_version(self, change):
        raw = copy.deepcopy(load(CONTROL).raw)
        before = spec_lock.policy_digest(raw)
        change(raw)
        assert spec_lock.policy_digest(raw) == before


# --------------------------------------------------------------------------- the lock
class TestTheShippedLock:

    def test_the_shipped_lock_is_current(self):
        """If this fails after a deliberate rule change: bump the control's `version`, then
        `python3 -m tools.lock_spec`. Never the other way round - the tool refuses."""
        assert lock_spec.main(["--check"]) == 0

    def test_it_holds_every_shipped_control_at_its_version_and_digest(self):
        locked = spec_lock.read_lock(SPEC)
        assert sorted(locked) == list(available())
        for control_id in available():
            ir = load(control_id)
            assert locked[control_id] == (ir.version, ir.digest), control_id

    def test_the_shipped_spec_has_no_lock_problem(self):
        assert spec_lock.lock_problems(SPEC) == []


class TestEditingARuleWithoutABumpIsRefused:
    """plan-v3 §5, slice 16, exit test 2."""

    def test_an_untouched_copy_validates(self, tmp_path, capsys):
        code, out = _validate(_copy_spec(tmp_path), capsys)
        assert code == 0, out

    def test_one_predicate_changed_without_a_bump_fails_validate_spec_naming_the_control(
            self, tmp_path, capsys):
        spec = _copy_spec(tmp_path)
        _edit(spec, CONTROL, _raise_the_threshold)
        code, out = _validate(spec, capsys)
        assert code == 1, out
        assert CONTROL in out and "without a version bump" in out, out

    def test_bumping_it_passes(self, tmp_path, capsys):
        spec = _copy_spec(tmp_path)
        _edit(spec, CONTROL, lambda raw: (_raise_the_threshold(raw), _bump(raw)))
        code, out = _validate(spec, capsys)
        assert code == 0, out
        assert "not yet locked" in out and CONTROL in out, (
            "a bumped rule passes, but it must still say the lock has to be regenerated")

    def test_the_lock_tool_records_the_bump_and_then_nothing_is_pending(self, tmp_path, capsys):
        spec = _copy_spec(tmp_path)
        _edit(spec, CONTROL, lambda raw: (_raise_the_threshold(raw), _bump(raw)))
        assert lock_spec.main(["--check", "--spec", str(spec)]) == 1
        assert lock_spec.main(["--spec", str(spec)]) == 0
        assert lock_spec.main(["--check", "--spec", str(spec)]) == 0
        assert spec_lock.read_lock(spec)[CONTROL][0] == 3
        capsys.readouterr()
        code, out = _validate(spec, capsys)
        assert code == 0 and "not yet locked" not in out, out

    def test_the_lock_tool_refuses_to_launder_an_unbumped_edit(self, tmp_path, capsys):
        """The tool is not a way round the check. Regenerating the lock over an edit that kept
        its version would record the new rule under the old number - exactly the lie."""
        spec = _copy_spec(tmp_path)
        before = (spec / spec_lock.LOCK_FILE).read_text(encoding="utf-8")
        _edit(spec, CONTROL, _raise_the_threshold)
        assert lock_spec.main(["--spec", str(spec)]) == 1
        assert CONTROL in capsys.readouterr().out
        assert (spec / spec_lock.LOCK_FILE).read_text(encoding="utf-8") == before
        with pytest.raises(SpecError, match=CONTROL):
            spec_lock.build_lock(spec)

    def test_a_version_that_goes_backwards_is_refused(self, tmp_path, capsys):
        spec = _copy_spec(tmp_path)
        _edit(spec, CONTROL, lambda raw: raw.update(version=1))
        code, out = _validate(spec, capsys)
        assert code == 1 and CONTROL in out and "backwards" in out, out

    def test_rewording_a_note_needs_no_bump(self, tmp_path, capsys):
        spec = _copy_spec(tmp_path)
        _edit(spec, CONTROL, lambda raw: raw["assertion"]["predicates"][0].update(note="Reworded."))
        code, out = _validate(spec, capsys)
        assert code == 0, out
        assert lock_spec.main(["--check", "--spec", str(spec)]) == 0

    def test_a_new_control_validates_but_is_reported_as_not_yet_locked(self, tmp_path, capsys):
        """Criterion 6: a twelfth control is a spec change. It is born at its first version and
        must be locked before it merges - the suite's lock check is what enforces that."""
        spec = _copy_spec(tmp_path)
        raw = json.loads((spec / "ir" / ("%s.json" % CONTROL)).read_text(encoding="utf-8"))
        raw["control_id"] = "a_twelfth_control"
        raw["version"] = 1
        (spec / "ir" / "a_twelfth_control.json").write_text(json.dumps(raw), encoding="utf-8")
        code, out = _validate(spec, capsys)
        assert code == 0 and "a_twelfth_control" in out and "not yet locked" in out, out
        assert lock_spec.main(["--check", "--spec", str(spec)]) == 1

    def test_a_spec_root_with_no_lock_at_all_has_every_control_unlocked(self, tmp_path):
        spec = _copy_spec(tmp_path)
        (spec / spec_lock.LOCK_FILE).unlink()
        assert spec_lock.read_lock(spec) == {}
        assert spec_lock.lock_problems(spec) == []
        assert spec_lock.unlocked(spec) == list(available(spec))
