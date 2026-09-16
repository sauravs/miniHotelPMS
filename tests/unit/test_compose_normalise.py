# -*- coding: utf-8 -*-
"""
L0 - PROSE becomes a restricted sentence, and then the same rule as everything else.

`normalise(prose, proposer, registry, deployment) -> Normalisation` is slice 13's seam and
decision D10's whole substance. Every test here protects one claim:

    D10       the model produces a SENTENCE, and the deterministic grammar produces the rule.
              So a compiled draft carries `confidence == 1.0` and `source == "grammar"`: the
              parse was exact, whatever drafted the text that was parsed.
    §17       the gate is unchanged. A proposal naming vocabulary nobody declared is refused
              BY NAME, by the same validator a hand-written IR file goes through.
    §18       ambiguity is reported, never resolved - and a proposer that asks a question
              instead of guessing has behaved correctly, not failed.
    F13-ish   a proposer is somebody else's code. When it breaks, that is a stated reason on
              screen, never a traceback out of a compile step.

NO TEST HERE TOUCHES A MODEL OR A NETWORK. `StubProposer` is a dictionary of fixed replies, and
the live backends refuse to arm inside a test process anyway - see
`test_proposers_refuse_in_tests.py`.
"""
import pytest

from hotelcontrols.compiler import (Normalisation, Turn, deployment_of, normalise, split_reply)
from hotelcontrols.spec import Registry, load
from tools.proposers import ExplodingProposer, StubProposer


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


@pytest.fixture(scope="module")
def deployment():
    """A real control's deployment half, which is what the UI borrows too.

    A sentence cannot name a population without naming a PMS endpoint (criterion 5), so this
    arrives as data in both the product and the test - the test is not being given something
    the flow does not have.
    """
    borrowed = deployment_of(load("room_assignment_type_validity").raw)
    return {**borrowed, "control_id": "composed_draft", "name": "Composed Draft",
            "version": 1, "source_control": "composed"}


def a_turn(prose, proposer=None, registry=None, deployment=None, history=()):
    return normalise(prose, proposer or StubProposer(), registry, deployment=deployment,
                     history=history)


# ---------------------------------------------------------------------------------------
class TestProseBecomesARule:

    def test_a_sentence_the_stub_proposes_compiles_to_a_validated_ir(self, registry,
                                                                     deployment):
        result = a_turn("every reservation must record a guest email", registry=registry,
                        deployment=deployment)
        assert result.ok, [str(p) for p in result.compilation.problems]
        assert result.compilation.ir["control_id"] == "composed_draft"

    def test_the_rule_is_the_grammars_work_not_the_models(self, registry, deployment):
        """D10. The model wrote text; the parse is exact, so confidence is 1.0 and the source
        is the grammar. A model's opinion of itself never enters this."""
        result = a_turn("every reservation must record a guest email", registry=registry,
                        deployment=deployment)
        assert result.compilation.confidence == 1.0
        assert result.compilation.source == "grammar"

    def test_the_proposed_sentence_is_kept_verbatim(self, registry, deployment):
        """An author cannot correct a sentence they were never shown, and the UI lets them edit
        it before anything runs."""
        result = a_turn("no checkout with money still owing", registry=registry,
                        deployment=deployment)
        assert result.sentence.startswith("every reservation where")
        assert "folio.balance_due at most 0" in result.sentence

    def test_the_ir_declares_the_evidence_the_sentence_reads(self, registry, deployment):
        result = a_turn("no checkout with money still owing", registry=registry,
                        deployment=deployment)
        fields = {entry["field"] for entry in result.compilation.ir["required_evidence"]}
        assert "folio.balance_due" in fields and "reservation.status" in fields

    def test_the_sentence_is_filed_on_the_ir_as_its_restricted_language(self, registry,
                                                                        deployment):
        """So a stored draft can be recompiled and compared to itself, exactly as
        `tools/validate_spec.py` does for the eleven shipped controls."""
        result = a_turn("every reservation must record a guest email", registry=registry,
                        deployment=deployment)
        assert result.compilation.ir["restricted_language"] == result.sentence


