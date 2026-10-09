# -*- coding: utf-8 -*-
"""
Slice 22: the approved decision table is the contract, and the engine cannot drift from it.

`spec/guest/late_checkout.json` was written and approved by the owner before any code (plan-v3
§5's checkpoint). These tests hold the file and the code together: the engine refuses a table
that is not approved, or whose rules differ from the ones it implements, and the table's digest
is pinned to its version - slice 16's rule ("editing a rule makes a new version") applied to a
guest template, without touching `spec/ir.lock.json` or `tools/lock_spec.py`, which slice 22
may not change.

Also here: the request is parsed exactly as slice 21 parses a time (D12, no model), the policy
is typed with slice 21's `ParameterSchema` (D15, no defaults, null is not decided), and the fee
is repeated `Money.plus` (the kernel is unchanged).
"""
import copy
import json
import pathlib
import shutil
from datetime import time
from decimal import Decimal

import pytest

from hotelcontrols.guest import (DECISIONS, RULES, GuestRequest, RequestRefused, charged_hours,
                                 fee_for, load_policy, load_template, parse_request,
                                 policy_from_block)
from hotelcontrols.guest.template import Template
from hotelcontrols.kernel import Money
from hotelcontrols.spec import SpecError, TenantConfig
from hotelcontrols.spec.registry import SPEC_DIR

TEMPLATE_FILE = SPEC_DIR / "guest" / "late_checkout.json"

# THE LOCK FOR THIS TEMPLATE. Editing anything decision-bearing in the table changes the digest;
# this test then fails until the version is bumped and the new pair is written here, on purpose,
# in the same PR. A stored decision names both, so "decided under v1" cannot quietly mean two
# different tables.
LOCKED = {1: "sha256:36310ed91a9f03b5c5afe3ce47cabd60bd3832c8b188d3a74d023e03db2c86c5"}

DECIDED = {"free_until": "14:00", "charge_from": "14:00", "approval_required_after": "16:00",
           "maximum_time": "18:00", "fee_per_hour": {"amount": "25.00", "currency": "USD"},
           "hour_rounding": "started_hour"}


def raw_template():
    return json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- the table
class TestTheApprovedTable:

    def test_it_is_approved_and_records_the_owners_answers(self):
        raw = raw_template()
        assert raw["status"] == "approved"
        assert sorted(raw["approval"]["answers"]) == ["1", "2", "3", "4", "5"]

    def test_the_engine_implements_exactly_the_tables_rules_in_order(self):
        assert [(r["rule"], r["decision"]) for r in raw_template()["rules"]] == list(RULES)

    def test_the_gap_rule_is_first_and_decides_staff_review(self):
        """V10's structural half: nothing can be decided before the gaps are looked at."""
        assert RULES[0] == ("LC1-gaps", "STAFF_REVIEW")

    def test_the_five_decisions_are_d15s(self):
        assert DECISIONS == ("APPROVED", "APPROVED_WITH_FEE", "DENIED", "STAFF_REVIEW",
                             "UNAVAILABLE")

    def test_no_rule_decides_unavailable(self):
        """G12a: availability is BLOCKED, and the table says UNAVAILABLE is unreachable."""
        assert "UNAVAILABLE" not in {decision for _rule, decision in RULES}
        assert "UNAVAILABLE" in raw_template()["unreachable"]

    def test_the_digest_is_pinned_to_the_version(self):
        template = load_template()
        assert LOCKED.get(template.version) == template.digest, (
            "spec/guest/late_checkout.json changed without a version bump: bump `version`, "
            "then record {%d: %r} in LOCKED here" % (template.version, template.digest))

    def test_rewording_prose_needs_no_new_version(self):
        raw = raw_template()
        reworded = copy.deepcopy(raw)
        reworded["note"] = "reworded"
        reworded["rules"][3]["why"] = "reworded"
        reworded["parameters"]["free_until"]["description"] = "reworded"
        assert Template.from_dict(reworded).digest == Template.from_dict(raw).digest

    def test_changing_a_decision_bearing_line_moves_the_digest(self):
        raw = raw_template()
        changed = copy.deepcopy(raw)
        changed["actions"]["APPROVED"]["severity"] = "high"
        assert Template.from_dict(changed).digest != Template.from_dict(raw).digest

    def test_every_parameter_is_required_and_has_no_default(self):
        """D15: no defaults. slice 21's schema refuses one, and the template declares none."""
        template = load_template()
        assert sorted(template.schema.parameters) == sorted(DECIDED)
        assert all(p.required for p in template.schema.parameters.values())

    def test_both_providers_ask_for_the_same_window_the_reason_names(self):
        """The not-found reason states the window, so it must be the window each provider is
        actually asked for. The tokens are compared, not interpreted."""
        population = raw_template()["evidence"]["population"]
        window = population["window"]
        assert window == {"from": "today-1d", "to": "today+1d"}
        for provider, query in population["provider_query"].items():
            text = json.dumps(query["filters"])
            assert window["from"] in text and window["to"] in text, provider


