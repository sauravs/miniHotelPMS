# -*- coding: utf-8 -*-
"""
Evidence gathering against real captured responses.

This is where review finding F1 is either fixed or it is not. In v1, three controls returned
**111 UNKNOWN out of 111 records** because a stay could never be joined to the room it was
assigned - and the evidence was not missing, it sat in a response costing ONE call for the whole
property. There was simply no way for a rule to say so.

The cost model is the other thing under test, and it is asserted by COUNTING INVOCATIONS rather
than assumed: `1 + R + N`, where R is references and N is records needing a per-record call.
R1 is why - a folio takes one reservation per call and there is no bulk journal endpoint.
"""
import pytest

from hotelcontrols.evidence import BudgetExceeded, CallBudget, gather
from hotelcontrols.providers.base import ProviderError
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.minihotel import FrozenSource, MiniHotelAdapter
from hotelcontrols.spec import TenantConfig, load


def setup(capture="sandbox2026", as_of="2026-07-08T09:00"):
    tenant = TenantConfig.load("sandbox")
    source = FrozenSource(capture)
    return (MiniHotelAdapter(tenant, source), tenant, source,
            FixedClock.at(as_of, tenant.timezone))


class TestTheJoinThatV1CouldNotExpress:
    """F1, directly."""

    def test_room_capacity_now_resolves_for_real_stays(self):
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))

        assert len(evidence) > 100, "the 2026 capture holds a hundred-odd room stays"
        resolved = [b for b in evidence
                    if b.fields["room.max_guests.adults"].is_known]
        unknown = [b for b in evidence
                   if not b.fields["room.max_guests.adults"].is_known]

        # v1 returned 111 of 111 unknown. Anything resolving at all is the fix; the remainder
        # are unknown for a REASON THE HOTEL CAN ACT ON rather than for want of a join.
        assert resolved, "no stay resolved its room's capacity - the join is not working"
        for bundle in unknown:
            reason = bundle.fields["room.max_guests.adults"].reason
            # Three legitimate reasons, none of them "we could not perform the join":
            #   R12  the room reports capacity 0, meaning unconfigured
            #   -    the room has no capacity block at all
            #   -    the stay names a room this property does not have, or names none
            assert ("unconfigured" in reason
                    or "absent from the provider response" in reason
                    or "no room in this property matches" in reason
                    or "not established" in reason), reason

    def test_the_room_master_is_fetched_once_for_every_stay_in_the_run(self):
        """The whole point of a reference. One call answers for all of them."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))
        endpoints = [request.endpoint for request in source.calls]
        assert len(evidence) > 100
        assert endpoints.count("getRooms") == 1, endpoints

    def test_a_set_reference_resolves_to_the_whole_collection(self):
        """Control 1b asks whether a room's type is one of the DEFINED types."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_assignment_type_validity"), adapter, tenant, clock,
                          CallBudget(200))
        codes = evidence.bundles[0].fields["room_type.code"]
        assert codes.is_known
        assert "dbl" in codes.payload and "twin" in codes.payload

    def test_a_collection_reference_brings_back_every_matching_record(self):
        """Control 2 starts from the room side: one room, several occupancy segments."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("ooo_room_protection"), adapter, tenant, clock, CallBudget(200))
        with_segments = [b for b in evidence if b.related.get("occupancy")]
        assert with_segments, "room 303 holds two captured occupancy segments"
        segments = with_segments[0].related["occupancy"]
        assert all("occupancy.reservation_id" in s for s in segments)


class TestAJoinNeverInventsAMatch:
    def test_a_key_that_matches_nothing_is_unknown_with_that_reason(self):
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))
        unmatched = [b for b in evidence
                     if "no room in this property matches"
                     in (b.fields["room.max_guests.adults"].reason or "")]
        if unmatched:
            for bundle in unmatched:
                assert not bundle.fields["room.max_guests.adults"].is_known

    def test_an_unknown_key_never_silently_picks_the_first_record(self):
        """The failure this guard exists for: a stay with no assigned room must not acquire
        room 01's capacity because room 01 happened to be first in the response."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))
        unassigned = [b for b in evidence if not b.fields["stay.room_number"].is_known
                      or b.fields["stay.room_number"].payload in (None, "")]
        for bundle in unassigned:
            assert not bundle.fields["room.max_guests.adults"].is_known

    def test_a_tenant_supplied_reference_nobody_supplied_is_unknown_not_empty(self):
        """R13 / open question 1.6. Control 9's rate-plan mapping cannot come from this PMS at
        all. An empty set would make every membership test FAIL; UNKNOWN says what to connect."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("rate_room_category_consistency"), adapter, tenant, clock,
                          CallBudget(200))
        assert len(evidence) > 0
        for bundle in evidence:
            value = bundle.fields["rate_plan.permitted_room_types"]
            assert not value.is_known
            assert "property" in value.reason


class TestCostIsAsserted:
    def test_the_checkout_control_costs_one_plus_n(self):
        """R1. One population call, plus one folio per checked-out reservation. The 2026
        capture holds two checkouts on 8 July, so three calls."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("checkout_money_owed"), adapter, tenant, clock, CallBudget(50))
        n = len(evidence)
        assert n >= 1
        assert len(source.calls) == 1 + n, [r.endpoint for r in source.calls]

    def test_a_control_with_a_reference_costs_one_plus_r(self):
        adapter, tenant, source, clock = setup()
        gather(load("room_capacity_compliance"), adapter, tenant, clock, CallBudget(200))
        # One population call plus one room-master call. No per-record calls: capacity comes
        # from the reference, which is the entire saving.
        assert len(source.calls) == 2, [r.endpoint for r in source.calls]

    def test_the_budget_stops_a_run_rather_than_truncating_it(self):
        """A truncated population reports 'no violations' about records nobody looked at."""
        adapter, tenant, source, clock = setup()
        with pytest.raises(BudgetExceeded):
            # One call buys the population; the first folio then has nowhere to come from.
            gather(load("checkout_money_owed"), adapter, tenant, clock, CallBudget(1))