# ---------------------------------------------------------------------------------------
class TestTheGateIsUnchanged:
    """§17. A model earns no extra trust, and no second validation path exists."""

    def test_an_undeclared_field_is_refused_by_name(self, registry, deployment):
        result = a_turn("VIP rooms must be inspected before arrival", registry=registry,
                        deployment=deployment)
        assert not result.ok
        reasons = " ".join(str(p) for p in result.compilation.problems)
        # BY NAME is the whole point. "invalid rule" would tell a hotel nothing.
        assert "room.inspection_status" in reasons
        assert "reservation.vip" in reasons

    def test_a_sentence_that_chooses_its_own_population_is_refused(self, registry, deployment):
        """Criterion 5. A rule that named its own date window would be a rule that named a PMS
        query, and the sentence printed beside a verdict would stop being the whole rule."""
        result = a_turn("reservations arriving tomorrow need a guarantee", registry=registry,
                        deployment=deployment)
        assert not result.ok
        assert "arriving" in " ".join(str(p) for p in result.compilation.problems)

    def test_a_refused_proposal_still_shows_what_was_proposed(self, registry, deployment):
        result = a_turn("VIP rooms must be inspected before arrival", registry=registry,
                        deployment=deployment)
        assert result.sentence, "the sentence must survive its own rejection"

    def test_nothing_compiles_without_a_deployment(self, registry):
        """The deployment half is not optional and is not guessable. A rule with no bounded
        population is an unbounded number of calls against somebody else's server (R1, R8)."""
        result = a_turn("no checkout with money still owing", registry=registry,
                        deployment=None)
        assert not result.ok
        assert "population" in " ".join(str(p) for p in result.compilation.problems)


# ---------------------------------------------------------------------------------------
class TestAQuestionIsABetterAnswerThanAGuess:
    """§18: *an LLM can interpret language, but it cannot invent hotel policy.*"""

    def test_a_policy_question_comes_back_as_a_question_not_a_rule(self, registry, deployment):
        result = a_turn("corporate rates must belong to an approved company", registry=registry,
                        deployment=deployment)
        assert result.is_question
        assert not result.ok
        assert "rate codes" in result.question

    def test_a_question_is_not_a_failure(self, registry, deployment):
        """It has no problems to fix. Rendering it as an error would teach a reader to distrust
        the one behaviour worth keeping."""
        result = a_turn("corporate rates must belong to an approved company", registry=registry,
                        deployment=deployment)
        assert result.problems == ()
        assert result.compilation is None

    def test_an_ambiguous_operand_is_reported_rather_than_chosen(self, registry, deployment):
        """`is cancelled` means the string "cancelled" or a field called `cancelled`, and the
        grammar declines to pick. Asserted through this seam because a proposer will produce
        exactly this - an unquoted literal is the commonest thing a model gets wrong."""
        class Unquoted:
            name = "unquoted"

            def propose(self, prose, history=()):
                return 'every reservation where reservation.status is cancelled ' \
                       'must have folio.balance_due at most 0'

        result = a_turn("x", proposer=Unquoted(), registry=registry, deployment=deployment)
        assert not result.ok
        assert result.compilation.ambiguities


# ---------------------------------------------------------------------------------------
class TestAProposerIsSomebodyElsesCode:

    def test_a_proposer_that_raises_becomes_a_stated_reason(self, registry, deployment):
        result = a_turn("anything", proposer=ExplodingProposer(), registry=registry,
                        deployment=deployment)
        assert not result.ok
        assert "the proposer failed" in str(result.problems[0])
        assert "refused the connection" in str(result.problems[0])

    def test_a_proposer_returning_the_wrong_type_is_refused_not_crashed(self, registry,
                                                                       deployment):
        class Wrong:
            name = "wrong"

            def propose(self, prose, history=()):
                return {"entity": "reservation"}

        result = a_turn("x", proposer=Wrong(), registry=registry, deployment=deployment)
        assert not result.ok
        assert "must be a sentence" in str(result.problems[0])

    def test_empty_prose_is_refused_before_a_proposer_is_asked(self, registry, deployment):
        """Nothing is spent - no call, no token, no second of a local model's time - on a
        request that says nothing."""
        stub = StubProposer()
        result = a_turn("   ", proposer=stub, registry=registry, deployment=deployment)
        assert not result.ok
        assert stub.calls == ()

    def test_a_proposer_without_a_name_is_still_usable(self, registry, deployment):
        class Nameless:
            def propose(self, prose, history=()):
                return "every reservation must have folio.balance_due at most 0"

        result = a_turn("x", proposer=Nameless(), registry=registry, deployment=deployment)
        assert result.proposer == "Nameless"


