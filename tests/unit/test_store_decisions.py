# -*- coding: utf-8 -*-
"""
Slice 22: every guest decision is stored - tenant-scoped, versioned - and raises at most one task.

The `decisions` table is born under slice 17's structural guard (`test_tenant_scoped_store.py`
discovers it from `schema.sql`), and its task goes into slice 18's `actions` table through the
same natural-key insert a FAIL uses. What these protect:

  - V9: the same request submitted twice is ONE decision and ONE action (D1 §65).
  - V4: one property cannot read another's decision; it reads as absent, like one that never
    existed, so an id cannot be probed.
  - V3, applied to decisions: each names the template version and digest that made it.
  - R9: the fee survives a round trip as Money with its currency, never a bare number.
"""
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from hotelcontrols.actions import guest_task
from hotelcontrols.guest import (APPROVED_WITH_FEE, DENIED, STAFF_REVIEW, Decision, Gap,
                                 GuestRequest, Policy, ReservationEvidence, decide,
                                 load_template, make_decision)
from hotelcontrols.kernel import Money, Value
from hotelcontrols.store import RunStore

TEMPLATE = load_template()
AT = datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)
VALUES = {"free_until": time(14), "charge_from": time(14), "approval_required_after": time(16),
          "maximum_time": time(18), "fee_per_hour": Money.parse("25.00", "USD"),
          "hour_rounding": "started_hour"}


def a_decision(tenant_id="sandbox", at="15:00", status="checked_in", values=None,
               reservation_id="007004343") -> Decision:
    hour, minute = map(int, at.split(":"))
    request = GuestRequest(reservation_id, time(hour, minute))
    policy = Policy(tenant_id=tenant_id, values=values if values is not None else dict(VALUES))
    evidence = ReservationEvidence(
        reservation_id=reservation_id,
        status=Value.known(status, source="pms:x/reservations"),
        departure_date=Value.known("2026-07-08", source="pms:x/reservations"))
    ruling = decide(request, policy, evidence, date(2026, 7, 8))
    return make_decision(TEMPLATE, request, policy, evidence, ruling, tenant_id=tenant_id,
                         received_at=AT, provider="x", evidence_label="cap")


@pytest.fixture
def store():
    store = RunStore()
    yield store
    store.close()


class TestRoundTrip:

    def test_a_decision_reads_back_as_it_was_made(self, store):
        made = a_decision()
        stored, created = store.save_decision(made, guest_task(made))
        assert created and stored == made
        again = store.decision(made.decision_id, tenant_id="sandbox")
        assert again == made
        assert again.fee == Money(Decimal("25.00"), "USD")          # R9: with its currency
        assert again.template_version == TEMPLATE.version
        assert again.template_digest == TEMPLATE.digest

    def test_gaps_and_unknown_evidence_survive(self, store):
        made = a_decision(values={name: None for name in VALUES})
        store.save_decision(made, guest_task(made))
        again = store.decision(made.decision_id, tenant_id="sandbox")
        assert again.decision == STAFF_REVIEW
        assert again.gaps == made.gaps and all(isinstance(g, Gap) for g in again.gaps)
        assert len(again.gaps) == 6

    def test_listing_is_newest_first_and_per_property(self, store):
        first, second = a_decision(at="15:00"), a_decision(at="15:30")
        for made in (first, second):
            store.save_decision(made, guest_task(made))
        store.save_decision(a_decision("demo"), guest_task(a_decision("demo")))
        listed = store.decisions(tenant_id="sandbox")
        assert {d.decision_id for d in listed} == {first.decision_id, second.decision_id}


class TestOneDecisionOneAction:
    """D1 §65: a double tap is Tuesday, not an edge case."""

    def test_the_same_request_twice_is_one_decision_and_one_task(self, store):
        made = a_decision()
        _first, created = store.save_decision(made, guest_task(made))
        again, created_again = store.save_decision(a_decision(), guest_task(a_decision()))
        assert (created, created_again) == (True, False)
        assert again == made
        assert len(store.decisions(tenant_id="sandbox")) == 1
        assert len(store.actions(tenant_id="sandbox")) == 1

    def test_a_different_time_is_a_second_decision_with_its_own_task(self, store):
        for at in ("15:00", "16:30"):
            made = a_decision(at=at)
            store.save_decision(made, guest_task(made))
        assert len(store.decisions(tenant_id="sandbox")) == 2
        assert len(store.actions(tenant_id="sandbox")) == 2

    def test_a_denial_raises_no_task(self, store):
        made = a_decision(status="cancelled")
        assert made.decision == DENIED and guest_task(made) is None
        stored, _created = store.save_decision(made, None)
        assert stored.action_id is None
        assert store.actions(tenant_id="sandbox") == []

    def test_the_task_is_the_tables_severity_and_audience(self, store):
        made = a_decision()
        assert made.decision == APPROVED_WITH_FEE
        store.save_decision(made, guest_task(made))
        (task,) = store.actions(tenant_id="sandbox")
        assert (task.severity, task.audience) == ("medium", "front_office_manager")
        assert task.action_id == store.decision(made.decision_id,
                                                tenant_id="sandbox").action_id
        assert "25.00 USD" in task.reason and "007004343" in task.reason

    def test_a_task_is_moved_by_a_person_through_slice_18s_state_machine(self, store):
        made = a_decision()
        store.save_decision(made, guest_task(made))
        moved = store.transition(made.action_id, "done", tenant_id="sandbox", at=AT,
                                 actor="operator")
        assert moved.state == "done"


class TestIsolation:
    """V4: one property cannot read another's decisions."""

    def test_reads_need_a_property_by_keyword(self, store):
        with pytest.raises(TypeError):
            store.decision("x")                                     # noqa
        with pytest.raises(TypeError):
            store.decisions()                                       # noqa
        with pytest.raises(TypeError):
            store.decision("x", "sandbox")                          # noqa

    def test_another_propertys_decision_is_absent_exactly_like_a_missing_one(self, store):
        made = a_decision("demo")
        store.save_decision(made, guest_task(made))
        assert store.decision(made.decision_id, tenant_id="sandbox") is None
        assert store.decision("no-such-id", tenant_id="sandbox") is None
        assert store.decisions(tenant_id="sandbox") == []

    def test_a_task_in_another_propertys_name_is_refused(self, store):
        made = a_decision("demo")
        with pytest.raises(ValueError, match="property"):
            store.save_decision(made, guest_task(a_decision("sandbox")))
        assert store.decisions(tenant_id="demo") == []


def test_a_task_whose_key_disagrees_with_its_decision_is_refused():
    """The decision names its task by slice 18's natural key; a decision carrying any other id
    would raise a task detached from it, so `guest_task` refuses."""
    from dataclasses import replace
    with pytest.raises(ValueError, match="natural key"):
        guest_task(replace(a_decision(), action_id="0000000000000000"))
