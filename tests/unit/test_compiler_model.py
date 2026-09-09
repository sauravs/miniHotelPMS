# -*- coding: utf-8 -*-
"""
THE MODEL SEAM, EXERCISED AGAINST A STUB - decision D9, and the whole of it.

`docs/open-questions.md` D9, taken 2026-09-09 before this slice opened:

    Build the seam; exercise it against a stub. ... A stub tests the gate HARDER than a real
    model does. Slice 9's gate is that a sentence naming vocabulary nobody defined is rejected
    by name. A stub emits exactly the proposals that exercise it - an undeclared field, an
    unknown operator, an aggregate with no group_by, a predicate with two right-hand sides. A
    real model mostly emits plausible IR, which exercises the validator least. The thing under
    test is the gate, not the model.

So this file is a set of deliberately broken proposals, and the claim it protects is a
NEGATIVE one: there is no route from a proposal to a runnable rule that skips a check a
hand-written JSON file has to pass. `TestTheRejectionIsTheSameCodeNotMerelyTheSameOutcome` is
the test that makes that claim testable rather than asserted - it compares the compiler's
refusal against `spec.validate` called directly on the same document, message for message.

No model is wired. Nothing here can reach one: the proposer is handed in, and the compiler
package has no HTTP client to find one with (asserted over the AST in
`test_compiler_grammar.py`).
"""
import copy

import pytest

from hotelcontrols.compiler import LOGIC_KEYS, ModelCompiler, deployment_of
from hotelcontrols.spec import Registry, load, validate


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def deployment():
    return deployment_of(load("checkout_money_owed").raw)


@pytest.fixture
def good_logic():
    """A shipped control's rule half - the shape a proposer is asked for."""
    raw = copy.deepcopy(load("checkout_money_owed").raw)
    return {key: raw[key] for key in LOGIC_KEYS}


class Stub:
    """A proposer that returns whatever it was given. The model, standing still.

    Deliberately dumb. A stub that generated proposals would be a second thing under test, and
    the thing under test is the gate.
    """

    def __init__(self, proposal):
        self.proposal = proposal
        self.asked = []

    def propose(self, sentence):
        self.asked.append(sentence)
        return self.proposal


class Exploding:
    def propose(self, sentence):
        raise RuntimeError("the model is not available")


SENTENCE = "a reservation cannot be closed while the guest still owes money"


def compile_proposal(proposal, registry, deployment, sentence=SENTENCE):
    return ModelCompiler(registry, Stub(proposal)).compile(sentence, deployment=deployment)


# ---------------------------------------------------------------------------------------
class TestTheSeamItself:
    """One method, `propose(sentence) -> dict`, and nothing else crosses."""

    def test_a_well_formed_proposal_compiles(self, good_logic, registry, deployment):
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is not None, [str(p) for p in result.problems]
        assert result.ir["assertion"] == good_logic["assertion"]

    def test_the_proposer_is_asked_for_the_sentence_and_nothing_else_crosses(
            self, good_logic, registry, deployment):
        stub = Stub(good_logic)
        ModelCompiler(registry, stub).compile(SENTENCE, deployment=deployment)
        assert stub.asked == [SENTENCE]

    def test_the_compiled_rule_carries_the_sentence_that_was_proposed_from(
            self, good_logic, registry, deployment):
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir["natural_language"] == SENTENCE

    def test_confidence_is_none_because_nothing_here_established_one(
            self, good_logic, registry, deployment):
        """The same rule that makes a value nobody could establish an UNKNOWN rather than a
        PASS. A model's opinion of itself is not evidence, and no acceptance decision here
        reads this field."""
        assert compile_proposal(good_logic, registry, deployment).confidence is None

    def test_a_proposer_that_fails_becomes_a_stated_reason_rather_than_a_traceback(
            self, registry, deployment):
        result = ModelCompiler(registry, Exploding()).compile(SENTENCE, deployment=deployment)
        assert result.ir is None
        assert any("not available" in str(p) for p in result.problems), result.problems

    def test_a_proposal_that_is_not_an_ir_object_is_refused_naming_what_arrived(
            self, registry, deployment):
        result = compile_proposal("scope: everything", registry, deployment)
        assert result.ir is None
        assert any("str" in str(p) for p in result.problems), result.problems

    def test_a_proposal_missing_a_whole_clause_is_told_which_and_what_it_says(
            self, good_logic, registry, deployment):
        del good_logic["assertion"]
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("assertion" in str(p) and "must be true" in str(p)
                   for p in result.problems), result.problems

    def test_a_proposal_reaching_into_the_deployments_half_is_refused(
            self, good_logic, registry, deployment):
        """The split is enforced in both directions. A proposer that wrote its own population
        query would be naming a PMS endpoint from above the boundary (criterion 5)."""
        good_logic["population"] = {"description": "everything", "provider_query": {"x": {}}}
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("population" in str(p) for p in result.problems), result.problems


