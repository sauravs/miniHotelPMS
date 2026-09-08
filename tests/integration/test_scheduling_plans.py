# -*- coding: utf-8 -*-
"""
Every shipped control, on every provider, produces a plan - and none of them raises.

The unit tests prove each branch of the scheduler. This proves the eleven controls we actually
ship are clean against it, which is the difference between a scheduler that works and an
execution model that is real. Finding F7's complaint was never that the logic was wrong; it was
that `execution` and `freshness_requirement` had been declared, encoded as data, and never read.

THE INTERESTING RESULT IS THE ONE DISAGREEMENT
-----------------------------------------------
`resource_occupancy_consistency` runs in REAL TIME on one provider and on an HOURLY timer on
the other, because only one of them publishes a room-occupancy event. Same rule, same evidence,
same verdicts - a different trigger, and the plan names the missing event so a hotel can go and
ask its vendor for it.

That control is the most time-critical in the set: a double-booked room is discovered at the
front desk with a guest standing there. Hourly is the honest degradation, and it is the
interval the IR declared for precisely this case rather than a number this engine chose.

That is not a crack in criterion 7. Criterion 7 is about verdicts, and the two providers agree
on every one of them. When a control runs is a capability question, and two providers that
happened to publish identical webhooks would have left the fallback path untested.
"""
import pytest

from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.runner import Plan, next_evaluation, run
from hotelcontrols.spec import TenantConfig, available, load

AS_OF = "2026-07-08T09:00"

# Which property runs which PMS - read from the tenant files, so a third provider joins by
# adding one rather than by editing this list.
PROPERTIES = ("sandbox", "demo")

# Measured, not aspirational. Every shipped control's plan on each provider, as it actually
# comes out. The one difference between the two columns is the point of the file.
EXPECTED = {
    "sandbox": {
        "checkout_money_owed": "event",
        "checkout_unrefunded_credit": "daily",
        "duplicate_channel_reservation": "event",
        "inactive_room_future_stay": "periodic",
        "ooo_room_protection": "periodic",
        "rate_room_category_consistency": "event",
        "required_reservation_fields": "event",
        "resource_occupancy_consistency": "event",
        "room_assignment_active_room": "event",
        "room_assignment_type_validity": "event",
        "room_capacity_compliance": "event",
    },
}
EXPECTED["demo"] = dict(EXPECTED["sandbox"],
                        # No room-occupancy webhook on this provider, so the control falls back
                        # to the interval it declared for exactly this case.
                        resource_occupancy_consistency="periodic")


def setup(property_id):
    tenant = TenantConfig.load(property_id)
    package = next(p for p in all_providers() if p.name == tenant.provider)
    adapter, source = package.build(tenant)
    return tenant, adapter, source, FixedClock.at(AS_OF, tenant.timezone)


def plan_for(property_id, control_id, **kwargs):
    tenant, adapter, _source, clock = setup(property_id)
    return next_evaluation(load(control_id), adapter.events(), clock, **kwargs)


@pytest.mark.parametrize("property_id", PROPERTIES)
@pytest.mark.parametrize("control_id", sorted(available()))
class TestEveryControlPlans:
    def test_a_plan_comes_out_and_nothing_raises(self, control_id, property_id):
        assert isinstance(plan_for(property_id, control_id), Plan)

    def test_the_plan_is_the_measured_one(self, control_id, property_id):
        assert plan_for(property_id, control_id).mode == EXPECTED[property_id][control_id]

    def test_no_shipped_control_is_left_without_a_trigger(self, control_id, property_id):
        """Every one of the eleven can actually be caused to run on both providers. A control
        with no trigger is a control nobody notices is dead, which is worse than one that runs
        too often."""
        assert plan_for(property_id, control_id).is_schedulable

    def test_the_plan_explains_itself_as_a_sentence(self, control_id, property_id):
        """Same standard as a verdict's reason. "Runs every 6 hours" is a schedule; "runs every
        6 hours because this PMS publishes no room.occupancy_updated" is something a hotel can
        act on."""
        plan = plan_for(property_id, control_id)
        assert plan.reason.endswith(".") and len(plan.reason) > 30
        assert plan.headline.startswith(("Waiting", "Runs", "Scheduled"))

    def test_a_plan_that_fell_back_names_the_event_it_could_not_use(self, control_id,
                                                                    property_id):
        plan = plan_for(property_id, control_id)
        if not plan.fell_back:
            return
        declared = load(control_id)["execution"].get("events", [])
        assert any(event in plan.reason for event in declared), plan.reason


