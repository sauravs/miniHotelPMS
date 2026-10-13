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

AN ABSENCE IS NOT A KEY (issue #86). `absent_means: "false"` makes a missing field a known
`False` - right for `exists` ("this stay is not yet assigned"), wrong as a key: stringified,
every absence is the same key "False", so an unassigned stay matched the one room with no number
and was judged on that room's evidence. An absent key is never indexed and never looked up.

A COLLECTION KNOWS WHAT IT IS COMPLETE FOR (issue #109, P2 and P3). A room's occupancy is many
segments over all of time, and no request asks for all of time (R8). So the rule's deployment
half declares the window a collection's ONE request asks (`population.reference_windows`), it
is resolved through the property clock, and the index records it - with the day it was asked.
Without that, "no segment overlaps the closure" would be a statement about whatever slice of
time the response happened to hold. And a remote record whose key cannot be READ is kept, as
UNPLACED: it may be any record's, so dropping it would make a room that looks empty read as one
that is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..kernel import NOT_APPLICABLE, Clock, Value
from ..providers.base import ProviderError
from ..spec import SpecError
from .budget import BudgetExceeded
from .population import resolve_dates


def absent_key(key: Value) -> bool:
    """A key the provider left empty, which the registry let through as a KNOWN answer.

    Both forms: known `False` (`absent_means: "false"`) and not applicable (R7's "no channel").
    Each is a fact about the record and each is the same for every record missing the field,
    which is exactly what disqualifies it as a key.
    """
    return key.is_known and (key.payload is False or key.payload is NOT_APPLICABLE)


@dataclass(frozen=True, slots=True)
class FetchedWindow:
    """The dates a collection was fetched for, both inclusive, and the property's day it was
    asked on - what a PASS over every record of it has to lie inside (#109, P3)."""

    start: str
    end: str
    asked_on: str

    def __str__(self) -> str:
        return "%s..%s" % (self.start, self.end)


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
    # A collection's window, when the rule declared one (#109). None: fetched for no window,
    # so complete for no question.
    window: FetchedWindow | None = None
    # Remote records whose key could not be read: each may belong to any local record.
    unplaced: tuple = ()

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
        if absent_key(key):
            # Neither a match nor a definite non-match: this record names no key at all. As
            # "False" it matched every remote record missing ITS key; as a non-match it read
            # like control 1a's violation about a room nobody named.
            return [], ("this record has no %s, so it joins to no %s record - an absence is "
                        "not a key" % (self.local_field or "join key", self.entity))
        found = self.by_key.get(str(key.payload))
        if not found:
            return [], ("no %s in this property matches %s - the join is reported rather than "
                        "guessed, because pairing the wrong records would put wrong evidence "
                        "behind a right-looking verdict" % (self.entity, key.payload))
        return found, None


def build_references(ir, adapter, cache, clock: Clock | None = None) -> dict[str, ReferenceIndex]:
    """Fetch and index every reference the control declares. One call each, at most."""
    indexes: dict[str, ReferenceIndex] = {}
    windows = (ir.get("population") or {}).get("reference_windows") or {}
    for reference in ir.references:
        entity, kind = reference["entity"], reference["kind"]
        window = reference_window(entity, windows, clock)

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

        request = reference_request(adapter, entity, window)
        if request is None:
            indexes[entity] = ReferenceIndex(
                entity, kind, unavailable=(
                    "this provider offers no way to retrieve %s records%s"
                    % (entity, " within a window of dates (%s)" % window if window else "")))
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
            unplaced: list[Any] = []
            for record in records:
                key = adapter.resolve(remote_field, record)
                if key.is_known and not absent_key(key):
                    by_key.setdefault(str(key.payload), []).append(record)
                elif not key.is_known:
                    # Not an absence, which is a fact ("this segment names no room"): a key
                    # nobody could read may be ANY record's. Kept, so a collection judged per
                    # record can see it; a lookup never matches it.
                    unplaced.append(record)
            indexes[entity] = ReferenceIndex(
                entity, kind, local_field=reference["local_field"],
                remote_field=remote_field, by_key=by_key, window=window,
                unplaced=tuple(unplaced))
    return indexes


def reference_request(adapter, entity: str, window: FetchedWindow | None):
    """The one request a reference makes: bounded to its window when the rule declares one.

    Shared with the probe's printed plan, so what a plan shows is what a run sends (#70).
    """
    if window is None:
        return adapter.reference_request(entity)
    return adapter.reference_request(entity, {"from": window.start, "to": window.end})


def reference_window(entity: str, windows: dict, clock: Clock | None) -> FetchedWindow | None:
    """The window this reference's request asks, resolved through the PROPERTY clock (F11)."""
    declared = windows.get(entity)
    if declared is None:
        return None
    if clock is None:
        # Never a guess at "today": a window resolved against the wrong day is a collection
        # complete for a question nobody asked.
        raise SpecError("the %s reference declares a window of relative dates, and resolving "
                        "it needs the property clock, which was not supplied" % entity)
    resolved = resolve_dates(declared, clock)
    return FetchedWindow(resolved["from"], resolved["to"], clock.today().isoformat())