class TestDegradationIsPerRecord:
    def test_an_uncapturable_folio_degrades_one_bundle_not_the_run(self):
        """Only three folios were captured: one call per reservation is the cost this control
        is built around (R1), on somebody else's server (R8). The rest must be UNKNOWN."""
        adapter, tenant, source, clock = setup(as_of="2026-07-10T09:00")
        evidence = gather(load("checkout_money_owed"), adapter, tenant, clock, CallBudget(50))
        assert len(evidence) >= 2, "10 July has two checkouts in the capture"
        missing = [b for b in evidence if not b.fields["folio.balance_due"].is_known]
        present = [b for b in evidence if b.fields["folio.balance_due"].is_known]
        assert missing and present, "this date is chosen because it has one of each"
        for bundle in missing:
            assert bundle.record_id, "a degraded record stays in the population"
            assert "could not be fetched" in bundle.fields["folio.balance_due"].reason

    def test_a_failed_response_is_attempted_once_not_once_per_record(self):
        adapter, tenant, source, clock = setup(as_of="2026-07-10T09:00")
        gather(load("checkout_money_owed"), adapter, tenant, clock, CallBudget(50))
        attempted = [r for r in source.calls if r.endpoint != "GetReservationKey"]
        assert len(attempted) == len({r.key() for r in attempted}), \
            "the same folio must never be requested twice in one run"


class TestBundleShape:
    def test_every_declared_field_is_present_even_when_unknown(self):
        """A caller that has to remember which fields might be absent is a caller that will
        forget. A bundle is always complete in SHAPE."""
        adapter, tenant, source, clock = setup()
        ir = load("room_capacity_compliance")
        evidence = gather(ir, adapter, tenant, clock, CallBudget(200))
        declared = set(ir.evidence_fields)
        for bundle in evidence:
            assert set(bundle.fields) == declared

    def test_no_field_is_ever_none(self):
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))
        for bundle in evidence:
            for name, value in bundle.fields.items():
                assert value is not None, name
                assert value.is_known or value.reason, name

    def test_every_unknown_carries_provenance_so_a_hotel_knows_where_we_looked(self):
        adapter, tenant, source, clock = setup(as_of="2026-07-10T09:00")
        evidence = gather(load("checkout_money_owed"), adapter, tenant, clock, CallBudget(50))
        for bundle in evidence:
            for name, value in bundle.fields.items():
                assert value.source, (
                    "%s: an UNKNOWN with no provenance tells a hotel nothing about what to fix"
                    % name)


