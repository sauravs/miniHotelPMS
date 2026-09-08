# -*- coding: utf-8 -*-
"""
Readiness - which controls can this property actually run, before running anything?

Review finding F8. `control_rule_architecture.docx` sections 15-16 build the whole integration
strategy on it:

    Control readiness: 1 of 2 evidence sources connected
    ...
    Connect housekeeping system to enable this control.
    Now the integration is driven by customer demand for a specific control, rather than by our
    roadmap guessing which integrations hotels need.

v1 had every ingredient - `required_evidence[].source`, `resolvable` flags, provider coverage -
and surfaced none of it per control.

Readiness is computed from the SPEC ALONE. It says what a control COULD answer if it ran, not
what one run happened to find, because a hotel deciding whether to connect a system needs the
first.
"""
import json
import pathlib

import pytest

from hotelcontrols.runner import readiness
from hotelcontrols.spec import Registry, load

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"


@pytest.fixture(scope="module")
def provider_map():
    return json.loads((SPEC / "providers" / "minihotel.json").read_text())


@pytest.fixture(scope="module")
def registry():
    return Registry.load()


class TestAnExecutableControl:
    def test_a_control_whose_evidence_is_all_mapped_is_executable(self, provider_map,
                                                                  registry):
        report = readiness(load("checkout_money_owed"), "minihotel", provider_map, registry)
        assert report.is_executable
        assert report.available == report.total
        assert "of %d fields available" % report.total in report.headline

    def test_it_groups_by_the_system_the_evidence_comes_from(self, provider_map, registry):
        """'1 of 2 evidence sources connected' is the sentence the doc asks for, and it needs
        the fields grouped by which system holds them."""
        report = readiness(load("checkout_money_owed"), "minihotel", provider_map, registry)
        assert {source.name for source in report.sources} == {"pms"}
        assert report.connected_sources == 1


class TestAControlThisProviderCannotRun:
    def test_control_nine_is_not_executable_and_names_what_is_missing(self, provider_map,
                                                                      registry):
        """R13. A reservation's rate code and the provider's price-list code are different key
        spaces, so no endpoint resolves the mapping. This is the 'connect this to enable the
        control' path rather than a wrong verdict."""
        report = readiness(load("rate_room_category_consistency"), "minihotel", provider_map,
                           registry)
        assert not report.is_executable
        assert "rate_plan.permitted_room_types" in report.missing_fields
        assert "connect a source for" in report.headline

    def test_it_separates_tenant_supplied_evidence_from_a_missing_integration(
            self, provider_map, registry):
        """Different conversations. 'The PMS has no endpoint for this' goes to the vendor;
        'the hotel has not told us its rate plans' goes to the hotel."""
        report = readiness(load("rate_room_category_consistency"), "minihotel", provider_map,
                           registry)
        assert "rate_plan.code" in report.tenant_supplied
        assert "tenant" in {source.name for source in report.sources}

    def test_an_unresolvable_field_is_reported_as_such(self, provider_map, registry):
        report = readiness(load("rate_room_category_consistency"), "minihotel", provider_map,
                           registry)
        assert report.unresolvable


class TestEveryShippedControl:
    @pytest.mark.parametrize("control_id", sorted(
        __import__("hotelcontrols.spec", fromlist=["available"]).available()))
    def test_readiness_can_be_computed_without_running_anything(self, control_id,
                                                                provider_map, registry):
        report = readiness(load(control_id), "minihotel", provider_map, registry)
        assert report.total > 0
        assert 0 <= report.available <= report.total
        assert report.headline

    def test_most_controls_are_executable_on_this_provider(self, provider_map, registry):
        """The commercial headline. Of the eleven shipped, only the rate-plan control needs
        evidence MiniHotel structurally cannot supply."""
        from hotelcontrols.spec import available
        executable = [c for c in available()
                      if readiness(load(c), "minihotel", provider_map, registry).is_executable]
        assert len(executable) >= 10
