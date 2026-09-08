# -*- coding: utf-8 -*-
"""
Verdicts on real records, end to end: provider -> evidence -> evaluator.

Every record here was returned by the vendor's own system. Fixtures are pseudonymised, so guest
names are invented - but reservation ids, statuses, dates, amounts and currencies are exactly as
captured, and every verdict below is about real vendor behaviour.

The slice-4 gate is that ALL FOUR OUTCOMES are reachable from captured evidence. v1 spent a week
unable to reach PASS or FAIL at all, drove both from hand-written fixtures, and recorded the
success criterion as unmet until seven more sandbox calls found the checked-out reservations.
Nothing in this repository is invented.
"""
from collections import Counter

import pytest

from hotelcontrols.evaluator import evaluate_record
from hotelcontrols.evidence import CallBudget, gather
from hotelcontrols.kernel import Outcome
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import TenantConfig, available, load


def run(control_id, capture="sandbox2026", as_of="2026-07-08T09:00"):
    """The whole stack, offline: fetch, gather, judge."""
    tenant = TenantConfig.load("sandbox")
    source = FrozenSource(capture)
    adapter = MiniHotelAdapter(tenant, source)
    ir = load(control_id)
    evidence = gather(ir, adapter, tenant, FixedClock.at(as_of, tenant.timezone),
                      CallBudget(400))
    verdicts = [evaluate_record(ir, bundle, tenant.settings) for bundle in evidence]
    return verdicts, evidence, source


def outcomes(verdicts):
    return Counter(v.outcome for v in verdicts)


class TestTheCheckoutControls:
    """Decision D8, demonstrated on the record that motivated it."""

    def test_a_settled_folio_passes_both_controls(self):
        """Reservation 007004351 departed at 0 ILS. It owes nothing and is owed nothing."""
        for control_id in ("checkout_money_owed", "checkout_unrefunded_credit"):
            verdicts, _, _ = run(control_id)
            settled = [v for v in verdicts if v.record_id == "007004351"]
            assert settled and settled[0].outcome is Outcome.PASS, control_id

    def test_the_overpaid_folio_fails_only_the_credit_control(self):
        """THE test for decision D8.

        Reservation 007004348 departed at -490.75 ILS: the guest overpaid and the hotel owes a
        refund. v1 reported that as an outstanding balance - correct as specified, and not what
        a finance team means by the phrase. Split in two, it lands in the right queue.
        """
        owed, _, _ = run("checkout_money_owed")
        credit, _, _ = run("checkout_unrefunded_credit")
        by_id = {v.record_id: v for v in owed}
        assert by_id["007004348"].outcome is Outcome.PASS, \
            "an overpaid guest owes the hotel nothing"
        by_id = {v.record_id: v for v in credit}
        assert by_id["007004348"].outcome is Outcome.FAIL, \
            "an unrefunded credit is a liability this control exists to find"
        assert "-490.75 ILS" in by_id["007004348"].reason

    def test_a_folio_that_was_never_captured_is_unknown_not_a_pass(self):
        """One call per reservation is the cost this control is built around (R1) and the
        sandbox is someone else's server (R8), so only three folios were taken. The rest must
        be UNKNOWN - the rule that keeps the whole system honest."""
        verdicts, _, _ = run("checkout_money_owed", as_of="2026-07-10T09:00")
        unknown = [v for v in verdicts if v.outcome is Outcome.UNKNOWN]
        assert unknown, "10 July has a checkout whose folio was deliberately not captured"
        assert "could not be fetched" in unknown[0].reason

    def test_the_call_count_is_one_plus_n(self):
        """R1, asserted end to end and not merely at the evidence layer."""
        verdicts, evidence, source = run("checkout_money_owed")
        assert len(source.calls) == 1 + len(verdicts)


class TestTheControlsV1CouldNotAnswer:
    """Three of these returned 111 UNKNOWN out of 111 records in v1, for want of a join."""

    @pytest.mark.parametrize("control_id", [
        "room_assignment_type_validity", "inactive_room_future_stay"])
    def test_they_now_reach_real_verdicts(self, control_id):
        verdicts, _, _ = run(control_id)
        tally = outcomes(verdicts)
        assert tally[Outcome.PASS] > 0, (
            "%s reaches no conclusion about any record: %s" % (control_id, dict(tally)))

    def test_a_stay_passes_only_when_its_room_and_type_both_check_out(self):
        """Control 1a-1c, all three halves: the room exists, its type is defined, and the
        reservation agrees with it."""
        verdicts, _, _ = run("room_assignment_type_validity")
        passing = [v for v in verdicts if v.outcome is Outcome.PASS]
        assert passing
        for verdict in passing:
            assert "resolves" in verdict.reason or "satisfies" in verdict.reason


