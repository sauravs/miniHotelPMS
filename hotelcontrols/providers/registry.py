# -*- coding: utf-8 -*-
"""
PROVIDER REGISTRY - every PMS this engine can speak to, discovered rather than listed.

    names()          -> every adapter's own name, in order
    load(name)       -> ProviderPackage
    all_providers()  -> every one, in name order

WHY DISCOVERY AND NOT A DICTIONARY
-----------------------------------
A dictionary would work, and it would also be the first place the canonical boundary leaked. A
module holding `{"somepms": SomePmsAdapter}` names a vendor in code the engine evaluates, which
is exactly what the boundary test forbids above `providers/<name>/` - and rightly, because the
day a layer can name a PMS is the day one of them starts getting special treatment.

So a provider package declares four names and this module finds them:

    ADAPTER           the adapter class.  ADAPTER(tenant, source) -> Provider
    FROZEN            the replay source.  FROZEN(capture) -> something with .fetch()
    CAPTURES          the bodies of evidence it can be replayed against
    DEFAULT_CAPTURE   which one to use when the caller does not say

There is no vendor name in this file, and adding a third PMS does not put one here. That is the
mechanical form of the claim slice 7 exists to make: a new PMS is a directory and a mapping
file, not an edit to anything above it.

WHY THE REPLAY SOURCE IS PART OF THE CONTRACT
----------------------------------------------
Because in this engine it is not a test fixture. Live transport is opt-in and off by default
(slice 11, criterion 11), so a frozen body of evidence is the ordinary way a provider is
consulted - and the contract suite needs to build every provider the same way to check that
they behave the same way.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any

# What a provider package must declare to be discoverable at all.
REQUIRED = ("ADAPTER", "FROZEN", "CAPTURES", "DEFAULT_CAPTURE")


@dataclass(frozen=True, slots=True)
class ProviderPackage:
    """One PMS adapter, and everything needed to run it against a body of evidence."""

    name: str
    adapter: Any
    frozen: Any
    captures: tuple[str, ...]
    default_capture: str

    def build(self, tenant, capture: str | None = None):
        """An adapter for this tenant, reading a frozen body of evidence.

        Returns the adapter and the source, because a caller needs both: the source is what
        knows which evidence a run used and whether it is real, and a run that cannot say that
        is not auditable.
        """
        source = self.frozen(capture or self.default_capture)
        return self.adapter(tenant, source), source

    def __repr__(self) -> str:
        return "ProviderPackage(%s)" % self.name


def _discover() -> dict[str, ProviderPackage]:
    """Import every sub-package that declares itself a provider.

    Imported rather than scanned as text: a package that declares the four names and cannot be
    imported is broken, and finding that out at startup is better than finding it out during a
    run. Packages that declare none are skipped silently - `transport/` will be one of them.
    """
    import hotelcontrols.providers as package

    found: dict[str, ProviderPackage] = {}
    for entry in pkgutil.iter_modules(package.__path__):
        if not entry.ispkg:
            continue
        module = importlib.import_module("%s.%s" % (package.__name__, entry.name))
        if not all(hasattr(module, name) for name in REQUIRED):
            continue
        adapter = module.ADAPTER
        found[adapter.name] = ProviderPackage(
            name=adapter.name,
            adapter=adapter,
            frozen=module.FROZEN,
            captures=tuple(module.CAPTURES),
            default_capture=module.DEFAULT_CAPTURE)
    return found


def names() -> tuple[str, ...]:
    """Every provider the engine can speak to, in name order."""
    return tuple(sorted(_discover()))


def load(name: str) -> ProviderPackage:
    """One provider by name.

    Raises for an unknown name rather than returning None. This value arrives from a URL and a
    tenant file, and "the provider you asked for does not exist" is a different thing from
    "the provider answered nothing" - conflating them sends somebody looking for missing data
    that was never the problem.
    """
    try:
        return _discover()[name]
    except KeyError:
        raise KeyError("no provider adapter called %r - the engine offers %s"
                       % (name, ", ".join(names()))) from None


def all_providers() -> tuple[ProviderPackage, ...]:
    """Every provider, in name order. What the contract suite runs against."""
    found = _discover()
    return tuple(found[name] for name in sorted(found))
