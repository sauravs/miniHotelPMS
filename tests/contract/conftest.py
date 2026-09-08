# -*- coding: utf-8 -*-
"""
One suite, run against EVERY registered provider.

This is the piece v1 did not have and the one that makes criterion 7 real. Everything here is
parameterised over `providers.registry.all_providers()`, so adding a third PMS means running an
existing suite rather than writing a new one - and a PMS that quietly breaks the contract is
caught by tests nobody had to remember to write for it.

Nothing in this directory names a provider, an endpoint or a wire format. Canonical field names
DO appear, and they are supposed to: that vocabulary is the contract. The whole point is that a
sentence like "a field whose absence is not applicable resolves to the sentinel, on every
provider" can be written once and be true everywhere.

Which tenant goes with which provider is read from `spec/tenants/*.json`, where each property
declares the PMS it runs on. So a third adapter needs a tenant file, not an edit here.
"""
import pathlib

import pytest

from hotelcontrols.evidence import CallBudget, gather
from hotelcontrols.kernel import FixedClock
from hotelcontrols.providers.base import ProviderError
from hotelcontrols.providers.registry import all_providers
from hotelcontrols.spec import TenantConfig, available, load

SPEC = pathlib.Path(__file__).resolve().parents[2] / "spec"

# The instant every provider is asked about. Both bodies of evidence describe the same hotel in
# the same week, so one clock serves both - and using one is what makes a difference between
# them a difference in the ADAPTER rather than in the question.
AS_OF = "2026-07-08T09:00"


class Subject:
    """One provider, wired to the property that runs it, over its default evidence."""

    def __init__(self, package):
        self.package = package
        self.name = package.name
        self.tenant = _tenant_for(package.name)
        self.adapter, self.source = package.build(self.tenant)
        self.clock = FixedClock.at(AS_OF, self.tenant.timezone)

    def bundles(self):
        """Every control's evidence, gathered once.

        Controls this body of evidence cannot answer are skipped by name rather than silently:
        a provider refusing a question it cannot answer is the contract working, and the
        refusal itself is asserted in `TestRefusals`.
        """
        found = []
        for control_id in available():
            adapter, _source = self.package.build(self.tenant)
            try:
                evidence = gather(load(control_id), adapter, self.tenant,
                                  self.clock, CallBudget(400))
            except ProviderError:
                continue
            found.extend((control_id, bundle) for bundle in evidence.bundles)
        return found

    def __repr__(self):
        return "Subject(%s)" % self.name


def _tenant_for(provider_name: str) -> TenantConfig:
    """The property that runs this PMS, from the tenant files rather than from a table here."""
    for path in sorted((SPEC / "tenants").glob("*.json")):
        tenant = TenantConfig.load(path.stem, SPEC)
        if tenant.provider == provider_name:
            return tenant
    raise AssertionError(
        "no tenant in spec/tenants/ declares provider %r - a provider the engine offers and no "
        "property runs cannot be exercised by this suite, which is how an adapter rots"
        % provider_name)


@pytest.fixture(scope="session", params=[p.name for p in all_providers()])
def provider(request):
    """Every registered provider, one test run each."""
    return Subject(next(p for p in all_providers() if p.name == request.param))


@pytest.fixture(scope="session")
def bundles(provider):
    """Every bundle this provider produces, across every control it can answer."""
    return provider.bundles()
