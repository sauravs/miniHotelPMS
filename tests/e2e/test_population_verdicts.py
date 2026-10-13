# -*- coding: utf-8 -*-
"""
Aggregate controls, end to end, on real records.

Two controls in the shipped set ask questions about a GROUP: duplicate channel reservations
(control 14) and resource occupancy consistency (control 20). v1 answered neither - it declared
the operators and implemented none of them (finding F2).

THE PAIRS THIS FILE EXISTS FOR
------------------------------
R7, the cancel-and-recreate pattern an OTA modification produces. v1 documented one instance by
hand in the 2024 capture: portal id `test0000000N1` shared by 007003206 (CL, cancelled) and
007003207 (OK4). Issue #71 retired that evidence - the duplicate control asks a CREATE window,
the 2024 capture recorded only an arrival window, and replay now refuses rather than answer
from it. The covering capture's 2026 arrival window holds SEVEN such pairs (TESTAIRBN1 and six
more, all created 2026-04-18, each a CL half and an OK4 half), so the guards are exercised on
those, asked by arrival - a question that capture did record. The control's own 30-day create
window holds no shared portal id at all, which is also stated below rather than hidden.

The engine's answer is EXCLUDED for the cancelled half and UNKNOWN for the other - because
`OK4` is documented nowhere, so nobody can say whether it means active. That is open question 1.3, and it resolves on one sentence from the vendor (question
2.1). What the engine must NOT do is guess, in either direction: calling it a duplicate accuses
a hotel of a defect that is probably just a modification, and calling it clean asserts something
about a status code we cannot read.
"""
import copy
from collections import Counter

import pytest

from hotelcontrols.evaluator import evaluate_population
from hotelcontrols.evidence import CallBudget, gather
from hotelcontrols.kernel import FixedClock, Outcome
from hotelcontrols.providers.base import ResponseUnavailable
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import ControlIR, TenantConfig, available, load


# Issue #71: the capture that recorded the questions these controls ask. sandbox2026 holds one
# departure window and now refuses an arrival or create question rather than answer from it.
COVER = "sandbox2026cover"

# The seven cancel-and-recreate pairs in the covering capture's arrival window: (CL, OK4).
PAIRS = [("007003917", "007003918"), ("007003919", "007003920"), ("007003921", "007003922"),
         ("007003923", "007003924"), ("007003925", "007003926"), ("007003927", "007003928"),
         ("007003929", "007003930")]


def by_arrival(control_id):
    """The control's own rule over a population asked by ARRIVAL - the window six controls ask
    and the covering capture recorded - instead of its own window. Only the population query
    changes; scope, exceptions and assertion are the shipped rule's."""
    raw = copy.deepcopy(load(control_id).raw)
    raw["population"]["provider_query"]["minihotel"]["filters"] = copy.deepcopy(
        load("room_assignment_type_validity").raw["population"]["provider_query"]["minihotel"]
        ["filters"])
    return ControlIR(raw)


def run(control_id, capture=COVER, as_of="2026-07-08T09:00"):
    tenant = TenantConfig.load("sandbox")
    source = FrozenSource(capture)
    adapter = MiniHotelAdapter(tenant, source)
    ir = control_id if isinstance(control_id, ControlIR) else load(control_id)
    evidence = gather(ir, adapter, tenant, FixedClock.at(as_of, tenant.timezone),
                      CallBudget(400))
    return evaluate_population(ir, evidence.bundles, tenant.settings), evidence, source


# The only clock at which the occupancy control can be asked anything at all.
#
# Its population query is `DateRange {from: today, to: today+7d}` and the one occupancy capture
# ever taken has the fingerprint 2024-08-14..2024-08-21, so a run standing on 14 August 2024
# asks exactly the question this capture answers. At any other date the frozen source refuses
# (issue #9) rather than replaying August 2024 as though it were the week that was asked about
# - which it did until that issue was fixed, reporting two PASSes about July 2026.
OCCUPANCY_WINDOW = {"capture": "sandbox2024", "as_of": "2024-08-14T09:00"}

# What each aggregate control has to be asked in order to be answerable at all.
ASKABLE = {"duplicate_channel_reservation": {},
           "resource_occupancy_consistency": OCCUPANCY_WINDOW}


