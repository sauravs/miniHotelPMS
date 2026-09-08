# -*- coding: utf-8 -*-
"""
REFERENCES - joining a record to property-wide data.

This module is review finding F1, the largest functional gap in v1. Three of its controls
returned **111 UNKNOWN out of 111 records** because a stay could never be joined to the room it
was assigned. The evidence was not missing: `room.max_guests.adults` sits in a response that
costs ONE call for the whole property. There was simply no way to say so.

Now the IR says so, and this builds it:

    lookup      one remote record per key      a stay's assigned room
    collection  every remote record per key    a room's occupancy segments
    set         every value of one field       all defined room-type codes

COST: ONE CALL PER REFERENCE PER RUN. Not per record. The room master is fetched once and
answers for all 111 stays, which is the difference between `1 + R + N` and `1 + N + N`.

A JOIN NEVER INVENTS A MATCH. If the key is unknown, or matches nothing, the answer is UNKNOWN
with that reason - never the first plausible record. Wrong evidence behind a right-looking
verdict is the worst thing this engine can produce, and it is worse than answering nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel import Value
from ..providers.base import ProviderError
from .budget import BudgetExceeded


@dataclass(frozen=True, slots=True)
class ReferenceIndex:
    """One resolved reference: the remote records, indexed by the key they join on."""

    entity: str
    kind: str
    local_field: str | None = None
    remote_field: str | None = None
    by_key: dict[str, list[Any]] = field(default_factory=dict)
    values: tuple = ()
    unavailable: str | None = None

    @property
    def is_available(self) -> bool:
        return self.unavailable is None

    def match(self, key: Value) -> tuple[list[Any], str | None]:
        """The remote records for this key, or a reason there are none.

        Returns `(records, reason)` - exactly one of which is meaningful - so the caller cannot
        mistake "no match" for "matched nothing useful".
        """
        if self.unavailable is not None:
            return [], self.unavailable
        if not key.is_known:
            return [], ("the key this record joins on is not established (%s)" % key.reason)
        found = self.by_key.get(str(key.payload))
        if not found:
            return [], ("no %s in this property matches %s - the join is reported rather than "
                        "guessed, because pairing the wrong records would put wrong evidence "
                        "behind a right-looking verdict" % (self.entity, key.payload))
        return found, None


def build_references(ir, adapter, cache) -> dict[str, ReferenceIndex]:
    """Fetch and index every reference the control declares. One call each, at most."""
    indexes: dict[str, ReferenceIndex] = {}
    for reference in ir.references:
        entity, kind = reference["entity"], reference["kind"]

        if reference.get("source") == "tenant":
            # The hotel supplies this, not the PMS. R13 is the live example: a reservation's
            # rate code and the provider's price-list code are different key spaces, so no
            # endpoint can resolve it. Answering UNKNOWN with that reason IS the product's
            # "connect this to enable the control" path.
            indexes[entity] = ReferenceIndex(
                entity, kind, unavailable=(
                    "%s is supplied by the property rather than by the PMS, and this property "
                    "has not supplied it" % entity))
            continue

        request = adapter.reference_request(entity)
        if request is None:
            indexes[entity] = ReferenceIndex(
                entity, kind, unavailable=(
                    "this provider offers no way to retrieve %s records" % entity))
            continue

        try:
            response = cache.get(request)
            records = adapter.records(response, entity)
        except BudgetExceeded:
            # A budget stop ends the run. Degrading the reference instead would let every
            # record report "the join was unavailable" for a run that simply ran out of calls.
            raise
        except ProviderError as exc:
            # A reference that cannot be fetched degrades every record's join to UNKNOWN, with
            # the reason - it does not stop the run, and it never silently becomes an empty set
            # that would make every membership test fail.
            indexes[entity] = ReferenceIndex(
                entity, kind, unavailable="the %s reference could not be fetched: %s"
                                          % (entity, exc))
            continue

        if kind == "set":
            resolved = [adapter.resolve(reference["field"], record) for record in records]
            indexes[entity] = ReferenceIndex(
                entity, kind,
                values=tuple(v.payload for v in resolved if v.is_known))
        else:
            remote_field = reference["remote_field"]
            by_key: dict[str, list[Any]] = {}
            for record in records:
                key = adapter.resolve(remote_field, record)
                if key.is_known:
                    by_key.setdefault(str(key.payload), []).append(record)
            indexes[entity] = ReferenceIndex(
                entity, kind, local_field=reference["local_field"],
                remote_field=remote_field, by_key=by_key)
    return indexes
