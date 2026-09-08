# -*- coding: utf-8 -*-
"""
GATHER - one control's bounded population, with every record's evidence assembled.

    gather(ir, adapter, tenant, clock, budget) -> EvidenceSet

Three sources of evidence, in cost order, and the ordering IS the design:

    1. THE POPULATION RESPONSE      already fetched. Free.
    2. A REFERENCE                  one call per reference PER RUN, however many records want
                                    it. This is finding F1: the room master answers for all 111
                                    stays at once, and v1 had no way to say so.
    3. A PER-RECORD FOLLOW-UP       one call per record. R1: a folio takes one reservation per
                                    call and no bulk journal endpoint exists. This is the
                                    expensive one and the reason a population query exists.

Total cost is `1 + R + N`, asserted by counting invocations rather than assumed.

A BUNDLE IS ALWAYS COMPLETE IN SHAPE. Every declared field is present as a `Value`. Evidence we
could not obtain is an unknown Value carrying a reason, never a missing key - a caller that has
to remember which fields might be absent is a caller that will forget.

NOTHING HERE NAMES A PROVIDER, AN ENDPOINT OR A FIELD PATH. The tokens `source_key` and
`follow_up` are compared and passed back, never interpreted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel import Clock, Value
from ..providers.base import ProviderError
from ..spec import TenantConfig
from .budget import BudgetExceeded, CallBudget
from .cache import ResponseCache
from .population import build_request, population
from .reference import ReferenceIndex, build_references


@dataclass(frozen=True, slots=True)
class Bundle:
    """One record, and every canonical field the control asked for."""

    entity: str
    record_id: str | None
    fields: dict[str, Value]
    # Collection references, by entity: every related record's fields. Control 2 needs this -
    # "a room with an active closed window must not have an arriving reservation" is a question
    # about a room and the several segments booked into it.
    related: dict[str, tuple[dict[str, Value], ...]] = field(default_factory=dict)
    # Per referenced entity, whether the join actually MATCHED - as a three-valued answer:
    #   known(True)   the key matched a record in this property
    #   known(False)  the key was readable and matched nothing. A definite finding: control 1a
    #                 says a stay assigned to a room the master does not hold is a violation
    #   unknown(why)  the key was unreadable, or the reference could not be fetched at all
    # Kept separately from the resolved fields because "the room is not in the master" and "we
    # could not read the master" must never produce the same verdict.
    joins: dict[str, Value] = field(default_factory=dict)

    def unknown_fields(self) -> tuple[str, ...]:
        """What a verdict of UNKNOWN would cite."""
        return tuple(name for name, value in self.fields.items() if not value.is_known)

    def __repr__(self) -> str:
        return "Bundle(%s %s, %d fields, %d unknown)" % (
            self.entity, self.record_id, len(self.fields), len(self.unknown_fields()))


@dataclass(frozen=True, slots=True)
class EvidenceSet:
    """Everything one run gathered, and what it cost."""

    bundles: tuple[Bundle, ...]
    references: dict[str, ReferenceIndex] = field(default_factory=dict)
    calls: int = 0

    def __len__(self) -> int:
        return len(self.bundles)

    def __iter__(self):
        return iter(self.bundles)


def gather(ir, adapter, tenant: TenantConfig, clock: Clock,
           budget: CallBudget | None = None) -> EvidenceSet:
    """Fetch the population, the references, and each record's follow-ups."""
    budget = budget or CallBudget(tenant.call_budget)
    cache = ResponseCache(adapter.fetch, budget)

    records = population(ir, adapter, clock, cache)
    references = build_references(ir, adapter, cache)

    population_key = adapter.source_key_for_request(build_request(ir, adapter.name, clock))
    fields = [entry["field"] for entry in ir["required_evidence"]]

    bundles = []
    for record in records:
        identity = adapter.identity(record)
        bundles.append(Bundle(
            entity=ir["entity"],
            record_id=identity.payload if identity.is_known else None,
            fields=_assemble(fields, record, identity, adapter, references, cache,
                             population_key),
            related=_related(ir, record, adapter, references),
            joins=_joins(record, adapter, references)))

    return EvidenceSet(tuple(bundles), references, budget.spent)


