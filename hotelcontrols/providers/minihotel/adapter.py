# -*- coding: utf-8 -*-
"""
THE MINIHOTEL ADAPTER - canonical field in, Value out.

    resolve(field, record) -> Value

This is the entire interface the evidence layer sees. Above this call nothing knows that
MiniHotel exists, that responses are XML, that a balance is called TotalDebit, or that a room is
an rnm_struct_room.

DATA-DRIVEN BY DESIGN. It reads `spec/providers/minihotel.json` (where a field lives and how to
transform it) and `spec/canonical_fields.json` (what type it is and what its absence means) at
runtime. There is no field name in this file, and adding a twelfth control - or a second PMS -
must not require one.

FOUR RULES IT ENFORCES ON EVERY FIELD
-------------------------------------
  ABSENCE IS AN ANSWER, AND THE REGISTRY SAYS WHICH ONE. `absent_means` is per field: "unknown"
  is an evidence gap, "false" means the absence itself is the signal, "not_applicable" means a
  direct booking genuinely has no channel confirmation (R7). A missing field never returns
  None - None would be a second failure vocabulary, and the one callers forget to check.

  A PRESENT-BUT-EMPTY FIELD IS TREATED AS ABSENT. MiniHotel writes both `rateCode=""` and a
  self-closing `<rm_clsdt1 />`, and they mean the same thing.

  MONEY CARRIES ITS CURRENCY OR IT IS NOT EVIDENCE (R9). The currency lives in a different part
  of the response from the amount - reservation 007003199 is 870 USD while its own folio is
  3262.5 ILS - so the adapter fetches it and attaches it. If it cannot be established, the
  amount comes back UNKNOWN rather than as a bare number.

  A RECORD MAY READ UPWARDS, NEVER SIDEWAYS. See records.py.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from ...kernel import NOT_APPLICABLE, Money, Value
from ...spec import Registry, SpecError, TenantConfig
from ...spec.registry import SPEC_DIR
from ..base import ProviderError, Request
from .paths import find_elements, parse_document
from .records import IDENTITY_FIELD, Record, ancestry, record_tags, selector_for
from .transforms import TRANSFORMS, to_money
from . import paths as _paths

# Where a money field's currency comes from. `stay` has no currency of its own: the amount on a
# room stay is denominated in the reservation's, which sits on the <Booking> above the
# <RoomStay> block - hence the walk upwards.
CURRENCY_FIELD = {
    "reservation": "reservation.currency",
    "folio": "folio.currency",
    "stay": "reservation.currency",
}

# Which request parameter carries the record key, per endpoint. GetReservationBalance takes ONE
# reservation number per call and there is no bulk journal endpoint (R1) - so a control needing
# a folio costs one extra call per record. An endpoint absent from this table cannot be asked
# about a single record: it answers for the whole property, and the caller is told so.
KEY_PARAM = {"GetReservationBalance": "ReservationNumber"}

# The call that fetches a whole property's records of an entity, for a reference join. This is
# what makes the room master one call per RUN rather than one per record (finding F1).
REFERENCE_REQUEST = {
    "room": Request("getRooms", {}),
    "room_type": Request("getRoomTypes", {}),
    "occupancy": Request("RoomStatusInquiry", {}),
}


# The webhooks this PMS publishes, in canonical names. Taken from the vendor's own
# documentation and recorded in the IRs' execution rationales: reservation events, plus a
# dedicated room-occupancy one. There is NO event for a room being taken out of service, which
# is why `ooo_room_protection` is periodic rather than event-driven - a fact about this PMS
# that changes when a control runs and never what it answers.
PUBLISHED_EVENTS = ("reservation.created", "reservation.updated", "room.occupancy_updated")


class MiniHotelAdapter:
    """The provider adapter. One instance per tenant, because the status and department maps
    are the tenant's vocabulary rather than the provider's (A5)."""

    name = "minihotel"

    def __init__(self, tenant: TenantConfig, source, spec_dir: pathlib.Path | str = SPEC_DIR):
        spec_dir = pathlib.Path(spec_dir)
        provider = json.loads(
            (spec_dir / "providers" / "minihotel.json").read_text(encoding="utf-8"))
        self.mappings = {m["canonical"]: m for m in provider["mappings"]}
        self.registry = Registry.load(spec_dir)
        self.tenant = tenant
        # The transport. Injected rather than constructed, so this class cannot open a socket
        # and no test can make it (R8, criterion 11).
        self.source = source

    # ------------------------------------------------------------------ transport
    def fetch(self, request: Request) -> Record:
        body = self.source.fetch(request)
        return Record(request.endpoint, parse_document(body))

    def records(self, response: Record, entity: str) -> list[Record]:
        """Cut a response into one record per entity, each knowing what encloses it."""
        selector = selector_for(response.endpoint, entity)
        parent_of = ancestry(response.element)
        climbable = record_tags(response.endpoint)
        records = []
        for element in find_elements(response.element, selector):
            # Only RECORD-SHAPED ancestors, never list wrappers - see records.Record. A room
            # with no capacity block otherwise climbs into <ArrayOfRnm_struct_room> and reads
            # the next room's limit (R7, the same failure as borrowing a channel id).
            chain, node = [], parent_of.get(id(element))
            while node is not None and node is not response.element:
                if node.tag in climbable:
                    chain.append(node)
                node = parent_of.get(id(node))
            records.append(Record(response.endpoint, element, entity=entity,
                                  ancestors=tuple(chain)))
        return records

    # ------------------------------------------------------------------ resolution
    def identity(self, record: Record) -> Value:
        field_name = IDENTITY_FIELD.get(record.entity or "")
        if field_name is None:
            return Value.unknown("no identity field is defined for entity %r" % record.entity)
        return self.resolve(field_name, record)

    def resolve(self, field_name: str, record: Record) -> Value:
        """One canonical field for one record, reading upwards where the field belongs to a
        containing record - and never sideways (R7)."""
        mapping, spec = self._spec_for(field_name)
        source = self.provenance(field_name)

        if record.endpoint != mapping["endpoint"]:
            return Value.unknown(
                "%s is not available from this call" % field_name, source=source)

        # Walk outwards: this record first, then each element enclosing it, stopping before
        # the document root. The first one that actually holds the field answers.
        for element in record.lineage:
            raws = self._extract(mapping, element)
            if raws:
                return self._value(field_name, mapping, spec, raws[0], record, source)

        return self._absent(field_name, spec, source, present=False)

    def resolve_all(self, field_name: str, record: Record) -> list[Value]:
        """Every value of this field within one record - one per repeated element."""
        mapping, spec = self._spec_for(field_name)
        source = self.provenance(field_name)
        if record.endpoint != mapping["endpoint"]:
            return [Value.unknown("%s is not available from this call" % field_name,
                                  source=source)]
        raws = self._extract(mapping, record.element)
        if not raws:
            return [self._absent(field_name, spec, source, present=False)]
        return [self._value(field_name, mapping, spec, raw, record, source) for raw in raws]

    # ------------------------------------------------------------------ tokens for the layer above
    def provenance(self, field_name: str) -> str:
        """Where a field's evidence comes from, as it should read in an audit trail.

        This string is the one place a provider name crosses the canonical boundary, and it
        crosses as DATA: no PMS field path is in it, and no layer above parses it. An auditor
        has to know which system and which call produced a number.
        """
        if field_name not in self.mappings:
            # Not an error here, unlike source_key: the honest provenance of a field this
            # provider cannot supply at all is that we looked nowhere. R13's rate-plan fields
            # are the live case - the hotel supplies them or nobody does.
            return None
        return "pms:%s/%s" % (self.name, self.mappings[field_name]["endpoint"])

    def source_key_for_request(self, request: Request) -> str:
        """The same opaque token, for a call rather than a field.

        The evidence layer needs to ask "does this field come from the response I already
        have?" without learning what either of them is. Comparing two tokens answers that; it
        is the whole reason the token exists.
        """
        return request.endpoint

    def source_key(self, field_name: str) -> str:
        """An opaque token for "which call yields this field". Compared, never interpreted."""
        mapping, _ = self._spec_for(field_name)
        return mapping["endpoint"]

    def follow_up(self, field_name: str, record_id: str) -> Request | None:
        """The call fetching this field for ONE record, or None if its source answers for the
        whole property (R1)."""
        endpoint = self.source_key(field_name)
        parameter = KEY_PARAM.get(endpoint)
        if parameter is None:
            return None
        return Request(endpoint, {parameter: record_id})

    def reference_request(self, entity: str) -> Request | None:
        """The call fetching the whole property's records of an entity, for a join."""
        return REFERENCE_REQUEST.get(entity)

    def events(self) -> tuple[str, ...]:
        """The events this PMS publishes, in canonical names."""
        return PUBLISHED_EVENTS

    # ------------------------------------------------------------------ internals
    def _spec_for(self, field_name: str):
        try:
            mapping = self.mappings[field_name]
        except KeyError:
            raise SpecError("%r has no mapping for provider %r - a field the engine is asked "
                            "for but nobody told it where to find is a spec error, not an "
                            "evidence gap" % (field_name, self.name)) from None
        return mapping, self.registry.field(field_name)

    def _extract(self, mapping: dict[str, Any], element) -> list[str]:
        """Read a mapping's raw strings out of one element.

        The path is anchored to the element first: paths are written relative to the response,
        but records are cut deeper - an occupancy record IS a <Reservation>, so
        `Reservations/Reservation@ResNumber` has to start at the second segment or it looks for
        a container inside its own contents and finds nothing.
        """
        try:
            return _paths.find_all(element, _paths.anchor(mapping["path"], element.tag))
        except _paths.PathError as exc:
            raise SpecError("the mapping for %s is unusable: %s"
                            % (mapping["canonical"], exc)) from None

    def _value(self, field_name, mapping, spec, raw, record, source) -> Value:
        if not (raw or "").strip():
            # Present but empty. MiniHotel writes both forms and they mean the same thing.
            return self._absent(field_name, spec, source, present=True)

        unit = None
        if spec.is_money:
            currency = self._currency_for(field_name, record)
            if not currency.is_known:
                return Value.unknown(
                    "the amount is present but its currency could not be established (%s)"
                    % currency.reason, risk="R9", source=source)
            unit = currency.value if hasattr(currency, "value") else currency.payload
        elif spec.type == "integer":
            unit = "count"

        value = self._transform(mapping, raw, unit)

        # Where the registry and the provider map disagree, THE TYPE WINS.
        # reservation.total_amount is typed money and declares no transform, so identity would
        # hand back the string "870" - which compares as text, sorts as text, and would let an
        # amount reach a control without its currency (R9).
        if spec.is_money and value.is_known and not isinstance(value.payload, Money):
            value = to_money(str(value.payload), unit)

        risk = value.risk if value.risk is not None else (None if value.is_known else spec.risk)
        return Value(value.is_known, payload=value.payload, unit=value.unit,
                     reason=value.reason, risk=risk, source=source)

    def _transform(self, mapping, raw: str, unit: str | None) -> Value:
        name = mapping.get("transform")
        try:
            function = TRANSFORMS[name]
        except KeyError:
            # An unapplied transform is a wrong value that looks right, so this raises rather
            # than passing the raw string through.
            raise SpecError("the provider map names an unknown transform %r" % (name,)) from None
        if name == "tenant_status_map":
            return function(raw, unit, mapping=self.tenant.status_map)
        if name == "tenant_department_map":
            return function(raw, unit, mapping=self.tenant.department_map)
        return function(raw, unit)

    def _absent(self, field_name: str, spec, source: str, present: bool) -> Value:
        """What the registry says this field's absence means. Never None."""
        if spec.absent_means == "false":
            return Value.known(False, source=source)
        if spec.absent_means == "not_applicable":
            return Value.known(NOT_APPLICABLE, source=source)
        where = "present but empty in" if present else "absent from"
        return Value.unknown("%s is %s the provider response" % (field_name, where),
                             risk=spec.risk, source=source)

    def _currency_for(self, field_name: str, record: Record) -> Value:
        """Find the currency an amount is denominated in, walking outwards from the record.

        R9 is why this is not a constant: reservation 007003199 reports 870 USD while its own
        folio reports 3262.5 ILS, in the same property, on the same reservation.
        """
        entity = field_name.split(".")[0]
        currency_field = CURRENCY_FIELD.get(entity)
        if currency_field is None:
            return Value.unknown("no currency field is defined for %r" % entity, risk="R9")
        found = self.resolve(currency_field, record)
        if found.is_known:
            return Value.known(found.payload)
        return Value.unknown("%s could not be resolved" % currency_field, risk="R9")
