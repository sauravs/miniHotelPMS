# -*- coding: utf-8 -*-
"""
Slice 22: every way the reservation lookup can fail is a GAP, never a decision (V10, D15).

`look_up` reads two facts through the unchanged evidence layer. These are its failure paths, each
of which must reach the decision as a reservation that could not be established - and so as
STAFF_REVIEW naming why - rather than as an exception, an empty answer or, worst, a denial:

  - the capture cannot answer the window asked (F19c / issue #9: refused, not replayed wrong);
  - the call budget is already spent (R1, R8: the budget raises rather than truncating);
  - the template names no query for this provider;
  - two records carry the requested id, so which one is meant cannot be said.

Also here: the template's remaining refusals, and `make_decision`'s two.
"""
import copy
import json
from datetime import date, datetime, time, timezone

import pytest

from hotelcontrols.evidence import CallBudget
from hotelcontrols.guest import (STAFF_REVIEW, GuestRequest, Policy, ReservationEvidence,
                                 decide, load_template, look_up, make_decision, window)
from hotelcontrols.guest.template import Template
from hotelcontrols.kernel import FixedClock, Value
from hotelcontrols.providers import registry as providers
from hotelcontrols.providers.base import Request
from hotelcontrols.spec import SpecError, TenantConfig
from hotelcontrols.spec.registry import SPEC_DIR

TEMPLATE = load_template()


def sandbox(capture="sandbox2026"):
    tenant = TenantConfig.load("sandbox")
    adapter, source = providers.load(tenant.provider).build(tenant, capture)
    return tenant, adapter, source


class TestTheLookupOnRealEvidence:

    def test_a_checked_in_guest_departing_today_is_found_for_one_call(self):
        tenant, adapter, source = sandbox()
        evidence = look_up(TEMPLATE, "007004343", adapter, tenant,
                           FixedClock.at(source.as_of, tenant.timezone))
        assert evidence.absent is None and evidence.calls == 1
        assert (evidence.status.payload, evidence.departure_date.payload) == \
            ("checked_in", "2026-07-08")
        assert evidence.status.source == "pms:minihotel/GetReservationKey"

    def test_a_window_the_capture_never_covered_is_refused_into_a_gap(self):
        """The capture holds departures from 2026-07-01. Asked as of that day, the window
        starts the day before - which the frozen source refuses rather than answering from
        the wrong window (F19c)."""
        tenant, adapter, _source = sandbox()
        evidence = look_up(TEMPLATE, "007004343", adapter, tenant,
                           FixedClock.at("2026-07-01", tenant.timezone))
        assert evidence.absent and "could not be looked up" in evidence.absent
        assert "cannot answer that question" in evidence.absent

    def test_a_spent_budget_is_a_gap_and_not_a_truncated_answer(self):
        tenant, adapter, source = sandbox()
        budget = CallBudget(1)
        budget.spend(Request("already", {}))
        evidence = look_up(TEMPLATE, "007004343", adapter, tenant,
                           FixedClock.at(source.as_of, tenant.timezone), budget)
        assert evidence.absent and "call budget" in evidence.absent

    def test_a_provider_the_template_names_no_query_for_is_a_gap(self):
        raw = copy.deepcopy(TEMPLATE.raw)
        del raw["evidence"]["population"]["provider_query"]["minihotel"]
        tenant, adapter, source = sandbox()
        evidence = look_up(Template.from_dict(raw), "007004343", adapter, tenant,
                           FixedClock.at(source.as_of, tenant.timezone))
        assert evidence.absent and "no way to look a reservation up" in evidence.absent

    def test_the_window_is_the_days_the_reason_names(self):
        assert window(TEMPLATE, date(2026, 7, 8)) == (date(2026, 7, 7), date(2026, 7, 9))

    def test_a_window_token_nobody_understands_is_refused(self):
        raw = copy.deepcopy(TEMPLATE.raw)
        raw["evidence"]["population"]["window"]["to"] = "tomorrow"
        with pytest.raises(ValueError, match="tomorrow"):
            window(Template.from_dict(raw), date(2026, 7, 8))