# ---------------------------------------------------------------------------------------
class TestTheFourClassesOfBadProposal:
    """`plan.md` slice 9: "The stub emits each class of bad proposal ... Each is rejected
    exactly as a hand-written IR would be, by the same code path."

    One class per test, each broken in exactly ONE way, so a passing test means the check it
    names fired rather than that the document was malformed six ways at once.
    """

    def test_an_undeclared_field_is_rejected_naming_the_field(
            self, good_logic, registry, deployment):
        """Check 1, and the §17 gate. MiniHotel has no VIP flag at all - the only VIP
        information in the whole 2026 capture is Hebrew prose in a free-text remarks field
        (open question 1.5)."""
        good_logic["scope"] = [{"field": "reservation.vip", "operator": "equals",
                                "value": True}]
        good_logic["required_evidence"].append({"field": "reservation.vip", "source": "pms"})
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("reservation.vip" in str(p) and "undeclared" in str(p)
                   for p in result.problems), [str(p) for p in result.problems]

    def test_an_unknown_operator_is_rejected(self, good_logic, registry, deployment):
        good_logic["assertion"]["predicates"][0]["operator"] = "approximately"
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("approximately" in str(p) for p in result.problems), result.problems

    def test_an_aggregate_with_no_group_by_is_rejected_saying_why_a_count_needs_one(
            self, good_logic, registry, deployment):
        """F2 exactly. v1 shipped two aggregate assertions with no grouping key, which is why
        duplicate detection could never be evaluated: the rule never said what a duplicate was
        OF."""
        good_logic["assertion"] = {"mode": "aggregate", "predicates": [
            {"field": "reservation.id", "operator": "count_lte", "value": 1}]}
        good_logic["required_evidence"].append({"field": "reservation.id", "source": "pms"})
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("group_by" in str(p) for p in result.problems), result.problems

    def test_a_predicate_with_two_right_hand_sides_is_rejected(
            self, good_logic, registry, deployment):
        """Check 4. Two right-hand sides means the engine picks one, and the rule that ran is
        not the rule that was written."""
        good_logic["assertion"]["predicates"][0]["compare_to"] = "reservation.total_amount"
        good_logic["required_evidence"].append(
            {"field": "reservation.total_amount", "source": "pms"})
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("exactly one of value, compare_to or tenant_setting" in str(p)
                   for p in result.problems), result.problems

    def test_a_field_read_but_never_declared_as_evidence_is_rejected(
            self, good_logic, registry, deployment):
        """Check 2, the fifth class and the quietest one. Without it a rule depends on a field
        the evidence layer was never asked to fetch, and the failure appears at runtime as an
        UNKNOWN that looks like the hotel's data gap rather than the rule's defect."""
        good_logic["required_evidence"] = [
            e for e in good_logic["required_evidence"] if e["field"] != "folio.balance_due"]
        result = compile_proposal(good_logic, registry, deployment)
        assert result.ir is None
        assert any("folio.balance_due" in str(p) and "required_evidence" in str(p)
                   for p in result.problems), result.problems


# ---------------------------------------------------------------------------------------
class TestTheRejectionIsTheSameCodeNotMerelyTheSameOutcome:
    """The claim slice 9 actually rests on.

    "A model's proposal is rejected exactly as a human's is, by the same code path" is easy to
    say and easy to get wrong by writing a second, kinder validator on the model side. So this
    compares the compiler's refusal against `spec.validate` called DIRECTLY on the same
    document - message for message. A private check in the model path would show up here as an
    extra message; a relaxed one would show up as a missing message.
    """

    BREAKAGES = (
        ("undeclared field",
         lambda logic: logic["scope"].__setitem__(
             0, {"field": "reservation.vip", "operator": "equals", "value": True})),
        ("unknown operator",
         lambda logic: logic["assertion"]["predicates"][0].__setitem__(
             "operator", "approximately")),
        ("aggregate with no group_by",
         lambda logic: logic.__setitem__("assertion", {"mode": "aggregate", "predicates": [
             {"field": "folio.balance_due", "operator": "count_lte", "value": 1}]})),
        ("two right-hand sides",
         lambda logic: logic["assertion"]["predicates"][0].__setitem__(
             "compare_to", "folio.total_paid")),
    )

    @pytest.mark.parametrize("label,break_it", BREAKAGES, ids=[b[0] for b in BREAKAGES])
    def test_the_messages_are_the_validators_own(self, label, break_it, good_logic,
                                                 registry, deployment):
        break_it(good_logic)
        through_the_compiler = compile_proposal(good_logic, registry, deployment)

        by_hand = dict(deployment)
        by_hand.update(good_logic)
        by_hand["natural_language"] = SENTENCE
        by_hand["restricted_language"] = SENTENCE
        directly = validate(by_hand, registry)

        assert through_the_compiler.ir is None
        assert [str(p) for p in through_the_compiler.problems] == [str(p) for p in directly], (
            "the model path's rejection of a %s differs from the validator's own" % label)