class TestTheEngineRefusesADriftedTable:

    @pytest.fixture
    def spec(self, tmp_path):
        target = tmp_path / "spec"
        shutil.copytree(SPEC_DIR, target, ignore=shutil.ignore_patterns("drafts"))
        return target

    def edit(self, spec, change):
        path = spec / "guest" / "late_checkout.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        change(raw)
        path.write_text(json.dumps(raw), encoding="utf-8")

    def test_a_draft_table_is_not_read(self, spec):
        self.edit(spec, lambda raw: raw.update(status="DRAFT - awaiting approval"))
        with pytest.raises(SpecError, match="not approved"):
            load_template(spec_dir=spec)

    def test_a_rule_whose_decision_was_edited_is_refused_naming_it(self, spec):
        def widen(raw):
            raw["rules"][0]["decision"] = "APPROVED"
        self.edit(spec, widen)
        with pytest.raises(SpecError, match="LC1-gaps"):
            load_template(spec_dir=spec)

    def test_a_reordered_table_is_refused(self, spec):
        def swap(raw):
            raw["rules"][7], raw["rules"][8] = raw["rules"][8], raw["rules"][7]
        self.edit(spec, swap)
        with pytest.raises(SpecError, match="LC8-free|LC9-after-maximum"):
            load_template(spec_dir=spec)

    def test_a_parameter_with_a_default_is_refused_by_slice_21s_schema(self, spec):
        self.edit(spec, lambda raw: raw["parameters"]["free_until"].update(default="14:00"))
        with pytest.raises(SpecError, match="default"):
            load_template(spec_dir=spec)

    def test_an_optional_parameter_is_refused(self, spec):
        self.edit(spec, lambda raw: raw["parameters"]["maximum_time"].update(required=False))
        with pytest.raises(SpecError, match="maximum_time"):
            load_template(spec_dir=spec)


# --------------------------------------------------------------------------- the request
class TestTheRequest:
    """D12: structured. A malformed request is refused naming the field, never guessed."""

    def test_a_well_formed_request(self):
        assert parse_request({"reservation_id": " 007004343 ", "requested_time": "15:00"}) == \
            GuestRequest("007004343", time(15, 0))

    @pytest.mark.parametrize("form, field", [
        ({"requested_time": "15:00"}, "reservation_id"),
        ({"reservation_id": "  ", "requested_time": "15:00"}, "reservation_id"),
        ({"reservation_id": "1"}, "requested_time"),
        ({"reservation_id": "1", "requested_time": ""}, "requested_time"),
        ({"reservation_id": "1", "requested_time": "3pm"}, "requested_time"),
        ({"reservation_id": "1", "requested_time": "3"}, "requested_time"),
        ({"reservation_id": "1", "requested_time": "25:00"}, "requested_time"),
        ({"reservation_id": "1", "requested_time": "15:00Z"}, "requested_time"),
        ({"reservation_id": "1", "requested_time": "15:00+02:00"}, "requested_time"),
    ])
    def test_a_malformed_request_is_refused_naming_the_field(self, form, field):
        with pytest.raises(RequestRefused) as refused:
            parse_request(form)
        assert refused.value.field == field
        assert field in str(refused.value)

    def test_a_time_naming_another_clock_says_so(self):
        """Parsed exactly as slice 21 parses a time parameter: F11, the property's clock."""
        with pytest.raises(RequestRefused, match="another clock"):
            parse_request({"reservation_id": "1", "requested_time": "15:00Z"})


