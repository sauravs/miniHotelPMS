# -*- coding: utf-8 -*-
"""
READINESS - which controls can this property actually run?

Review finding F8, and `control_rule_architecture.docx` sections 15 and 16 are explicit about
why it matters commercially:

    Control readiness: 1 of 2 evidence sources connected
    ...
    PMS evidence available: VIP + room. Inspection evidence unavailable.
    Connect housekeeping system to enable this control.

    Now the integration is driven by customer demand for a specific control, rather than by our
    roadmap guessing which integrations hotels need.

That is the whole argument for UNKNOWN being a first-class result rather than a limitation, and
v1 had every ingredient - `required_evidence[].source`, `resolvable` flags, provider coverage -
and surfaced none of it per control.

Readiness is computed from the SPEC alone: it says what a control COULD answer if it ran, not
what one run happened to find. A hotel deciding whether to connect a system needs the first.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..spec import ControlIR, Registry


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """One system a control needs evidence from, and how much of it is available."""

    name: str
    available: int
    total: int
    missing: tuple[str, ...] = ()

    @property
    def is_connected(self) -> bool:
        return self.available == self.total


@dataclass(frozen=True, slots=True)
class Readiness:
    """What a control can answer on one provider, before it is ever run."""

    control_id: str
    provider: str
    sources: tuple[EvidenceSource, ...] = ()
    unresolvable: tuple[str, ...] = ()
    tenant_supplied: tuple[str, ...] = ()

    @property
    def available(self) -> int:
        return sum(s.available for s in self.sources)

    @property
    def total(self) -> int:
        return sum(s.total for s in self.sources)

    @property
    def is_executable(self) -> bool:
        """Whether every field this control declares can be obtained at all."""
        return self.total > 0 and self.available == self.total

    @property
    def connected_sources(self) -> int:
        return sum(1 for s in self.sources if s.is_connected)

    @property
    def headline(self) -> str:
        """The line a customer reads next to the control's name."""
        if self.is_executable:
            return "%s: %d of %d fields available" % (self.provider, self.available, self.total)
        return ("%s: %d of %d fields available - %s"
                % (self.provider, self.available, self.total,
                   "connect a source for " + ", ".join(sorted(self.missing_fields))))

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(name for source in self.sources for name in source.missing)


def readiness(ir: ControlIR, provider_name: str, provider_map: dict,
              registry: Registry) -> Readiness:
    """What this control could answer on this provider, from the specification alone."""
    mapped = {m["canonical"] for m in provider_map["mappings"]}

    by_source: dict[str, list[tuple[str, bool]]] = {}
    unresolvable: list[str] = []
    tenant_supplied: list[str] = []

    for entry in ir["required_evidence"]:
        name, source = entry["field"], entry["source"]
        spec = registry.field(name) if registry.has(name) else None

        if source == "tenant":
            # The hotel supplies this rather than the PMS. Not a gap in the integration - it is
            # the "connect this to enable the control" path, and it is a different conversation
            # from a missing endpoint.
            tenant_supplied.append(name)
            by_source.setdefault(source, []).append((name, False))
            continue

        obtainable = name in mapped and (spec is None or spec.resolvable)
        if spec is not None and not spec.resolvable:
            unresolvable.append(name)
        by_source.setdefault(source, []).append((name, obtainable))

    sources = tuple(
        EvidenceSource(
            name=source,
            available=sum(1 for _f, ok in fields if ok),
            total=len(fields),
            missing=tuple(f for f, ok in fields if not ok))
        for source, fields in sorted(by_source.items()))

    return Readiness(ir.control_id, provider_name, sources,
                     tuple(sorted(unresolvable)), tuple(sorted(tenant_supplied)))
