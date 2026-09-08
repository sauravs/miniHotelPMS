# -*- coding: utf-8 -*-
"""
THE CANONICAL BOUNDARY.

Everything above this package speaks canonical field names and nothing else - no endpoint, no
field path, no wire format, no vendor name. That is what makes a second PMS an adapter rather
than a rewrite, and it is enforced by a grep test over the source tree that is strict enough to
catch prose.

A provider adapter's whole job is to answer, for one canonical field and one record: what is
the value, or why can we not say? Everything MiniHotel-shaped - three date formats, a currency
that lives in a different part of the response from the amount it denominates, `0` meaning
"unconfigured", per-property status codes, where one record ends and the next begins - lives
below this line and stops existing above it.

`Response` and `Record` are deliberately opaque upwards. A caller may pass them back down and
may ask a `Record` for its identity, but it cannot read one, and `source_key` hands out a token
it is expected to compare rather than interpret.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..kernel import Value


@dataclass(frozen=True, slots=True)
class Request:
    """One call to a provider. `endpoint` and `params` are the provider's own vocabulary,
    carried as opaque data from the IR's population query."""

    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """A stable identity for caching, so one response is never fetched twice in a run."""
        return "%s|%s" % (self.endpoint, sorted_repr(self.params))


def sorted_repr(params: dict[str, Any]) -> str:
    """Order-independent rendering, so two equivalent requests share a cache entry."""
    if isinstance(params, dict):
        return "{%s}" % ",".join("%s:%s" % (k, sorted_repr(params[k])) for k in sorted(params))
    if isinstance(params, (list, tuple)):
        return "[%s]" % ",".join(sorted_repr(x) for x in params)
    return str(params)


class ProviderError(Exception):
    """The provider could not answer. Callers turn this into UNKNOWN, never into a verdict."""


class ResponseUnavailable(ProviderError):
    """The response could not be obtained - a network failure, or a fixture that was never
    captured. NOT an error condition in the ordinary sense: it is the evidence gap a control
    has to survive, and it degrades one record rather than a run."""


class RecordBoundaryUnknown(ProviderError):
    """This response cannot be cut into records of that entity.

    Named rather than a bare KeyError so a runner can report it as a run that could not be
    performed, instead of letting it escape as a stack trace. It is a gap in this engine, and
    the honest thing to do with a gap is to say which one it is.
    """


@runtime_checkable
class Provider(Protocol):
    """What every PMS adapter must offer. One shared contract suite runs against all of them."""

    name: str

    def fetch(self, request: Request) -> Any:
        """Perform one call and return an opaque response."""

    def records(self, response: Any, entity: str) -> list[Any]:
        """Cut a response into one record per `entity`."""

    def identity(self, record: Any) -> Value:
        """The record's own identifier, as a canonical value."""

    def resolve(self, field_name: str, record: Any) -> Value:
        """One canonical field's value for one record - or a reasoned admission."""

    def source_key(self, field_name: str) -> str:
        """An opaque token for "which call yields this field", so two fields from one response
        cost one call rather than two (R1). Callers compare it; they never interpret it."""

    def source_key_for_request(self, request: Request) -> str:
        """The same token for a call rather than a field, so the layer above can ask "is this
        field already in the response I hold?" without learning what either one is."""

    def follow_up(self, field_name: str, record_id: str) -> Request | None:
        """The call that fetches `field_name` for ONE record, or None if this field's source
        answers for the whole property and cannot be asked about a single record."""

    def reference_request(self, entity: str) -> Request | None:
        """The call that fetches the whole property's records of `entity`, for a join."""

    def provenance(self, field_name: str) -> str:
        """Where a field's evidence comes from, as it should read in an audit trail."""

    def events(self) -> tuple[str, ...]:
        """The events this PMS publishes, in CANONICAL names.

        A capability, not a wire detail: `reservation.updated` is the same fact on every system
        that has it, and an IR names those events without knowing which systems do. What
        differs is who publishes what - one PMS emits a dedicated room-occupancy event and
        another emits nothing when a room is taken out of service - and that difference decides
        whether a control runs in real time or on a timer.

        Read by `runner.scheduling.next_evaluation`, which falls back to the control's declared
        interval when an event is missing and SAYS which one. The alternative - assuming every
        provider publishes everything - produces a control that subscribes to a webhook nobody
        sends and never runs at all.
        """
