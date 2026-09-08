# -*- coding: utf-8 -*-
"""
Aggregate controls, end to end, on real records.

Two controls in the shipped set ask questions about a GROUP: duplicate channel reservations
(control 14) and resource occupancy consistency (control 20). v1 answered neither - it declared
the operators and implemented none of them (finding F2).

THE PAIR THIS FILE EXISTS FOR
-----------------------------
The 2024 capture contains a confirmed instance of R7: portal id `test0000000N1` is shared by
reservation 007003206 (status CL, cancelled) and 007003207 (status OK4). v1 documented this by
hand as the cancel-and-recreate pattern an OTA modification produces.

The engine's answer is EXCLUDED for the cancelled half and UNKNOWN for the other - because
`OK4` appears on 32 reservations and is documented nowhere, so nobody can say whether it means
active. That is open question 1.3, and it resolves on one sentence from the vendor (question
2.1). What the engine must NOT do is guess, in either direction: calling it a duplicate accuses
a hotel of a defect that is probably just a modification, and calling it clean asserts something
about a status code we cannot read.
"""
from collections import Counter

import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import CallBudget, gather
from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import TenantConfig, available, load


def run(control_id, capture="sandbox2026", as_of="2026-07-08T09:00"):
    tenant = TenantConfig.load("sandbox")
    source = FrozenSource(capture)
    adapter = MiniHotelAdapter(tenant, source)
    ir = load(control_id)
    evidence = gather(ir, adapter, tenant, FixedClock.at(as_of, tenant.timezone),
                      CallBudget(400))
    return evaluate_population(ir, evidence.bundles, tenant.settings), evidence, source


class TestTheKnownDuplicatePair:
    def test_the_cancelled_half_is_excluded_not_reported(self):
        """R7. An OTA modification is a cancel plus a recreate reusing the same portal id.
        Counting the cancelled half would report every modified booking in the property."""
        verdicts, _, _ = run("duplicate_channel_reservation", capture="sandbox2024",
                             as_of="2024-09-01T09:00")
        cancelled = next(v for v in verdicts if v.record_id == "007003206")
        assert cancelled.outcome is Outcome.EXCLUDED
        assert "cancelled" in cancelled.reason

    def test_the_surviving_half_is_unknown_because_nobody_can_read_its_status(self):
        """Open questions 1.3 and 2.1, arriving as a verdict.

        `OK4` appears on 32 reservations across the captures and is documented nowhere. Whether
        this reservation is active decides whether the pair is a duplicate at all - so the
        engine says it cannot tell, and names the code it could not read.
        """
        verdicts, _, _ = run("duplicate_channel_reservation", capture="sandbox2024",
                             as_of="2024-09-01T09:00")
        survivor = next(v for v in verdicts if v.record_id == "007003207")
        assert survivor.outcome is Outcome.UNKNOWN
        assert "OK4" in survivor.reason

    def test_the_engine_never_guesses_in_either_direction(self):
        """Calling it a duplicate accuses a hotel of a defect that is probably a modification.
        Calling it clean asserts something about a status code we cannot read."""
        verdicts, _, _ = run("duplicate_channel_reservation", capture="sandbox2024",
                             as_of="2024-09-01T09:00")
        pair = [v for v in verdicts if v.record_id in ("007003206", "007003207")]
        assert len(pair) == 2
        assert not any(v.outcome is Outcome.FAIL for v in pair)
        assert not any(v.outcome is Outcome.PASS for v in pair)


class TestAggregateControlsNowAnswer:
    @pytest.mark.parametrize("control_id", [
        "duplicate_channel_reservation", "resource_occupancy_consistency"])
    def test_both_reach_real_conclusions(self, control_id):
        """The slice gate. v1 reached zero conclusions on either."""
        verdicts, _, _ = run(control_id)
        answered = [v for v in verdicts if v.is_answer]
        assert answered, "%s reaches no conclusion about any record" % control_id

    def test_no_fail_is_manufactured_where_the_data_holds_none(self):
        """Honesty check, and a deliberate non-assertion.

        Neither control reaches FAIL on this capture, because the property genuinely has no
        active duplicate and no double-booked room. Inventing a fixture to produce a nicer
        demo is exactly what v1 did with fixtures/synthetic/ and exactly what this repository
        does not do - every record here came from the vendor's own system.
        """
        for control_id in ("duplicate_channel_reservation", "resource_occupancy_consistency"):
            verdicts, _, source = run(control_id)
            assert source.is_synthetic is False
            assert Counter(v.outcome for v in verdicts)[Outcome.FAIL] == 0

    def test_the_two_segments_of_one_reservation_do_not_conflict_with_each_other(self):
        """Reservation 007003204 holds room 303 twice - 10-11 and 15-16 August. v1 read that
        repetition as the reason occupancy could not be cut into records at all; it is the
        ordinary case, and a reservation cannot double-book itself."""
        verdicts, _, _ = run("resource_occupancy_consistency")
        assert {v.record_id for v in verdicts} == {"007003204"}
        assert all(v.outcome is Outcome.PASS for v in verdicts)

    def test_a_group_verdict_names_the_other_records_in_its_group(self):
        """The slice gate. An accusation that does not say who else is involved cannot be
        acted on - somebody has to open both reservations."""
        verdicts, _, _ = run("duplicate_channel_reservation")
        grouped = [v for v in verdicts
                   if any(line.field == "other records in this group" for line in v.evidence)]
        for verdict in grouped:
            names = next(line for line in verdict.evidence
                         if line.field == "other records in this group")
            assert names.value.is_known and names.value.payload


class TestTheDirectBookingGuard:
    def test_direct_bookings_are_excluded_rather_than_grouped_on_a_shared_absence(self):
        """R7's other half. 7 of 11 sandbox bookings are direct and carry no portal id at all.
        Grouping them on a shared absence would produce one enormous false group in which every
        direct booking is a duplicate of every other."""
        verdicts, _, _ = run("duplicate_channel_reservation", capture="sandbox2024",
                             as_of="2024-09-01T09:00")
        direct = [v for v in verdicts if "not applicable" in v.reason]
        assert len(direct) == 5, "the 2024 capture holds five direct bookings"
        for verdict in direct:
            assert verdict.outcome is Outcome.EXCLUDED

        # The control guards this TWICE: `channel_confirmation_id exists` in scope, and a
        # `not_exists` exception. In practice scope fires first, so the exception is dead - but
        # it is kept deliberately, because the day somebody relaxes the scope clause the
        # exception is what still stops every direct booking becoming a duplicate of every
        # other one. What matters is the property, not which clause enforces it.
        assert all("does not apply here" in v.reason or "exception applies" in v.reason
                   for v in direct)

    def test_no_group_ever_forms_around_a_missing_key(self):
        for capture, as_of in (("sandbox2024", "2024-09-01T09:00"),
                               ("sandbox2026", "2026-07-08T09:00")):
            verdicts, _, _ = run("duplicate_channel_reservation", capture, as_of)
            for verdict in verdicts:
                if verdict.outcome is Outcome.FAIL:
                    assert "not applicable" not in verdict.reason


class TestEveryControlStillRuns:
    @pytest.mark.parametrize("control_id", sorted(available()))
    def test_the_single_entry_point_handles_both_shapes(self, control_id):
        """A runner calls `evaluate_population` for everything; it must hand a record-level
        control straight through without the caller knowing which shape it is."""
        verdicts, evidence, _ = run(control_id)
        assert len(verdicts) == len(evidence.bundles)
        for verdict in verdicts:
            assert verdict.evidence
