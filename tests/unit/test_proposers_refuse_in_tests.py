# -*- coding: utf-8 -*-
"""
NO TEST IN THIS REPOSITORY REACHES A MODEL, AND THIS IS THE FILE THAT PROVES IT.

Criterion 11 says the engine runs offline and no test can reach the network. Slice 13 adds the
first thing in this repository that wants to talk to a model at all, so it inherits the
transport's proof pattern exactly (`providers/transport/http.py`, slice 11):

    lock 1   an environment variable, HOTELCONTROLS_COMPOSE
    lock 2   a refusal to arm while a test runner is loaded in the process

One lock would not be a lock. An environment variable is one `monkeypatch.setenv` away, so the
test that matters below SETS IT AND IS REFUSED ANYWAY - which is as close to proving a negative
as this gets.

THE LOCAL BACKEND IS HELD TO THIS TOO, and that is deliberate. It talks to `localhost`, which
is still a socket. "No test touches the network" is stated without an exception for loopback,
because a rule with one exception acquires a second.

The structural half of the guarantee is asserted elsewhere and still passes unchanged:
`test_stdlib_only.py` walks `hotelcontrols/` and finds no outbound HTTP client, and
`test_compiler_grammar.py` walks the compiler package and finds nothing that could reach a
model. Everything in `tools/proposers/` is outside both, by design - which is why these
runtime locks have to exist.
"""
import ast
import pathlib
import sys

import pytest

from tools import proposers
from tools.proposers import base
from tools.proposers.local import LocalProposer

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "hotelcontrols"


# ---------------------------------------------------------------------------------------
class TestLockTwoCannotBeOpenedByATest:

    def test_a_test_process_is_detected(self):
        assert base.under_test(), "pytest is loaded; this is the condition lock 2 watches for"

    def test_the_local_backend_refuses_even_with_the_variable_set(self, monkeypatch):
        """THE TEST THAT MATTERS. Lock 1 is opened deliberately and the answer is still no."""
        monkeypatch.setenv(base.ENABLE, "1")
        assert base.is_enabled(), "lock 1 is open, so only lock 2 is left to refuse"

        with pytest.raises(base.ProposerDisabled) as refusal:
            LocalProposer().propose("no checkout with money owing")
        assert "test process" in str(refusal.value)

    def test_the_hosted_backend_refuses_even_with_the_variable_set(self, monkeypatch):
        anthropic = pytest.importorskip(
            "anthropic", reason="the hosted backend is an optional extra (requirements-llm.txt)")
        assert anthropic is not None
        from tools.proposers.anthropic_api import AnthropicProposer

        monkeypatch.setenv(base.ENABLE, "1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
        with pytest.raises(base.ProposerDisabled) as refusal:
            AnthropicProposer().propose("no checkout with money owing")
        assert "test process" in str(refusal.value)

    def test_the_refusal_names_the_runner_it_found(self):
        """So whoever hits it knows which lock stopped them rather than guessing."""
        with pytest.raises(base.ProposerDisabled) as refusal:
            base.assert_armed("the thing")
        assert "the thing" in str(refusal.value)


class TestLockOneIsClosedByDefault:

    def test_the_variable_is_not_set_by_anything_in_this_repository(self, monkeypatch):
        monkeypatch.delenv(base.ENABLE, raising=False)
        assert not base.is_enabled()

    def test_the_refusal_says_how_to_arm_it(self, monkeypatch):
        monkeypatch.delenv(base.ENABLE, raising=False)
        with pytest.raises(base.ProposerDisabled) as refusal:
            base.assert_armed("the local proposer")
        assert base.ENABLE in str(refusal.value)

    @pytest.mark.parametrize("value", ["", "0", "no", "off", "false", " ", "maybe"])
    def test_only_an_explicitly_truthy_value_arms_it(self, monkeypatch, value):
        monkeypatch.setenv(base.ENABLE, value)
        assert not base.is_enabled()

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_the_truthy_spellings_are_the_documented_ones(self, monkeypatch, value):
        monkeypatch.setenv(base.ENABLE, value)
        assert base.is_enabled()


# ---------------------------------------------------------------------------------------
class TestTheEngineStillCannotReachAModel:
    """The structural half. These would fail if a backend ever moved inside the package."""

    def test_no_module_in_the_engine_imports_a_proposer_backend(self):
        forbidden = {"tools", "anthropic", "openai"}
        offenders = []
        for path in sorted(ENGINE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in forbidden:
                        offenders.append("%s imports %r" % (path.relative_to(ENGINE.parent),
                                                            name))
        assert not offenders, (
            "the engine must not import a model backend - they live under tools/ and are "
            "injected (decision D10):\n  " + "\n  ".join(offenders))

    def test_the_seam_holds_a_protocol_and_no_client(self):
        """`compiler/sentences.py` defines what a proposer must offer and never provides one."""
        source = (ENGINE / "compiler" / "sentences.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        assert roots <= {"re", "dataclasses", "typing", "__future__"}, roots


class TestTheStubIsTheOnlyBackendTestsUse:

    def test_the_stub_needs_no_arming(self):
        """It has no model behind it, so there is nothing to refuse. That is what makes the
        compose UI demonstrable and testable with nothing installed."""
        assert proposers.build("stub").propose("no checkout with money owing")

    def test_off_builds_nothing_at_all(self):
        assert proposers.build("off") is None

    def test_an_unknown_backend_is_refused_by_name(self):
        with pytest.raises(ValueError, match="no proposer called"):
            proposers.build("telepathy")

    def test_building_the_stub_never_imports_the_hosted_backend(self):
        """The optional dependency must not be needed to use the free or stub backends."""
        sys.modules.pop("tools.proposers.anthropic_api", None)
        proposers.build("stub")
        assert "tools.proposers.anthropic_api" not in sys.modules
