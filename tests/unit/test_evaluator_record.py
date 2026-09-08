# -*- coding: utf-8 -*-
"""
Verdicts: the order of the clauses, three-valued logic, and purity.

Two things here decide whether the product is honest.

THE UNKNOWN PRECEDENCE TESTS. Under `all`, one predicate that definitely fails is a complete
answer - an outstanding balance is a violation whether or not some unrelated field was missing.
The REVERSE must never happen: a would-be pass outranking a missing field. Both directions are
tested, and the second is the one that keeps the system honest.

THE PURITY TEST. The evaluator is a function of (IR, evidence) and nothing else, asserted by
breaking `open` and `socket` underneath it. That is what makes a stored verdict defensible six
months later rather than an anecdote about a Tuesday.
"""
import builtins
import socket

import pytest

from hotelcontrols.evaluator import evaluate_record
from hotelcontrols.evidence import Bundle
from hotelcontrols.kernel import Money, NotAuditable, Outcome, Value
from hotelcontrols.spec import ControlIR


def ir(scope=(), exceptions=(), mode="all", predicates=(), evidence=()):
    return ControlIR({
        "control_id": "test_control", "entity": "reservation",
        "scope": list(scope), "exceptions": list(exceptions),
        "assertion": {"mode": mode, "predicates": list(predicates)},
        "required_evidence": [{"field": f, "source": "pms"} for f in evidence],
    })


def bundle(fields, joins=None):
    return Bundle("reservation", "007003199", fields, {}, joins or {})


BALANCE_ZERO = {"folio.balance_due": Value.known(Money.parse("0", "ILS"))}
BALANCE_OWED = {"folio.balance_due": Value.known(Money.parse("812.5", "ILS"))}
BALANCE_NONE = {"folio.balance_due": Value.unknown("the folio call failed", risk="R1")}
LTE_ZERO = [{"field": "folio.balance_due", "operator": "lte", "value": 0}]


class TestTheFourOutcomes:
    def test_a_settled_folio_passes(self):
        assert evaluate_record(ir(predicates=LTE_ZERO),
                               bundle(BALANCE_ZERO)).outcome is Outcome.PASS

    def test_an_outstanding_balance_fails(self):
        assert evaluate_record(ir(predicates=LTE_ZERO),
                               bundle(BALANCE_OWED)).outcome is Outcome.FAIL

    def test_a_balance_that_was_never_established_is_unknown_never_fail(self):
        """The single most important line in the product. A folio nobody could fetch is not a
        folio with money owing, and reporting it as one would send a hotel chasing a guest who
        paid."""
        verdict = evaluate_record(ir(predicates=LTE_ZERO), bundle(BALANCE_NONE))
        assert verdict.outcome is Outcome.UNKNOWN
        assert "folio call failed" in verdict.reason

    def test_a_record_outside_scope_is_excluded_not_passed(self):
        """EXCLUDED is not PASS. A run over a hundred records where ninety were out of scope
        must not report '90 passed' - a compliance number made of records nobody checked."""
        verdict = evaluate_record(
            ir(scope=[{"field": "reservation.status", "operator": "equals",
                       "value": "checked_out"}], predicates=LTE_ZERO),
            bundle(dict(BALANCE_ZERO, **{"reservation.status": Value.known("confirmed")})))
        assert verdict.outcome is Outcome.EXCLUDED


class TestClauseOrder:
    def test_scope_is_evaluated_before_the_assertion(self):
        """An out-of-scope record with a violating balance is EXCLUDED, not FAIL. The control
        has no opinion about records it does not apply to."""
        verdict = evaluate_record(
            ir(scope=[{"field": "reservation.status", "operator": "equals",
                       "value": "checked_out"}], predicates=LTE_ZERO),
            bundle(dict(BALANCE_OWED, **{"reservation.status": Value.known("cancelled")})))
        assert verdict.outcome is Outcome.EXCLUDED

    def test_an_unestablished_scope_is_unknown_not_excluded(self):
        """A control that cannot tell whether it applies has not excluded anything. One
        reservation in five carries a status this engine refuses to name (A5), so this path
        runs constantly on real data."""
        verdict = evaluate_record(
            ir(scope=[{"field": "reservation.status", "operator": "equals",
                       "value": "checked_out"}], predicates=LTE_ZERO),
            bundle(dict(BALANCE_OWED, **{
                "reservation.status": Value.unknown("'OK4' is not in this property's status "
                                                    "map", risk="A5")})))
        assert verdict.outcome is Outcome.UNKNOWN
        assert "whether this control applies" in verdict.reason

    def test_exceptions_are_evaluated_after_scope_and_exclude(self):
        verdict = evaluate_record(
            ir(exceptions=[{"field": "reservation.is_group", "operator": "equals",
                            "value": True}], predicates=LTE_ZERO),
            bundle(dict(BALANCE_OWED, **{"reservation.is_group": Value.known(True)})))
        assert verdict.outcome is Outcome.EXCLUDED
        assert "an exception applies" in verdict.reason

    def test_an_unestablished_exception_is_unknown_not_a_pass(self):
        """Most hotel controls read 'X must not happen UNLESS APPROVED', and no PMS records the
        approval. Turning an unverifiable exception into a pass is open question 1.1, and until
        somebody decides otherwise the answer is UNKNOWN."""
        verdict = evaluate_record(
            ir(exceptions=[{"field": "reservation.is_group", "operator": "equals",
                            "value": True}], predicates=LTE_ZERO),
            bundle(dict(BALANCE_ZERO, **{
                "reservation.is_group": Value.unknown("not exposed by this provider")})))
        assert verdict.outcome is Outcome.UNKNOWN