# --------------------------------------------------------------------------- per record
def _assemble(fields, record, identity, adapter, references, cache, population_key):
    resolved: dict[str, Value] = {}
    for name in fields:
        entity = name.split(".")[0]
        reference = references.get(entity)

        if reference is not None:
            resolved[name] = _through_reference(name, record, identity, adapter, reference)
        elif adapter.source_key(name) == population_key:
            resolved[name] = adapter.resolve(name, record)
        else:
            resolved[name] = _follow_up(name, identity, adapter, cache)
    return resolved


def _through_reference(name, record, identity, adapter, reference) -> Value:
    """Resolve a field that lives on a referenced record."""
    provenance = adapter.provenance(name)

    if not reference.is_available:
        # Checked before anything else: an unavailable reference has no join key to read, and
        # asking for one would raise about a mapping when the real answer is "the hotel has not
        # connected this yet" (R13 / open question 1.6).
        return Value.unknown(reference.unavailable, source=provenance)

    if reference.kind == "set":
        # The whole collection, as one value. A membership predicate compares against it.
        return Value.known(reference.values, source=provenance)

    matches, reason = reference.match(_key_for(reference, record, adapter))
    if reason is not None:
        return Value.unknown(reason, source=provenance)
    # For a collection, the full set is exposed through `related`; reading one field scalar-wise
    # gives the first match, which is what a per-record predicate means by it.
    return adapter.resolve(name, matches[0])


def _key_for(reference, record, adapter) -> Value:
    """The value on THIS record that the reference joins on."""
    return adapter.resolve(reference.local_field, record)


def _follow_up(name, identity, adapter, cache) -> Value:
    """One extra call for one record - or a reasoned unknown if it cannot be made.

    A failure here degrades ONE bundle. The record stays in the population with that field
    unknown, because dropping it would report "nothing to see here" about a record we merely
    failed to look at.
    """
    # Provenance even on failure: an UNKNOWN has to say where the engine looked, or the hotel
    # cannot act on it.
    provenance = adapter.provenance(name)

    if not identity.is_known:
        return Value.unknown(
            "this evidence needs a per-record call, but the record's identity is not "
            "established (%s)" % identity.reason, risk="R1", source=provenance)

    request = adapter.follow_up(name, identity.payload)
    if request is None:
        return Value.unknown(
            "this evidence is not obtainable for a single record: its source answers for the "
            "whole property and this control declares no reference to join against",
            risk="R1", source=provenance)

    try:
        response = cache.get(request)
    except BudgetExceeded:
        # NOT an evidence gap, and it must not be caught here. A budget that degraded one
        # record instead of stopping the run would produce exactly the truncated population it
        # exists to prevent: "no violations" about records nobody looked at. It propagates.
        raise
    except ProviderError as exc:
        # The response is cached per request, so the reason names the response rather than
        # whichever field happened to trigger the call - every field from it shares the gap.
        return Value.unknown("the response carrying this evidence could not be fetched: %s"
                             % exc, risk="R1", source=provenance)
    return adapter.resolve(name, response)


def _joins(record, adapter, references) -> dict[str, Value]:
    """Whether each declared join matched, as its own three-valued answer."""
    joins: dict[str, Value] = {}
    for entity, index in references.items():
        if index.kind == "set":
            joins[entity] = Value.known(index.is_available)
            continue
        if not index.is_available:
            joins[entity] = Value.unknown(index.unavailable)
            continue
        key = _key_for(index, record, adapter)
        if not key.is_known:
            joins[entity] = Value.unknown(
                "the key this record joins on is not established (%s)" % key.reason)
            continue
        # The key is readable and either matches or does not. Both are definite answers.
        joins[entity] = Value.known(bool(index.by_key.get(str(key.payload))))
    return joins


def _related(ir, record, adapter, references) -> dict[str, tuple[dict[str, Value], ...]]:
    """Every record joined by a `collection` reference, with its own fields resolved."""
    related: dict[str, tuple[dict[str, Value], ...]] = {}
    for reference in ir.references:
        entity = reference["entity"]
        index = references.get(entity)
        if index is None or index.kind != "collection":
            continue
        if not index.is_available:
            related[entity] = ()
            continue
        matches, _reason = index.match(_key_for(index, record, adapter))
        wanted = [e["field"] for e in ir["required_evidence"]
                  if e["field"].split(".")[0] == entity]
        related[entity] = tuple(
            {name: adapter.resolve(name, match) for name in wanted} for match in matches)
    return related
