# -*- coding: utf-8 -*-
"""
A RULE NOBODY WROTE, TYPED AS PROSE, RUNNING ON BOTH PROVIDERS.

Slice 13's gate, and the strongest form of the claim decision D10 rests on. `test_runs.py` and
`test_compiled_control_runs.py` already prove that a control is a spec change rather than a
code change; this file starts one step further back - **nobody writes the sentence either** -
and then checks the thing that actually matters:

    a draft composed from prose behaves exactly like a shipped control.

Same verdicts on both providers, same record ids, same call count. If a composed rule were
special in any way, the canonical boundary would have a hole in it that a normal control does
not, and the portability claim would hold for eleven rules and not for the twelfth.

WHAT IS AND IS NOT BEING TESTED
--------------------------------
Not the model. `StubProposer` is a dictionary of fixed replies and no test in this repository
reaches a model at all (`test_proposers_refuse_in_tests.py`). What is under test is the
pipeline: prose -> sentence -> deterministic grammar -> the same validator -> a file on disk ->
a run through an adapter that has never heard of any of this.
"""
import json
import shutil

import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig, available, load, validate
from hotelcontrols.spec.registry import SPEC_DIR, Registry
from hotelcontrols.web import App
from tools.proposers import StubProposer

# The same logical hotel through two deliberately incompatible wire formats, at the instant
# both captures describe.
PROPERTIES = {"sandbox": "sandbox2026", "demo": "demo2026"}
AS_OF = "2026-07-08"

# Prose a person would type. It is NOT one of the eleven, and the rule it becomes is not
# shipped - so nothing here can pass by accidentally matching a filed control.
PROSE = "every reservation must record a guest email"
FORM = ("control_id=guest_email_on_file&name=Guest+Email+On+File"
        "&template=room_assignment_type_validity"
        "&property=sandbox&evidence=sandbox2026&sentence=")


@pytest.fixture
def draft_dir(tmp_path):
    directory = tmp_path / "drafts"
    (directory / "ir").mkdir(parents=True)
    for name in ("canonical_fields.json", "ir_schema.json"):
        shutil.copy(SPEC_DIR / name, directory / name)
    return directory


@pytest.fixture
def composed(draft_dir):
    """Prose in, a filed draft out - through the app, exactly as a reader would."""
    app = App(proposer=StubProposer(), draft_dir=draft_dir)

    asked = app.handle_post("/compose", "prose=%s" % PROSE.replace(" ", "+"))[2]
    assert "THIS COMPILES" in asked

    # The sentence the proposer produced, taken from the box it was put in - which is what a
    # person would press the button on.
    sentence = asked.split('name="sentence" rows="4">')[1].split("</textarea>")[0]
    sentence = sentence.replace("&quot;", '"').replace("&amp;", "&")

    from urllib.parse import quote_plus
    status, _ct, _body = app.handle_post("/compose/accept", FORM + quote_plus(sentence))
    assert status == 303
    return app, draft_dir, sentence


def a_run(property_id, draft_dir, control_id="guest_email_on_file"):
    tenant = TenantConfig.load(property_id)
    package = next(p for p in all_providers() if p.name == tenant.provider)
    adapter, _source = package.build(tenant, PROPERTIES[property_id])
    return run(control_id, tenant, adapter, FixedClock.at(AS_OF, tenant.timezone),
               evidence_label=PROPERTIES[property_id], spec_dir=draft_dir)