class TestPopulationIsABoundNotAVerdict:
    def test_records_the_control_will_exclude_are_still_returned(self):
        """Scope filtering is the evaluator's rule. Applying it here as well would mean the
        scope clause could never be exercised against real data - and the provider does return
        records nobody asked for."""
        adapter, tenant, source, clock = setup()
        evidence = gather(load("room_capacity_compliance"), adapter, tenant, clock,
                          CallBudget(200))
        statuses = {b.fields["reservation.status"].payload for b in evidence
                    if b.fields["reservation.status"].is_known}
        assert len(statuses) > 1, "the population is unfiltered, so several statuses appear"

    def test_relative_dates_resolve_through_the_property_clock(self):
        """F11. At 22:30 UTC it is already tomorrow in Jerusalem, and 'who checked out today'
        has a different answer depending on which clock is asked."""
        from hotelcontrols.evidence import build_request
        tenant = TenantConfig.load("sandbox")
        request = build_request(load("checkout_money_owed"), "minihotel",
                                FixedClock.at("2026-07-08T09:00", tenant.timezone))
        assert request.params["DepartureDate"] == {"From": "2026-07-07", "To": "2026-07-08"}

    def test_an_unrecognised_relative_date_raises_rather_than_being_passed_through(self):
        from hotelcontrols.evidence import build_request
        import copy
        ir = load("checkout_money_owed")
        broken = copy.deepcopy(ir.raw)
        broken["population"]["provider_query"]["minihotel"]["filters"]["DepartureDate"] = \
            {"From": "todayish", "To": "today"}
        from hotelcontrols.spec import ControlIR
        with pytest.raises(ValueError):
            build_request(ControlIR(broken), "minihotel",
                          FixedClock.at("2026-07-08T09:00", "Asia/Jerusalem"))


class TestEveryShippedControlCanGather:
    """The slice-3 gate, and the measurement that shows what the reference stage bought.

    v1's numbers, from the review: three controls returned 111 UNKNOWN out of 111 records, two
    were blocked outright, and one excluded every record. The evidence was not missing - it sat
    in a response costing ONE call for the whole property - but no rule could say so.
    """

    @pytest.mark.parametrize("control_id", sorted(__import__(
        "hotelcontrols.spec", fromlist=["available"]).available()))
    def test_gathering_either_answers_or_refuses_in_a_sentence(self, control_id):
        """No stack traces, ever. A control this body of evidence cannot answer must refuse
        with a NAMED provider error - which the runner turns into a sentence on screen - and
        never with an incidental exception or, worse, an answer from the wrong window.

        `resource_occupancy_consistency` is the live case (issue #9): the only occupancy
        capture covers 2024-08-14..2024-08-21, and asked about any other week the source
        refuses rather than replaying August 2024 as if it were this week.
        """
        adapter, tenant, source, clock = setup()
        try:
            evidence = gather(load(control_id), adapter, tenant, clock, CallBudget(400))
        except ProviderError as refusal:
            assert len(str(refusal)) > 20, "a refusal that does not explain itself is a crash"
            return
        assert isinstance(evidence.calls, int)

    @pytest.mark.parametrize("control_id", [
        "room_assignment_type_validity", "room_assignment_active_room",
        "inactive_room_future_stay"])
    def test_the_controls_that_returned_all_unknown_in_v1_now_resolve_most_of_their_evidence(
            self, control_id):
        adapter, tenant, source, clock = setup()
        evidence = gather(load(control_id), adapter, tenant, clock, CallBudget(400))
        total = sum(len(b.fields) for b in evidence)
        known = sum(1 for b in evidence for v in b.fields.values() if v.is_known)
        assert total > 500, "these controls run over a hundred-odd stays"
        assert known / total > 0.9, (
            "%s resolves only %d%% of its declared evidence" % (control_id, 100 * known // total))

    def test_no_control_costs_more_than_one_call_per_reference_plus_one_per_record(self):
        """R1, across the whole shipped set. The bound that matters is that a REFERENCE costs
        one call per run rather than one per record - the difference between 2 calls and 112."""
        for control_id in sorted(__import__(
                "hotelcontrols.spec", fromlist=["available"]).available()):
            adapter, tenant, source, clock = setup()
            ir = load(control_id)
            try:
                evidence = gather(ir, adapter, tenant, clock, CallBudget(400))
            except ProviderError:
                # A control this evidence set cannot answer costs whatever it spent before
                # being refused, and the bound below is about answered runs (issue #9).
                continue
            ceiling = 1 + len(ir.references) + len(evidence)
            assert evidence.calls <= ceiling, (
                "%s cost %d calls for %d records and %d references"
                % (control_id, evidence.calls, len(evidence), len(ir.references)))