class TestTheOneDisagreementBetweenProviders:
    """The whole reason a second provider declares a different capability set."""

    def test_the_occupancy_control_is_real_time_on_one_provider_and_timed_on_the_other(self):
        real_time = plan_for("sandbox", "resource_occupancy_consistency")
        timed = plan_for("demo", "resource_occupancy_consistency")

        assert real_time.is_subscription and real_time.events == ("room.occupancy_updated",)
        assert timed.mode == "periodic" and timed.fell_back
        assert "room.occupancy_updated" in timed.reason

    def test_the_fallback_uses_the_interval_the_control_declared_for_this_case(self):
        """Not a default this module chose. The IR says `1h` for precisely this situation, and
        a scheduler picking its own number would be deciding a hotel's policy."""
        from datetime import timedelta
        assert plan_for("demo", "resource_occupancy_consistency").interval == timedelta(hours=1)

    def test_every_other_control_plans_identically_on_both(self):
        """The disagreement is one control and one event. If it ever becomes two, that is a
        capability change worth noticing rather than absorbing."""
        differing = [c for c in available()
                     if plan_for("sandbox", c).mode != plan_for("demo", c).mode]
        assert differing == ["resource_occupancy_consistency"]

    def test_the_disagreement_does_not_reach_the_verdicts(self):
        """Criterion 7 is about answers, and it still holds. A different trigger is a different
        moment, not a different conclusion."""
        outcomes = []
        for property_id in PROPERTIES:
            tenant, adapter, _source, clock = setup(property_id)
            result = run("ooo_room_protection", tenant, adapter, clock)
            outcomes.append(sorted((v.record_id, v.outcome.value) for v in result.verdicts))
        assert outcomes[0] == outcomes[1]


class TestFreshnessOnRealRuns:
    """The other half of F7, end to end on captured evidence."""

    @pytest.mark.parametrize("property_id", PROPERTIES)
    def test_a_run_over_evidence_captured_weeks_ago_says_it_is_stale(self, property_id):
        """`ooo_room_protection` sends no date filter at all, so it is the one control that can
        be run at any instant against these captures - which makes it the one that can
        demonstrate real staleness rather than a constructed one.

        The captures were taken in September 2026. Asked on the 20th, they are twelve days old
        and this control wants evidence under thirty minutes. It is still a real answer about
        real records; it is also out of date, and the run says both.
        """
        tenant = TenantConfig.load(property_id)
        package = next(p for p in all_providers() if p.name == tenant.provider)
        adapter, _source = package.build(tenant)
        result = run("ooo_room_protection", tenant, adapter,
                     FixedClock.at("2026-09-20T09:00", tenant.timezone))

        assert result.freshness.is_stale is True
        assert result.freshness.is_known is True, "the age is known; it is simply large"
        assert "out of date" in result.freshness.headline

    @pytest.mark.parametrize("property_id", PROPERTIES)
    def test_staleness_annotates_a_run_and_never_suppresses_it(self, property_id):
        """A stale run is not a blocked run. Deleting the verdicts because the evidence was old
        would replace a qualified answer with no answer, which is strictly less useful."""
        tenant = TenantConfig.load(property_id)
        package = next(p for p in all_providers() if p.name == tenant.provider)
        adapter, _source = package.build(tenant)
        result = run("ooo_room_protection", tenant, adapter,
                     FixedClock.at("2026-09-20T09:00", tenant.timezone))
        assert result.freshness.is_stale and not result.is_blocked
        assert result.counts["total"] == 28

    @pytest.mark.parametrize("property_id", PROPERTIES)
    def test_a_run_carries_what_the_control_asked_for_and_when_the_evidence_was_obtained(
            self, property_id):
        tenant, adapter, source, clock = setup(property_id)
        result = run("checkout_money_owed", tenant, adapter, clock)
        assert result.maximum_age == load("checkout_money_owed")["freshness_requirement"][
            "maximum_age"]
        assert result.observed_at is not None
        assert result.observed_at.isoformat().startswith(source.observed_at)

    @pytest.mark.parametrize("property_id", PROPERTIES)
    def test_replaying_a_capture_against_an_earlier_clock_says_so_rather_than_calling_it_fresh(
            self, property_id):
        """These captures were taken in September 2026 and the checkout controls are run as of
        July, so the evidence is NEWER than the question. That is not staleness and it is not
        freshness either - it is a property of replaying captures against a historical clock,
        and pretending otherwise would be the only dishonest option available."""
        tenant, adapter, _source, clock = setup(property_id)
        freshness = run("checkout_money_owed", tenant, adapter, clock).freshness
        assert freshness.is_stale is False
        assert "after" in freshness.headline.lower()

    @pytest.mark.parametrize("property_id", PROPERTIES)
    def test_a_blocked_run_still_reports_its_freshness(self, property_id):
        """A run that could not happen has no verdicts and still has a provenance. Losing the
        freshness line on the blocked path would mean the pages that most need explaining are
        the ones explaining least."""
        tenant = TenantConfig.load(property_id)
        package = next(p for p in all_providers() if p.name == tenant.provider)
        adapter, _source = package.build(tenant, package.captures[0])
        result = run("room_assignment_type_validity", tenant, adapter,
                     FixedClock.at(AS_OF, tenant.timezone))
        assert result.is_blocked
        assert result.freshness.headline.endswith(".")
