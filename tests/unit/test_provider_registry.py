# -*- coding: utf-8 -*-
"""
The provider registry - every PMS the engine can speak to, discovered rather than listed.

The interesting assertion in this file is a negative one: `providers/registry.py` contains no
vendor name, and adding a PMS does not put one there. A dictionary of `{"somepms": SomeAdapter}`
would work and would also be the first place the canonical boundary leaks - the day a module
above an adapter can name a PMS is the day one of them starts getting special treatment.

That property is enforced for the engine as a whole by `test_canonical_boundary.py`. Here it is
checked at the seam where it would be most tempting to break.
"""
import ast
import pathlib

import pytest

from hotelcontrols.providers import registry
from hotelcontrols.providers.base import Provider

REGISTRY_SOURCE = pathlib.Path(registry.__file__)


class TestDiscovery:
    def test_more_than_one_provider_is_found(self):
        """The whole slice, in one assertion. Until this was true, portability was a claim."""
        assert len(registry.names()) >= 2, registry.names()

    def test_every_discovered_package_yields_something_satisfying_the_protocol(self):
        for package in registry.all_providers():
            adapter, source = package.build(_a_tenant_for(package))
            assert isinstance(adapter, Provider), package.name
            assert hasattr(source, "fetch")

    def test_a_package_registers_under_the_name_its_adapter_reports(self):
        """One name, in one place. A package whose directory and adapter disagreed would be
        addressable two ways and configurable one, which is how a tenant file ends up pointing
        at a provider that exists and cannot be built."""
        for package in registry.all_providers():
            assert package.adapter.name == package.name

    def test_a_default_capture_is_one_of_the_declared_captures(self):
        for package in registry.all_providers():
            assert package.default_capture in package.captures, package.name

    def test_providers_come_back_in_a_stable_order(self):
        """A run's output must not depend on filesystem iteration order."""
        assert registry.names() == tuple(sorted(registry.names()))
        assert [p.name for p in registry.all_providers()] == sorted(registry.names())


class TestRefusals:
    def test_an_unknown_provider_raises_naming_what_is_available(self):
        with pytest.raises(KeyError) as caught:
            registry.load("a-pms-nobody-has-written")
        for name in registry.names():
            assert name in str(caught.value)

    def test_a_package_that_declares_nothing_is_skipped_rather_than_breaking_discovery(self):
        """`transport/` will be such a package in slice 11: real code under `providers/` that
        is not an adapter. Discovery has to walk past it without comment."""
        assert all(hasattr(registry.load(name), "adapter") for name in registry.names())


class TestTheRegistryNamesNobody:
    """The negative assertion, and the reason this module exists at all."""

    def test_no_vendor_name_appears_in_the_registry_source(self):
        text = REGISTRY_SOURCE.read_text(encoding="utf-8")
        for name in registry.names():
            assert name not in text, (
                "%r appears in registry.py. A registry that names a provider is a registry a "
                "third provider has to be added to, which is the coupling this file exists to "
                "prevent" % name)

    def test_the_registry_holds_no_string_literal_that_could_become_one(self):
        """Checked over string constants the code EVALUATES, with docstrings excluded - the
        module explains the design at length in prose, and prose about why a value must not be
        hard-coded is not the value being hard-coded."""
        tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)}
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docstrings]
        for name in registry.names():
            assert not any(name in literal for literal in literals), name


def _a_tenant_for(package):
    """The property that runs this PMS, from `spec/tenants/` rather than from a table here."""
    from hotelcontrols.spec import TenantConfig
    spec = pathlib.Path(__file__).resolve().parents[2] / "spec"
    for path in sorted((spec / "tenants").glob("*.json")):
        tenant = TenantConfig.load(path.stem, spec)
        if tenant.provider == package.name:
            return tenant
    raise AssertionError("no tenant declares provider %r" % package.name)