class TestTheKnownDuplicatePairs:
    def test_the_cancelled_half_is_excluded_not_reported(self):
        """R7. An OTA modification is a cancel plus a recreate reusing the same portal id.
        Counting the cancelled half would report every modified booking in the property."""
        verdicts, _, _ = run(by_arrival("duplicate_channel_reservation"))
        found = {v.record_id: v for v in verdicts}
        for cancelled, _survivor in PAIRS:
            assert found[cancelled].outcome is Outcome.EXCLUDED, cancelled
            assert "cancelled" in found[cancelled].reason

    def test_the_surviving_half_is_unknown_because_nobody_can_read_its_status(self):
        """Open questions 1.3 and 2.1, arriving as a verdict.

        `OK4` is documented nowhere. Whether the surviving half is active decides whether the
        pair is a duplicate at all - so the engine says it cannot tell, and names the code.
        """
        verdicts, _, _ = run(by_arrival("duplicate_channel_reservation"))
        found = {v.record_id: v for v in verdicts}
        for _cancelled, survivor in PAIRS:
            assert found[survivor].outcome is Outcome.UNKNOWN, survivor
            assert "OK4" in found[survivor].reason

    def test_the_engine_never_guesses_in_either_direction(self):
        """Calling it a duplicate accuses a hotel of a defect that is probably a modification.
        Calling it clean asserts something about a status code we cannot read."""
        verdicts, _, _ = run(by_arrival("duplicate_channel_reservation"))
        pairs = {record for pair in PAIRS for record in pair}
        judged = [v for v in verdicts if v.record_id in pairs]
        assert len(judged) == 14
        assert not any(v.outcome in (Outcome.FAIL, Outcome.PASS) for v in judged)

    def test_the_controls_own_window_holds_no_pair_at_all(self):
        """Stated rather than hidden: asked its own question - created in the 30 days to
        2026-07-08 - the covering capture holds no shared portal id, which is why the pairs
        above are asked by arrival."""
        verdicts, _, _ = run("duplicate_channel_reservation")
        assert not {v.record_id for v in verdicts} & {r for pair in PAIRS for r in pair}

    def test_the_2024_capture_no_longer_answers_a_create_window_from_an_arrival_one(self):
        """Issue #71. The 2024 pair used to be judged from a capture that recorded an arrival
        window; the control asks a create window, so that answer was a different question's."""
        with pytest.raises(ResponseUnavailable, match="selected by ArrivalDate"):
            run("duplicate_channel_reservation", capture="sandbox2024",
                as_of="2024-09-01T09:00")


class TestAggregateControlsNowAnswer:
    @pytest.mark.parametrize("control_id", sorted(ASKABLE))
    def test_both_reach_real_conclusions(self, control_id):
        """The slice gate. v1 reached zero conclusions on either.

        Each is asked over the window its evidence actually covers. That qualification is not
        a weakening: a conclusion drawn from a window nobody asked about is not a conclusion.
        """
        verdicts, _, _ = run(control_id, **ASKABLE[control_id])
        answered = [v for v in verdicts if v.is_answer]
        assert answered, "%s reaches no conclusion about any record" % control_id

    def test_the_occupancy_control_refuses_a_week_the_capture_never_covered(self):
        """Issue #9, from the control's own end. Two PASSes about rooms in July 2026, drawn
        from segments captured in August 2024, is the exact failure F19c describes - and it
        is worse than an empty population, because it looks like an answer."""
        with pytest.raises(ResponseUnavailable) as caught:
            run("resource_occupancy_consistency")
        assert "2024-08-14" in str(caught.value) and "2026-07-08" in str(caught.value)

    def test_no_fail_is_manufactured_where_the_data_holds_none(self):
        """Honesty check, and a deliberate non-assertion.

        Neither control reaches FAIL on this capture, because the property genuinely has no
        active duplicate and no double-booked room. Inventing a fixture to produce a nicer
        demo is exactly what v1 did with fixtures/synthetic/ and exactly what this repository
        does not do - every record here came from the vendor's own system.
        """
        for control_id, asked in sorted(ASKABLE.items()):
            verdicts, _, source = run(control_id, **asked)
            assert source.is_synthetic is False
            assert Counter(v.outcome for v in verdicts)[Outcome.FAIL] == 0

    def test_the_two_segments_of_one_reservation_do_not_conflict_with_each_other(self):
        """Reservation 007003204 holds room 303 twice - 10-11 and 15-16 August. v1 read that
        repetition as the reason occupancy could not be cut into records at all; it is the
        ordinary case, and a reservation cannot double-book itself."""
        verdicts, _, _ = run("resource_occupancy_consistency", **OCCUPANCY_WINDOW)
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
        verdicts, _, _ = run("duplicate_channel_reservation")
        direct = [v for v in verdicts if "not applicable" in v.reason]
        assert len(direct) == 29, "the covering capture's create window holds 29 direct bookings"
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
        for control in ("duplicate_channel_reservation",
                        by_arrival("duplicate_channel_reservation")):
            verdicts, _, _ = run(control)
            for verdict in verdicts:
                if verdict.outcome is Outcome.FAIL:
                    assert "not applicable" not in verdict.reason


class TestEveryControlStillRuns:
    @pytest.mark.parametrize("control_id", sorted(available()))
    def test_the_single_entry_point_handles_both_shapes(self, control_id):
        """A runner calls `evaluate_population` for everything; it must hand a record-level
        control straight through without the caller knowing which shape it is."""
        verdicts, evidence, _ = run(control_id, **ASKABLE.get(control_id, {}))
        assert len(verdicts) == len(evidence.bundles)
        for verdict in verdicts:
            assert verdict.evidence