class _TwoOfEverything:
    """A provider whose one response holds two records with the same id."""

    name = "twins"

    def fetch(self, request):
        return "response"

    def records(self, response, entity):
        return ["first", "second"]

    def identity(self, record):
        return Value.known("42")

    def resolve(self, field_name, record):
        return Value.known("checked_in" if field_name.endswith("status") else "2026-07-08")

    def source_key(self, field_name):
        return "one"

    def source_key_for_request(self, request):
        return "one"

    def follow_up(self, field_name, record_id):
        return None

    def reference_request(self, entity):
        return None

    def provenance(self, field_name):
        return "pms:twins/x"


def test_two_records_with_the_requested_id_are_a_gap_not_a_choice():
    raw = copy.deepcopy(TEMPLATE.raw)
    raw["evidence"]["population"]["provider_query"]["twins"] = {"endpoint": "all", "filters": {}}
    tenant = TenantConfig.load("sandbox")
    evidence = look_up(Template.from_dict(raw), "42", _TwoOfEverything(), tenant,
                       FixedClock.at("2026-07-08", tenant.timezone))
    assert evidence.absent and "appears 2 times" in evidence.absent
    ruling = decide(GuestRequest("42", time(15)), Policy("sandbox", {
        name: None for name in TEMPLATE.schema.parameters}), evidence, date(2026, 7, 8))
    assert ruling.decision == STAFF_REVIEW and ruling.gaps[0].name == "reservation"


# --------------------------------------------------------------------------- refusals
class TestTheTemplatesOtherRefusals:

    def raw(self):
        return json.loads((SPEC_DIR / "guest" / "late_checkout.json").read_text("utf-8"))

    @pytest.mark.parametrize("change, match", [
        (lambda r: r["parameters"].pop("maximum_time"), "exactly"),
        (lambda r: r["evidence"].update(fields=["reservation.status"]), "must read exactly"),
        (lambda r: r["evidence"].pop("population"), "no population"),
        (lambda r: r["parameter_order"].update(rules=[["free_until", "breakfast"]]),
         "not two of its parameters"),
        (lambda r: r["actions"].pop("APPROVED"), "which task it raises"),
        (lambda r: r["actions"].update(DENIED={"severity": "low"}), "DENIED"),
        (lambda r: r["actions"].update(APPROVED={"severity": "urgent"}), "severity"),
    ])
    def test_refused(self, change, match):
        raw = self.raw()
        change(raw)
        with pytest.raises(SpecError, match=match):
            Template.from_dict(raw)

    def test_a_template_that_does_not_exist_or_names_itself_otherwise(self, tmp_path):
        with pytest.raises(SpecError, match="no guest-service template"):
            load_template("ROOM_UPGRADE")
        (tmp_path / "guest").mkdir()
        raw = self.raw()
        raw["template"] = "SOMETHING_ELSE"
        (tmp_path / "guest" / "late_checkout.json").write_text(json.dumps(raw), "utf-8")
        with pytest.raises(SpecError, match="SOMETHING_ELSE"):
            load_template(spec_dir=tmp_path)


class TestMakeDecisionRefuses:

    def parts(self, tenant_id="sandbox"):
        request = GuestRequest("1", time(15))
        policy = Policy(tenant_id, {name: None for name in TEMPLATE.schema.parameters})
        evidence = ReservationEvidence.missing("1", "not found")
        return request, policy, evidence, decide(request, policy, evidence, date(2026, 7, 8))

    def test_a_naive_instant(self):
        request, policy, evidence, ruling = self.parts()
        with pytest.raises(ValueError, match="timezone"):
            make_decision(TEMPLATE, request, policy, evidence, ruling, tenant_id="sandbox",
                          received_at=datetime(2026, 7, 8), provider="x", evidence_label="c")

    def test_another_propertys_policy(self):
        request, policy, evidence, ruling = self.parts("demo")
        with pytest.raises(ValueError, match="policy"):
            make_decision(TEMPLATE, request, policy, evidence, ruling, tenant_id="sandbox",
                          received_at=datetime(2026, 7, 8, tzinfo=timezone.utc), provider="x",
                          evidence_label="c")

    def test_a_policy_must_state_exactly_the_six(self):
        with pytest.raises(ValueError, match="exactly"):
            Policy("sandbox", {"free_until": None})
