# -*- coding: utf-8 -*-
"""
Coverage - did this run conclude anything at all?

Review finding F5, and the most valuable thing in this slice. A run reports four counts.
Nothing in v1 distinguished

    "28 rooms checked, all compliant"        from      "28 rooms, none of which was checked"

and the second renders as four tiles with a zero under FAIL - a clean bill of health for a
control that never looked. v1's own context document named this danger and the engine shipped
without a guard against it.

It is not hypothetical here. `ooo_room_protection` excludes all 28 rooms because no room in this
property has ever had a closed-date window set. That is the CORRECT answer, and it currently
looks like success.
"""
from hotelcontrols.kernel import EvidenceLine, Outcome, Value, Verdict
from hotelcontrols.runner import coverage_of


def verdict(outcome, reason="a reason"):
    return Verdict(outcome, reason, [EvidenceLine("f", Value.known("v"))])


class TestConcluded:
    def test_only_pass_and_fail_count_as_conclusions(self):
        coverage = coverage_of([verdict(Outcome.PASS), verdict(Outcome.FAIL),
                                verdict(Outcome.UNKNOWN), verdict(Outcome.EXCLUDED)])
        assert coverage.evaluated == 2
        assert coverage.total == 4
        assert coverage.concluded is True

    def test_a_run_of_only_exclusions_concluded_nothing(self):
        """The `ooo_room_protection` shape: every record correctly out of scope."""
        coverage = coverage_of([verdict(Outcome.EXCLUDED) for _ in range(28)])
        assert coverage.concluded is False
        assert "has not looked" in coverage.headline

    def test_a_run_of_only_unknowns_concluded_nothing(self):
        coverage = coverage_of([verdict(Outcome.UNKNOWN) for _ in range(40)])
        assert coverage.concluded is False

    def test_the_headline_never_reads_as_success_when_nothing_was_concluded(self):
        """This sentence replaces the count tiles. It must not be possible to read it as good
        news - 'has not found the property compliant; it has not looked'."""
        headline = coverage_of([verdict(Outcome.EXCLUDED) for _ in range(28)]).headline
        assert "no conclusion" in headline
        assert "compliant" in headline and "not" in headline

    def test_an_empty_population_says_so_rather_than_claiming_coverage(self):
        coverage = coverage_of([])
        assert coverage.concluded is False
        assert "nothing to check" in coverage.headline

    def test_partial_coverage_is_reported_as_partial(self):
        coverage = coverage_of([verdict(Outcome.PASS)] + [verdict(Outcome.EXCLUDED)] * 9)
        assert coverage.concluded is True
        assert "1 of 10" in coverage.headline


class TestTheDominantReason:
    def test_an_unknown_reason_outranks_an_exclusion(self):
        """The precedence that makes this field useful.

        When a run concludes nothing there are two different situations: every record correctly
        out of scope (nothing to fix), or records the control applied to and could not answer
        (THAT is the gap). Reporting the commonest reason overall buries the second under the
        first - 71 of 111 stays are cancelled, so 'does not apply: status is cancelled' wins the
        popularity contest while the records that mattered went unanswered.
        """
        verdicts = [verdict(Outcome.EXCLUDED, "does not apply: cancelled")] * 71 + \
                   [verdict(Outcome.UNKNOWN, "the room's capacity is unconfigured")] * 40
        assert "capacity is unconfigured" in coverage_of(verdicts).dominant_reason

    def test_the_full_distribution_is_reported_not_only_the_winner(self):
        """A single reason is often the least informative one. A reader needs to see both that
        most records were out of scope AND what happened to the rest."""
        verdicts = [verdict(Outcome.EXCLUDED, "cancelled")] * 71 + \
                   [verdict(Outcome.EXCLUDED, "no closed-date window")] * 40
        reasons = dict(coverage_of(verdicts).reasons)
        assert reasons["cancelled"] == 71
        assert reasons["no closed-date window"] == 40

    def test_a_concluding_run_needs_no_dominant_reason(self):
        assert coverage_of([verdict(Outcome.PASS)]).dominant_reason is None

    def test_conclusions_are_left_out_of_the_distribution(self):
        """The distribution answers "what stopped this run concluding", so a PASS has no place
        in it."""
        coverage = coverage_of([verdict(Outcome.PASS, "fine"),
                                verdict(Outcome.UNKNOWN, "a gap")])
        assert dict(coverage.reasons) == {"a gap": 1}
