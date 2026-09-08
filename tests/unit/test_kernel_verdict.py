# -*- coding: utf-8 -*-
"""
Verdict and Outcome - the answer, and what produced it.

An unexplained verdict is not auditable, and audit is the product. So a Verdict cannot be
constructed without evidence or without a reason: a structural guarantee rather than a
convention someone has to remember on the day they add the twelfth control.

FOUR OUTCOMES, NOT THREE. PASS, FAIL and UNKNOWN are the control's answers. EXCLUDED is the
fourth thing that can happen to a record and deliberately is not one of them: the control did
not apply, so it has no opinion. Folding EXCLUDED into PASS would let a run over a hundred
reservations where ninety were out of scope report "90 passed" - a compliance number made of
records nobody checked.
"""
import pytest

from hotelcontrols.kernel import (EvidenceLine, NotAuditable, Outcome, Value, Verdict)


def _evidence():
    return [EvidenceLine("folio.balance_due", Value.known("0", source="pms:x/Balance"))]


class TestOutcome:
    def test_there_are_exactly_four_outcomes(self):
        assert set(Outcome) == {Outcome.PASS, Outcome.FAIL, Outcome.UNKNOWN, Outcome.EXCLUDED}

    def test_excluded_is_not_pass(self):
        """The distinction the whole compliance number depends on."""
        assert Outcome.EXCLUDED is not Outcome.PASS

    def test_an_outcome_serialises_as_its_own_name(self):
        """Runs are stored as JSON and re-read months later; the stored form must be the
        word a human would expect to see."""
        assert str(Outcome.UNKNOWN) == "UNKNOWN"

    def test_answered_distinguishes_the_two_real_answers(self):
        """Coverage (finding F5) is built on this: `evaluated = PASS + FAIL`. A run where
        every record was EXCLUDED or UNKNOWN concluded nothing, and must not render as a
        clean bill of health."""
        assert Outcome.PASS.is_answer and Outcome.FAIL.is_answer
        assert not Outcome.UNKNOWN.is_answer
        assert not Outcome.EXCLUDED.is_answer


class TestVerdictRequiresItsWorking:
    def test_a_verdict_without_evidence_cannot_be_constructed(self):
        """Every success criterion about this product is some form of 'show your working'."""
        with pytest.raises(NotAuditable):
            Verdict(Outcome.FAIL, "the balance is not zero", evidence=[])

    def test_a_verdict_without_a_reason_cannot_be_constructed(self):
        with pytest.raises(NotAuditable):
            Verdict(Outcome.PASS, "", evidence=_evidence())

    def test_a_verdict_whose_reason_is_whitespace_is_also_refused(self):
        with pytest.raises(NotAuditable):
            Verdict(Outcome.PASS, "   ", evidence=_evidence())

    def test_a_well_formed_verdict_keeps_everything_it_was_given(self):
        v = Verdict(Outcome.FAIL, "balance_due is 812.5 ILS, which does not satisfy `lte 0`",
                    evidence=_evidence(), control_id="checkout_money_owed",
                    record_id="007003199")
        assert v.outcome is Outcome.FAIL
        assert v.control_id == "checkout_money_owed"
        assert v.record_id == "007003199"
        assert len(v.evidence) == 1


class TestVerdictReporting:
    def test_unknown_fields_names_what_the_hotel_must_fix(self):
        """An UNKNOWN verdict's whole value is telling somebody which evidence to go and get."""
        evidence = [
            EvidenceLine("reservation.status", Value.known("checked_out")),
            EvidenceLine("folio.balance_due", Value.unknown("the folio call failed", risk="R1")),
        ]
        v = Verdict(Outcome.UNKNOWN, "balance not established", evidence=evidence)
        assert v.unknown_fields == ("folio.balance_due",)

    def test_evidence_is_immutable_once_the_verdict_exists(self):
        """A stored FAIL with the number edited afterwards is an accusation without a receipt."""
        lines = _evidence()
        v = Verdict(Outcome.FAIL, "a reason", evidence=lines)
        lines.append(EvidenceLine("injected", Value.known("x")))
        assert len(v.evidence) == 1
        with pytest.raises((AttributeError, TypeError)):
            v.outcome = Outcome.PASS

    def test_repr_reads_as_a_sentence(self):
        v = Verdict(Outcome.FAIL, "balance is 812.5 ILS", evidence=_evidence(),
                    record_id="007003199")
        assert "FAIL" in repr(v) and "007003199" in repr(v)