class TestKleeneLogic:
    def test_under_all_a_definite_failure_outranks_an_unrelated_gap(self):
        """An outstanding balance is a violation whether or not some other field was missing.
        Calling this UNKNOWN would hide a real violation behind an unrelated gap."""
        verdict = evaluate_record(
            ir(mode="all", predicates=[
                {"field": "folio.balance_due", "operator": "lte", "value": 0},
                {"field": "reservation.channel", "operator": "exists"}]),
            bundle(dict(BALANCE_OWED, **{
                "reservation.channel": Value.unknown("absent from the response")})))
        assert verdict.outcome is Outcome.FAIL

    def test_under_all_a_would_be_pass_never_outranks_a_missing_field(self):
        """THE test. The reverse of the one above, and the direction that must never happen:
        every predicate we could check passes, one could not be checked, and the answer is
        UNKNOWN rather than PASS."""
        verdict = evaluate_record(
            ir(mode="all", predicates=[
                {"field": "folio.balance_due", "operator": "lte", "value": 0},
                {"field": "reservation.channel", "operator": "exists"}]),
            bundle(dict(BALANCE_ZERO, **{
                "reservation.channel": Value.unknown("absent from the response")})))
        assert verdict.outcome is Outcome.UNKNOWN

    def test_mode_none_fails_when_any_predicate_holds(self):
        verdict = evaluate_record(
            ir(mode="none", predicates=[{"field": "x", "operator": "exists"}]),
            bundle({"x": Value.known("something")}))
        assert verdict.outcome is Outcome.FAIL

    def test_mode_none_passes_when_none_hold(self):
        verdict = evaluate_record(
            ir(mode="none", predicates=[{"field": "x", "operator": "exists"}]),
            bundle({"x": Value.known(False)}))
        assert verdict.outcome is Outcome.PASS

    def test_mode_any_passes_on_the_first_satisfied_predicate(self):
        verdict = evaluate_record(
            ir(mode="any", predicates=[
                {"field": "a", "operator": "exists"},
                {"field": "b", "operator": "exists"}]),
            bundle({"a": Value.unknown("gap"), "b": Value.known("present")}))
        assert verdict.outcome is Outcome.PASS

    def test_an_aggregate_assertion_at_record_level_says_which_question_it_is(self):
        verdict = evaluate_record(
            ir(mode="aggregate", predicates=[
                {"field": "reservation.id", "operator": "count_lte", "value": 1}]),
            bundle({"reservation.id": Value.known("007003199")}))
        assert verdict.outcome is Outcome.UNKNOWN
        assert "group of records" in verdict.reason


class TestEveryVerdictShowsItsWorking:
    def test_a_verdict_carries_an_evidence_table(self):
        verdict = evaluate_record(ir(predicates=LTE_ZERO), bundle(BALANCE_OWED))
        assert verdict.evidence
        assert verdict.evidence[0].field == "folio.balance_due"
        assert "812.5 ILS" in str(verdict.evidence[0].value)

    def test_the_decisive_field_comes_first(self):
        """A reader should not have to hunt for the number the verdict turned on."""
        verdict = evaluate_record(
            ir(mode="all", predicates=[
                {"field": "reservation.channel", "operator": "exists"},
                {"field": "folio.balance_due", "operator": "lte", "value": 0}]),
            bundle(dict(BALANCE_OWED, **{"reservation.channel": Value.known("Qwerty")})))
        assert verdict.evidence[0].field == "folio.balance_due"

    def test_declared_context_appears_even_when_no_predicate_used_it(self):
        """reservation.currency is declared required evidence precisely so the currency split
        (R9) is visible next to the answer, though nothing compares against it."""
        verdict = evaluate_record(
            ir(predicates=LTE_ZERO,
               evidence=["folio.balance_due", "reservation.currency"]),
            bundle(dict(BALANCE_ZERO, **{"reservation.currency": Value.known("USD")})))
        assert "reservation.currency" in [line.field for line in verdict.evidence]

    def test_a_verdict_can_never_be_built_without_evidence(self):
        """Structural, not a convention somebody has to remember on the day they add the
        twelfth control."""
        with pytest.raises(NotAuditable):
            evaluate_record(ir(predicates=LTE_ZERO), bundle({}))


class TestPurity:
    def test_the_evaluator_performs_no_io(self, monkeypatch):
        """Asserted by breaking the world underneath it, not assumed. A verdict that depended
        on a file or a socket would not be reproducible, and reproducibility is what separates
        an audit trail from an anecdote."""
        def forbidden(*args, **kwargs):
            raise AssertionError("the evaluator performed I/O")

        monkeypatch.setattr(builtins, "open", forbidden)
        monkeypatch.setattr(socket, "socket", forbidden)
        assert evaluate_record(ir(predicates=LTE_ZERO),
                               bundle(BALANCE_ZERO)).outcome is Outcome.PASS

    def test_the_same_bundle_always_yields_the_same_verdict(self):
        rule, evidence = ir(predicates=LTE_ZERO), bundle(BALANCE_OWED)
        first = evaluate_record(rule, evidence)
        for _ in range(5):
            again = evaluate_record(rule, evidence)
            assert (again.outcome, again.reason) == (first.outcome, first.reason)

    def test_the_evaluator_reads_no_clock(self, monkeypatch):
        """A control's temporal question is resolved into its population query, through the
        property's clock. By the time evidence reaches here, 'today' is already decided."""
        import datetime

        class Frozen(datetime.date):
            @classmethod
            def today(cls):
                raise AssertionError("the evaluator read the wall clock")

        monkeypatch.setattr(datetime, "date", Frozen)
        assert evaluate_record(ir(predicates=LTE_ZERO), bundle(BALANCE_ZERO))
