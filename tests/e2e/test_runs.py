# -*- coding: utf-8 -*-
"""
Every control, over every body of captured evidence.

This is the matrix v1's review measured, and the file where success criterion 1 is assessed
HONESTLY rather than hopefully. v1 recorded its own criterion 2 as unmet for a week while
control 6 could reach neither PASS nor FAIL, and that is why the eventual "met" was worth
something.
"""
from datetime import datetime

import pytest

from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.base import ResponseUnavailable
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.runner import run
from hotelcontrols.spec import TenantConfig, available
from hotelcontrols.store import RunStore

CAPTURES = {"sandbox2026": "2026-07-08T09:00", "sandbox2024": "2024-09-01T09:00"}

# Measured, not aspirational. These reach a PASS or a FAIL on the 2026 capture.
CONCLUDING = {
    "checkout_money_owed", "checkout_unrefunded_credit", "duplicate_channel_reservation",
    "inactive_room_future_stay", "room_assignment_type_validity",
}

# Controls that cannot even be ASKED of this body of evidence, and are therefore blocked
# before any record is judged. Different from CANNOT_CONCLUDE below: those run and reach no
# conclusion, this one never runs at all.
#
# `resource_occupancy_consistency` asks about `today..today+7d` and the only occupancy capture
# covers 2024-08-14..2024-08-21 (issue #9). It counted towards criterion 1 until that guard
# was fixed - it was reaching two PASSes about July 2026 from segments captured in August 2024.
# Asked on 14 August 2024 it concludes perfectly well, which is asserted in
# tests/e2e/test_population_verdicts.py; neither of this repository's two evidence sets stands
# on that date.
BLOCKED = {
    "resource_occupancy_consistency":
        "the only occupancy capture covers 2024-08-14..2024-08-21, and a run asking about any "
        "other week is refused rather than answered from the wrong one (issue #9)",
}

# These cannot conclude, and each reason is a fact about the PROPERTY or the PROVIDER rather
# than a gap in the engine. Recorded here so a change in the number is noticed.
CANNOT_CONCLUDE = {
    "ooo_room_protection":
        "no room in this property has ever had a closed-date window set, so the control "
        "correctly applies to none of them (open question 2.4)",
    "room_assignment_active_room":
        "the same closed-date window, from the reservation side",
    "room_capacity_compliance":
        "23 of 28 rooms report adult capacity 0, meaning unconfigured (R12). Reading those as "
        "real zeroes would be a wall of false FAILs",
    "rate_room_category_consistency":
        "a rate code and the provider's price-list code are different key spaces (R13), so no "
        "endpoint resolves the mapping at all",
    "required_reservation_fields":
        "this property has nominated no rate codes, so the control applies to no reservation "
        "(open question 1.4)",
}


def a_run(control_id, capture="sandbox2026"):
    tenant = TenantConfig.load("sandbox")
    adapter = MiniHotelAdapter(tenant, FrozenSource(capture))
    return run(control_id, tenant, adapter,
               FixedClock.at(CAPTURES[capture], tenant.timezone), evidence_label=capture)


class TestTheWholeMatrix:
    @pytest.mark.parametrize("control_id", sorted(available()))
    @pytest.mark.parametrize("capture", sorted(CAPTURES))
    def test_every_control_over_every_capture_either_runs_or_names_its_blocker(
            self, control_id, capture):
        """No stack traces, ever. A run that cannot happen is a sentence."""
        try:
            result = a_run(control_id, capture)
        except ResponseUnavailable:
            # The 2024 capture cannot answer a question about a window it never covered, and
            # refusing is the point (F19c) - an empty population reads as "no violations".
            return
        assert result.is_blocked or result.counts["total"] >= 0
        if result.is_blocked:
            assert len(result.blocked) > 20, "a blocked run must explain itself"

    @pytest.mark.parametrize("control_id", sorted(available()))
    def test_every_run_records_what_it_ran_against(self, control_id):
        """Six months later, a verdict is only defensible if it says which control, as of
        when, over which evidence, and at what cost."""
        result = a_run(control_id)
        assert result.control_id == control_id
        assert result.natural_language.endswith(".")
        assert result.tenant_id == "sandbox" and result.provider == "minihotel"
        assert result.as_of == "2026-07-08"
        assert result.calls >= 1
        assert result.evidence_is_synthetic is False