# --------------------------------------------------------------------------- the policy
class TestThePolicy:
    """D15 typed with slice 21's vocabulary. null is not decided; a wrong type, unit or currency
    is refused by name; the times must be in order (D2 §31)."""

    TEMPLATE = load_template()

    def typed(self, **changes):
        block = dict(DECIDED)
        block.update(changes)
        return policy_from_block(self.TEMPLATE, block, tenant_id="test",
                                 currencies=("EUR", "ILS", "USD"))

    def test_a_decided_policy_is_typed(self):
        policy = self.typed()
        assert policy["free_until"] == time(14, 0)
        assert policy["fee_per_hour"] == Money(Decimal("25.00"), "USD")
        assert policy["hour_rounding"] == "started_hour"
        assert policy.undecided == ()

    def test_null_is_not_decided_and_is_kept_as_such(self):
        policy = self.typed(fee_per_hour=None, maximum_time=None)
        assert policy.undecided == ("maximum_time", "fee_per_hour")
        assert policy["fee_per_hour"] is None

    def test_a_bare_fee_is_refused(self):
        """R9: a bare 25 is not money - plan-v3 §5 'a bare 25 fails the test'."""
        with pytest.raises(SpecError, match="fee_per_hour.*bare"):
            self.typed(fee_per_hour=25)

    def test_a_fee_in_a_currency_the_property_does_not_use_is_refused(self):
        with pytest.raises(SpecError, match="GBP"):
            self.typed(fee_per_hour={"amount": "25.00", "currency": "GBP"})

    def test_a_rounding_with_no_such_option_is_refused(self):
        with pytest.raises(SpecError, match="hour_rounding"):
            self.typed(hour_rounding="nearest_hour")

    def test_a_missing_parameter_is_refused_rather_than_read_as_undecided(self):
        block = dict(DECIDED)
        del block["maximum_time"]
        with pytest.raises(SpecError, match="maximum_time"):
            policy_from_block(self.TEMPLATE, block, tenant_id="test", currencies=("USD",))

    @pytest.mark.parametrize("changes, first, second", [
        ({"charge_from": "14:30"}, "charge_from", "free_until"),
        ({"approval_required_after": "13:00"}, "free_until", "approval_required_after"),
        ({"maximum_time": "15:00"}, "approval_required_after", "maximum_time"),
    ])
    def test_times_out_of_order_are_refused_naming_both(self, changes, first, second):
        with pytest.raises(SpecError) as refused:
            self.typed(**changes)
        assert first in str(refused.value) and second in str(refused.value)

    def test_ties_are_allowed(self):
        """No approval band: D2 §1's property states approval_required_after == maximum."""
        assert self.typed(approval_required_after="18:00").undecided == ()

    def test_an_undecided_time_is_not_compared(self):
        """An undecided parameter is already a gap; comparing it would be reading null."""
        assert self.typed(free_until=None, charge_from="15:00").undecided == ("free_until",)

    def test_the_digest_follows_the_values(self):
        assert self.typed().digest == self.typed().digest
        assert self.typed().digest != self.typed(fee_per_hour={"amount": "30.00",
                                                               "currency": "USD"}).digest
        assert self.typed().digest != self.typed(free_until=None).digest

    def test_the_shipped_properties_decide_nothing(self):
        """The sandbox's policy is null (plan-v3 §5): nobody can decide a vendor test
        property's late-checkout policy, so every parameter is undecided - on both providers,
        because it is the same hotel."""
        for tenant_id in ("sandbox", "demo"):
            policy = load_policy(self.TEMPLATE, TenantConfig.load(tenant_id))
            assert policy.undecided == tuple(self.TEMPLATE.schema.parameters)

    def test_a_property_that_states_no_block_is_refused(self, tmp_path):
        spec = tmp_path / "spec"
        shutil.copytree(SPEC_DIR, spec, ignore=shutil.ignore_patterns("drafts"))
        path = spec / "tenants" / "sandbox.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["guest_services"]
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(SpecError, match="guest_services.LATE_CHECKOUT"):
            load_policy(load_template(spec_dir=spec), TenantConfig.load("sandbox", spec), spec)


# --------------------------------------------------------------------------- the fee
class TestTheFee:
    """D15: Money. The kernel has no multiplication and gains none - the fee is fee_per_hour
    added to itself once per charged hour."""

    @pytest.mark.parametrize("at, started, completed", [
        ("14:00", 0, 0), ("14:01", 1, 0), ("14:59", 1, 0), ("15:00", 1, 1),
        ("15:01", 2, 1), ("16:00", 2, 2), ("16:01", 3, 2), ("23:59", 10, 9),
    ])
    def test_charged_hours_under_each_rounding(self, at, started, completed):
        hour, minute = map(int, at.split(":"))
        asked = time(hour, minute)
        assert charged_hours(time(14, 0), asked, "started_hour") == started
        assert charged_hours(time(14, 0), asked, "completed_hour") == completed

    def test_no_charged_hours_is_no_fee_rather_than_a_fee_of_zero(self):
        assert fee_for(Money.parse("25.00", "USD"), 0) is None

    def test_the_fee_keeps_the_rates_currency_and_scale(self):
        fee = fee_for(Money.parse("25.00", "USD"), 3)
        assert fee == Money(Decimal("75.00"), "USD") and str(fee) == "75.00 USD"

    def test_the_fee_is_repeated_addition_not_multiplication(self, monkeypatch):
        """The kernel is unchanged: Money has no `__mul__`, and the fee does not need one."""
        assert not hasattr(Money, "__mul__")
        calls = []
        original = Money.plus

        def counted(self, other):
            calls.append(other)
            return original(self, other)

        monkeypatch.setattr(Money, "plus", counted)
        fee_for(Money.parse("25.00", "USD"), 4)
        assert len(calls) == 3

    def test_a_bad_rounding_is_refused_rather_than_defaulted(self):
        with pytest.raises(ValueError, match="nearest"):
            charged_hours(time(14, 0), time(15, 0), "nearest")
