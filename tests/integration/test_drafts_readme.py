# -*- coding: utf-8 -*-
"""
Issue #54: the documented way to promote a draft must actually work.

`spec/drafts/README.md` is the procedure a person follows to make a composed rule a reviewed one.
Since slice 16 a reviewed rule must be recorded in the spec lock, and a procedure that skipped
that step ended in a red suite. So the procedure is executed here, as written: every
`python3 -m tools.*` line of its code block, in order, against a temporary spec root holding a
draft, and the result must be a spec root whose lock is current and which validates.
"""
import json
import pathlib
import re
import shutil

from tools import lock_spec, validate_spec

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "spec" / "drafts" / "README.md"
TOOLS = {"lock_spec": lock_spec.main, "validate_spec": validate_spec.main}


def _documented_tool_steps() -> list[str]:
    block = re.search(r"```bash\n(.*?)```", README.read_text(encoding="utf-8"), re.S).group(1)
    return re.findall(r"^python3 -m tools\.(\w+)", block, re.M)


def test_the_documented_promotion_leaves_a_locked_spec_that_validates(tmp_path, capsys):
    spec = tmp_path / "spec"
    shutil.copytree(ROOT / "spec", spec, symlinks=True, ignore=shutil.ignore_patterns("drafts"))
    draft = json.loads((spec / "ir" / "checkout_money_owed.json").read_text(encoding="utf-8"))
    draft.update(control_id="promoted_draft", version=1)
    # the README's `git mv`: the draft arrives in spec/ir/
    (spec / "ir" / "promoted_draft.json").write_text(json.dumps(draft), encoding="utf-8")

    steps = _documented_tool_steps()
    assert steps, "the README documents no tool step at all"
    for step in steps:
        assert step in TOOLS, "the README names a tool this test does not know: %s" % step
        assert TOOLS[step](["--spec", str(spec)]) == 0, (step, capsys.readouterr().out)
    assert lock_spec.main(["--check", "--spec", str(spec)]) == 0, (
        "following the README leaves the spec lock stale - the suite would fail (#54)")