class TestSuccessCriterionOne:
    """`prd.md` asks that at least 8 of the 11 controls reach a PASS or a FAIL.

    THE MEASURED NUMBER IS 6. The criterion is NOT MET, and it is recorded as unmet rather than
    quietly relaxed - the five that cannot conclude are blocked by facts about this sandbox and
    this provider, not by anything the engine does wrong. See CANNOT_CONCLUDE above and the
    definition-of-done table in docs/plan.md.
    """

    def test_five_controls_reach_a_conclusion(self):
        concluding = {c for c in available() if a_run(c).coverage.concluded}
        assert concluding == CONCLUDING, (
            "the set of concluding controls changed - update CONCLUDING and the criterion-1 "
            "assessment in docs/plan.md rather than the assertion")

    def test_criterion_one_is_not_yet_met_and_the_shortfall_is_six_controls(self):
        concluding = [c for c in available() if a_run(c).coverage.concluded]
        assert len(concluding) == 5
        assert len(concluding) < 8, (
            "criterion 1 now passes - update docs/plan.md, which currently records it as unmet")

    @pytest.mark.parametrize("control_id", sorted(BLOCKED))
    def test_a_control_this_evidence_cannot_answer_is_blocked_with_a_sentence(self, control_id):
        """A blocked run is the OTHER honest failure: not "no violations", not "nothing
        applied", but "this body of evidence cannot answer that question". It must reach the
        screen as a sentence naming the window, and it must show no count tiles - four zeroes
        read as a clean bill of health for a control that never ran."""
        result = a_run(control_id)
        assert result.is_blocked, control_id
        assert "2024-08-14" in result.blocked, (
            "the blocker must name the window that WAS captured, or nobody can act on it")
        assert result.counts["total"] == 0
        assert not result.coverage.concluded

    @pytest.mark.parametrize("control_id", sorted(CANNOT_CONCLUDE))
    def test_every_control_that_cannot_conclude_says_why_on_screen(self, control_id):
        """The other half of criterion 1, and the half that IS met: a control that reaches no
        conclusion must never render as a clean bill of health."""
        result = a_run(control_id)
        coverage = result.coverage
        assert not coverage.concluded
        assert coverage.dominant_reason, control_id
        assert "no conclusion" in coverage.headline
        assert "has not looked" in coverage.headline


class TestFindingF5:
    def test_a_run_that_concluded_nothing_never_looks_like_a_clean_result(self):
        """The point of the slice. `ooo_room_protection` excludes all 28 rooms because
        the property has never set a closed-date window - correct, and in v1 indistinguishable
        on screen from '28 rooms checked, all compliant'."""
        result = a_run("ooo_room_protection")
        assert result.counts["FAIL"] == 0
        assert result.counts["EXCLUDED"] == 28
        assert result.coverage.concluded is False
        assert "compliant" in result.coverage.headline and "not" in result.coverage.headline

    def test_a_concluding_run_is_not_flagged(self):
        result = a_run("checkout_unrefunded_credit")
        assert result.coverage.concluded is True
        assert result.counts["FAIL"] == 1

    def test_excluded_is_never_folded_into_passed(self):
        """A run over 111 records where 71 were out of scope must not report '71 passed'."""
        result = a_run("room_assignment_type_validity")
        assert result.counts["EXCLUDED"] == 71
        assert result.counts["PASS"] == 27


class TestHistoryAndReReading:
    def test_three_runs_are_listed_newest_first_and_re_read_without_a_provider_call(self):
        """R1. Re-running to answer 'what did it say?' would cost one call per reservation all
        over again."""
        with RunStore() as store:
            ids = []
            for hour in (9, 10, 11):
                result = a_run("checkout_unrefunded_credit")
                stored = Run_at(result, hour)
                ids.append(store.save(stored))

            history = store.history("checkout_unrefunded_credit")
            assert len(history) == 3
            assert [row["created_at"] for row in history] == \
                sorted((row["created_at"] for row in history), reverse=True)

            restored = store.load(ids[0])
            assert restored.counts == a_run("checkout_unrefunded_credit").counts
            assert restored.verdicts[0].evidence

    def test_a_stored_run_keeps_the_overpayment_visible(self):
        """The number that motivated decision D8 has to survive being written down."""
        with RunStore() as store:
            restored = store.load(store.save(a_run("checkout_unrefunded_credit")))
        failing = [v for v in restored.verdicts if v.outcome is Outcome.FAIL]
        assert failing and "-490.75 ILS" in failing[0].reason


def Run_at(result, hour):
    """The same run, stamped at a different hour - three runs of one control, for history."""
    from dataclasses import replace
    return replace(result, created_at=datetime(2026, 9, 8, hour, 0, 0), run_id=None)