# ---------------------------------------------------------------------------------------
class TestTheDraftIsAnOrdinaryControl:

    def test_it_is_on_disk_as_json(self, composed):
        _app, draft_dir, _sentence = composed
        path = draft_dir / "ir" / "guest_email_on_file.json"
        assert json.loads(path.read_text(encoding="utf-8"))["control_id"] \
               == "guest_email_on_file"

    def test_it_passes_the_same_validator_every_shipped_control_passes(self, composed):
        _app, draft_dir, _sentence = composed
        ir = load("guest_email_on_file", draft_dir)
        assert validate(ir, Registry.load(), spec_dir=draft_dir) == []

    def test_the_spec_loader_lists_it_with_no_special_casing(self, composed):
        _app, draft_dir, _sentence = composed
        assert available(draft_dir) == ("guest_email_on_file",)

    def test_its_sentence_recompiles_to_the_same_rule(self, composed):
        """The check `tools/validate_spec.py` runs over the eleven, applied to a draft: the
        sentence on file and the rule on file must still be the same rule."""
        from hotelcontrols.compiler import compile_sentence, deployment_of
        _app, draft_dir, _sentence = composed
        ir = load("guest_email_on_file", draft_dir)
        again = compile_sentence(ir["restricted_language"], Registry.load(),
                                 deployment=deployment_of(ir.raw))
        assert again.ok, [str(p) for p in again.problems]
        assert again.ir["assertion"] == ir["assertion"]
        assert again.ir["scope"] == ir["scope"]

    def test_the_rule_is_the_grammars_and_says_so(self, composed):
        """D10. A draft records that it was composed, so its provenance outlives this screen -
        and `source_control: composed` is how a reader tells it from the eleven."""
        _app, draft_dir, _sentence = composed
        ir = load("guest_email_on_file", draft_dir)
        assert ir["source_control"] == "composed"
        assert "DRAFT" in " ".join(ir["caveats"])


# ---------------------------------------------------------------------------------------
class TestItRunsOnBothProviders:
    """Criterion 7, for a rule that arrived as prose an hour ago."""

    @pytest.mark.parametrize("property_id", sorted(PROPERTIES))
    def test_the_run_is_not_blocked(self, composed, property_id):
        _app, draft_dir, _sentence = composed
        result = a_run(property_id, draft_dir)
        assert not result.is_blocked, result.blocked

    @pytest.mark.parametrize("property_id", sorted(PROPERTIES))
    def test_it_reaches_a_conclusion(self, composed, property_id):
        """An absent email has `absent_means: false` in the registry, so it is a definite
        finding about the record rather than a gap in what we fetched."""
        _app, draft_dir, _sentence = composed
        result = a_run(property_id, draft_dir)
        assert result.coverage.concluded, result.coverage.headline

    def test_the_same_rule_yields_the_same_verdicts_through_both(self, composed):
        """The whole thesis, for a composed rule. Per record id, not merely in aggregate."""
        _app, draft_dir, _sentence = composed
        by_provider = {}
        for property_id in PROPERTIES:
            result = a_run(property_id, draft_dir)
            by_provider[property_id] = {
                verdict.record_id: verdict.outcome for verdict in result.verdicts}
        left, right = (by_provider[name] for name in sorted(PROPERTIES))
        assert left == right, "a composed rule must be as portable as a shipped one"
        assert left, "and it must actually have produced verdicts"

    def test_the_call_count_is_identical_too(self, composed):
        """Cost is part of the contract. A rule that cost more through one provider would mean
        the boundary leaked something about how evidence is fetched (R1)."""
        _app, draft_dir, _sentence = composed
        counts = {name: a_run(name, draft_dir).calls for name in PROPERTIES}
        assert len(set(counts.values())) == 1, counts

    def test_every_verdict_still_carries_its_evidence(self, composed):
        """Criterion 3 does not get a discount for a rule that was drafted by a model."""
        _app, draft_dir, _sentence = composed
        for verdict in a_run("sandbox", draft_dir).verdicts:
            assert verdict.evidence
            assert verdict.reason.strip()


# ---------------------------------------------------------------------------------------
class TestItIsStillNotAShippedControl:
    """The line the criterion-1 figure in docs/plan.md depends on."""

    def test_the_reviewed_directory_is_untouched(self, composed):
        assert "guest_email_on_file" not in available()
        assert len(available()) == 11

    def test_the_app_keeps_the_two_lists_apart(self, composed):
        app, _draft_dir, _sentence = composed
        assert "guest_email_on_file" in app._drafts()
        assert "guest_email_on_file" not in app._controls()

    def test_a_draft_is_run_from_the_drafts_root(self, composed):
        """So a draft and a reviewed control of the same name could never be confused for one
        another - and `_compose_accept` refuses that collision anyway."""
        app, draft_dir, _sentence = composed
        assert app._spec_dir_for("guest_email_on_file") == draft_dir
        assert app._spec_dir_for("checkout_money_owed") == app.spec_dir
