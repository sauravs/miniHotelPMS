# -*- coding: utf-8 -*-
"""
A CONTROL THIS PROJECT HAS NEVER SHIPPED, TYPED AS A SENTENCE AND RUN.

Criterion 6 from the other end. Criterion 6 says a twelfth control is a spec change rather than
a code change, and slice 6 proved it by dropping a hand-written IR file into a directory. This
file makes the stronger version of the claim: **nobody writes the file.** Somebody writes a
sentence, the compiler produces the IR, and the runner executes it - with no import touched, no
branch taken on which control it is, and no fixture added.

The sentence below is not one of the eleven. It is a rule this repository has never held:

    every reservation where reservation.status is not "cancelled"
        must have reservation.guest.email exists

It reaches real PASS and FAIL verdicts on captured evidence, on both providers, because
`reservation.guest.email` has `absent_means: false` in the registry - an absent email is a
definite finding about the record and not a gap in what we fetched.

WHAT THE TEST STILL HAS TO SUPPLY, AND WHY THAT IS NOT A CHEAT
---------------------------------------------------------------
The deployment: which bounded query finds the records on each provider, when the control runs,
how old its evidence may be, and who hears about a failure. A sentence cannot name a population
query without naming a PMS endpoint, which criterion 5 forbids - so it does not try, and the
compiler says so by name when it is missing. The population block here is borrowed verbatim
from a shipped control, which is what a hotel adding a second rule over the same records would
actually do.
"""
import copy
import json

import pytest

from hotelcontrols.compiler import compile_sentence, deployment_of
from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.spec import Registry, TenantConfig, load
from hotelcontrols.spec.registry import SPEC_DIR
from hotelcontrols.runner import run

SENTENCE = ('every reservation where reservation.status is not "cancelled" '
            'must have reservation.guest.email exists')

AS_OF = "2026-07-08T09:00"
CAPTURES = {"sandbox": "sandbox2026", "demo": "demo2026"}


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def deployment():
    """Everything the sentence does not say, written out as a hotel would supply it.

    The population is lifted from a shipped control - the same bounded window of arrivals - so
    this reads as "another rule about the records we already look at" rather than as a new
    integration.
    """
    return {
        "control_id": "guest_email_on_file",
        "version": 1,
        "name": "Guest Email On File",
        "source_control": "not-shipped-example",
        "population": copy.deepcopy(
            deployment_of(load("room_assignment_type_validity").raw)["population"]),
        "execution": {"mode": "daily",
                      "rationale": "a missing email is actionable once a day, not once a minute"},
        "freshness_requirement": {"maximum_age": "24h"},
        "unknown_conditions": [
            {"when": "the reservation response does not carry a contact block",
             "reason": "no email can be established for this record"}],
        "action": {"type": "report", "severity": "low", "audience": "front_office_manager"},
    }


@pytest.fixture(scope="module")
def compiled(registry, deployment):
    result = compile_sentence(SENTENCE, registry, deployment=deployment)
    assert result.ir is not None, [str(p) for p in result.problems]
    return result


@pytest.fixture(scope="module")
def spec_dir(compiled, tmp_path_factory):
    """A spec directory holding one control nobody wrote by hand."""
    directory = tmp_path_factory.mktemp("compiled-spec")
    (directory / "ir").mkdir()
    for name in ("canonical_fields.json", "ir_schema.json"):
        (directory / name).symlink_to(SPEC_DIR / name)
    (directory / "ir" / "guest_email_on_file.json").write_text(
        json.dumps(compiled.ir, indent=2), encoding="utf-8")
    return directory


def a_run(property_id, spec_dir):
    tenant = TenantConfig.load(property_id)
    package = next(p for p in all_providers() if p.name == tenant.provider)
    adapter, _ = package.build(tenant, CAPTURES[property_id])
    return run("guest_email_on_file", tenant, adapter,
               FixedClock.at(AS_OF, tenant.timezone),
               evidence_label=CAPTURES[property_id], spec_dir=spec_dir)


class TestASentenceBecomesARunningControl:

    def test_the_run_is_not_blocked(self, spec_dir):
        result = a_run("sandbox", spec_dir)
        assert not result.is_blocked, result.blocked

    def test_it_reaches_real_conclusions_rather_than_only_unknowns(self, spec_dir):
        """The point of running it at all. A compiled control that executed but concluded
        nothing would satisfy the letter of criterion 6 and none of its meaning."""
        counts = a_run("sandbox", spec_dir).counts
        assert counts["PASS"] + counts["FAIL"] > 0, counts
        assert counts["total"] > 0

    def test_a_verdict_carries_the_field_that_produced_it(self, spec_dir):
        """Criterion 3. A compiled rule's evidence table is the compiled rule's own doing:
        `required_evidence` was derived from the sentence, so if the derivation were wrong the
        table would be empty here."""
        result = a_run("sandbox", spec_dir)
        verdict = next(v for v in result.verdicts if v.outcome is not Outcome.EXCLUDED)
        assert any(line.field == "reservation.guest.email" for line in verdict.evidence), \
            verdict.evidence

    def test_the_sentence_is_what_the_run_reports_as_its_rule(self, spec_dir):
        """The chain criterion 3 is about - rule as written, answer, evidence - starts at the
        sentence somebody typed. A run reporting a different sentence from the one that
        produced it would break the chain at its first link."""
        assert a_run("sandbox", spec_dir).natural_language == SENTENCE

    def test_the_same_sentence_answers_identically_through_both_providers(self, spec_dir):
        """Criterion 7 applied to a rule that did not exist when either adapter was written.
        Neither provider has ever seen this control, and nothing below the compiler changed."""
        answers = {p: sorted((v.record_id, v.outcome.value)
                             for v in a_run(p, spec_dir).verdicts)
                   for p in ("sandbox", "demo")}
        assert answers["sandbox"] == answers["demo"]

    def test_it_costs_the_same_calls_on_both_providers(self, spec_dir):
        """R1. The cost model is a property of the control, not of the API underneath."""
        assert len({a_run(p, spec_dir).calls for p in ("sandbox", "demo")}) == 1


def test_the_shipped_spec_directory_was_not_touched():
    """The compiled control lives in a temporary directory and nowhere else.

    A test that wrote into `spec/ir/` would make the repository's control list depend on
    whether the suite had been run, and `available()` is what the index and criterion 6 rest
    on.
    """
    assert not (SPEC_DIR / "ir" / "guest_email_on_file.json").exists()