class TestAllFourOutcomesFromCapturedEvidence:
    """The slice-4 gate."""

    def test_every_outcome_is_reachable_without_a_single_invented_record(self):
        seen = Counter()
        for control_id in available():
            for as_of in ("2026-07-08T09:00", "2026-07-10T09:00"):
                verdicts, _, source = run(control_id, as_of=as_of)
                assert source.is_synthetic is False
                seen.update(outcomes(verdicts))
        for outcome in (Outcome.PASS, Outcome.FAIL, Outcome.UNKNOWN, Outcome.EXCLUDED):
            assert seen[outcome] > 0, "%s is unreachable from captured evidence: %s" % (
                outcome, dict(seen))

    def test_every_verdict_carries_the_fields_that_produced_it(self):
        """Success criterion 3. An unexplained verdict is not auditable, and audit is the
        product."""
        for control_id in available():
            verdicts, _, _ = run(control_id)
            for verdict in verdicts:
                assert verdict.evidence, "%s %s" % (control_id, verdict.record_id)
                for line in verdict.evidence:
                    assert line.value is not None
                    assert line.source or not line.value.is_known

    def test_no_control_raises_on_any_record(self):
        for control_id in available():
            verdicts, _, _ = run(control_id)
            assert isinstance(verdicts, list)


class TestHonestyOfTheAnswers:
    def test_a_control_whose_mechanism_was_never_observed_excludes_rather_than_passes(self):
        """Open question 2.4. All 28 rooms return an empty closed-date window, so the
        out-of-service mechanism has never been seen working on this property.

        The right answer is to EXCLUDE every room - the control does not apply where no window
        is set - and NOT to report 28 passes. v1's own context document warned that these
        controls could 'silently pass everything, reporting a clean bill of health while
        checking nothing'; excluding is what stops that, and slice 6's coverage verdict is what
        makes it visible.
        """
        verdicts, _, _ = run("ooo_room_protection")
        tally = outcomes(verdicts)
        assert tally[Outcome.PASS] == 0
        assert tally[Outcome.EXCLUDED] == len(verdicts)

    def test_a_control_needing_evidence_this_provider_cannot_supply_is_unknown(self):
        """R13 / open question 1.6. A reservation's rate code and the provider's price-list
        code are different key spaces, so control 9 cannot be answered here at all - and says
        so, which is the 'connect this to enable the control' path rather than a wrong verdict.
        """
        verdicts, _, _ = run("rate_room_category_consistency")
        unknown = [v for v in verdicts if v.outcome is Outcome.UNKNOWN]
        assert unknown
        assert any("property" in v.reason for v in unknown)

    def test_an_unnameable_status_never_decides_whether_a_control_applies(self):
        """A5. 44 of the 217 distinct reservations we have ever seen carry a status documented
        nowhere. Those must reach UNKNOWN rather than being quietly included or excluded."""
        verdicts, _, _ = run("required_reservation_fields")
        assert outcomes(verdicts)[Outcome.UNKNOWN] > 0

    def test_an_aggregate_control_declines_at_record_level_rather_than_guessing(self):
        """Duplicate detection is a question about a GROUP. Answering it one record at a time
        would mean answering a different question; the population evaluator lands in slice 5."""
        verdicts, _, _ = run("duplicate_channel_reservation")
        unknown = [v for v in verdicts if v.outcome is Outcome.UNKNOWN]
        assert unknown

        # Two distinct reasons, and both are correct. A record whose status this property
        # cannot name (A5) is UNKNOWN before the assertion is ever reached - the control cannot
        # tell whether it applies. The rest reach the assertion and decline it, because a
        # duplicate is a question about a GROUP.
        declined = [v for v in unknown if "group of records" in v.reason]
        scoped_out = [v for v in unknown if "whether this control applies" in v.reason]
        assert declined, "records that reach the assertion must decline it by name"
        assert len(declined) + len(scoped_out) == len(unknown), (
            "an UNKNOWN here should be one of exactly those two reasons: %s"
            % {v.reason[:60] for v in unknown})