# ---------------------------------------------------------------------------------------
class TestTheConversationCarriesItsOwnRefusals:
    """Feeding the reason back is what makes a second attempt worth making."""

    def test_history_reaches_the_proposer(self, registry, deployment):
        stub = StubProposer()
        history = (Turn(prose="VIP rooms must be inspected",
                        sentence="every reservation where reservation.vip is \"true\" "
                                 "must have room.inspection_status is \"clean\"",
                        problems=("references undeclared canonical field 'reservation.vip'",)),)
        a_turn("try again", proposer=stub, registry=registry, deployment=deployment,
               history=history)
        _prose, carried = stub.calls[0]
        assert carried == history

    def test_a_turn_records_why_it_was_refused(self, registry, deployment):
        result = a_turn("VIP rooms must be inspected before arrival", registry=registry,
                        deployment=deployment)
        turn = result.as_turn()
        assert turn.sentence == result.sentence
        assert any("room.inspection_status" in problem for problem in turn.problems)

    def test_a_turn_records_a_question_too(self, registry, deployment):
        result = a_turn("corporate rates must belong to an approved company", registry=registry,
                        deployment=deployment)
        assert result.as_turn().is_question


# ---------------------------------------------------------------------------------------
class TestReplyParsing:
    """Models wrap answers in prose and fences however firmly they are asked not to.

    The discriminator is the GRAMMAR'S OWN rule - a rule starts with a quantifier - so there is
    one definition of "this is a sentence" in the codebase rather than two.
    """

    @pytest.mark.parametrize("reply,expected", [
        ("every reservation must have folio.balance_due at most 0",
         "every reservation must have folio.balance_due at most 0"),
        ("Here it is:\n```\nevery reservation must have folio.balance_due at most 0\n```\nOk?",
         "every reservation must have folio.balance_due at most 0"),
        ("- every reservation must have folio.balance_due at most 0",
         "every reservation must have folio.balance_due at most 0"),
        ("every reservation\n    must have folio.balance_due at most 0",
         "every reservation must have folio.balance_due at most 0"),
        ("every reservation must have folio.balance_due at most 0\n\nI assumed money owed.",
         "every reservation must have folio.balance_due at most 0"),
    ])
    def test_a_sentence_is_found_however_it_is_wrapped(self, reply, expected):
        assert split_reply(reply)[0] == expected

    def test_a_closing_fence_ends_the_sentence(self):
        """Regression. Dropping fence lines rather than blanking them joined the rule to the
        pleasantry after it, so the sentence ended with "Hope that helps" - which the grammar
        refuses, correctly, about entirely the wrong thing."""
        sentence, rest = split_reply(
            "```\nevery reservation must have folio.balance_due at most 0\n```\nHope that helps")
        assert sentence == "every reservation must have folio.balance_due at most 0"
        assert "Hope that helps" in rest

    def test_a_reply_with_no_rule_in_it_is_all_question(self):
        sentence, rest = split_reply("Which rate codes count as corporate?")
        assert sentence == ""
        assert rest == "Which rate codes count as corporate?"

    def test_an_empty_reply_is_neither(self):
        assert split_reply("") == ("", "")


# ---------------------------------------------------------------------------------------
class TestNothingHereReachesAModel:

    def test_the_seam_never_looks_for_a_proposer(self):
        """`normalise` takes one. It cannot acquire one, which is what keeps the compiler
        package free of anything that could open a socket."""
        with pytest.raises(TypeError):
            normalise("every reservation must have folio.balance_due at most 0")  # noqa

    def test_a_normalisation_with_no_compilation_is_not_ok(self):
        assert not Normalisation(prose="x").ok
