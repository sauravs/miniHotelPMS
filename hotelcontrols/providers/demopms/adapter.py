# -*- coding: utf-8 -*-
"""
THE DEMOPMS ADAPTER - canonical field in, Value out.

    resolve(field, record) -> Value

The same interface the other adapter offers, and the reason this slice exists. Above this call
nothing knows that DemoPMS exists, that responses are JSON, that a balance lives at
`ledger.balance`, or that occupancy is nested inside a room rather than listed beside it.

Adding this provider required no change to the kernel, the spec layer, the evidence layer, the
evaluator, the runner or the store. What it required was a directory here, a mapping file in
`spec/providers/`, a tenant file in `spec/tenants/`, and one more key in each control's
`population.provider_query` - all of them data. That claim is the thesis of the whole
architecture, and it is only worth something because it is checked: the contract suite in
`tests/contract/` runs the same assertions against every registered provider, and the end-to-end
suite runs the same eleven IRs over the same logical hotel through both.

DATA-DRIVEN BY DESIGN, exactly as the other adapter is. It reads `spec/providers/demopms.json`
and `spec/canonical_fields.json` at runtime; there is no canonical field name in this file.

FOUR RULES IT ENFORCES ON EVERY FIELD - the same four, differently spelled
--------------------------------------------------------------------------
  ABSENCE IS AN ANSWER, AND THE REGISTRY SAYS WHICH ONE. A missing field never returns None.

  A PRESENT-BUT-NULL FIELD IS TREATED AS ABSENT. DemoPMS writes `null`; MiniHotel writes
  `<x />` and `rateCode=""`. All three mean the same thing, and the registry decides what that
  thing implies per field.

  MONEY CARRIES ITS CURRENCY OR IT IS NOT EVIDENCE (R9). Here the currency travels inside the
  amount's own object, so unlike the other adapter this one never goes hunting for it - and a
  money-typed field mapped to a transform that cannot produce `Money` is refused as a SPEC
  ERROR rather than quietly handing a control a bare string.

  A RECORD MAY READ UPWARDS, NEVER SIDEWAYS. See records.py and `paths.strip_prefix`.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from ...kernel import NOT_APPLICABLE, Money, Value
from ...spec import Registry, SpecError, TenantConfig
from ...spec.registry import SPEC_DIR
from ..base import Request
from .paths import PathError, find_all, parse_document, strip_prefix
from .records import IDENTITY_FIELD, Record, cut
from .transforms import MONEY_TRANSFORMS, TRANSFORMS

# Which request parameter carries the record key, per endpoint. A ledger takes ONE booking per
# call and there is no bulk journal endpoint - the same cost shape as the real PMS (R1), and
# not a coincidence: it is the constraint the population query exists to bound, so a second
# provider that did not have it would let the whole design go untested.
KEY_PARAM = {"ledger": "booking_ref"}

# The call that fetches a whole property's records of an entity, for a reference join. One call
# per reference PER RUN, however many records need it (finding F1).
REFERENCE_REQUEST = {
    "room": Request("rooms", {}),
    "room_type": Request("room-types", {}),
    "occupancy": Request("occupancy", {}),
}


class DemoPmsAdapter:
    """The provider adapter. One instance per tenant, because the status and department maps
    are the tenant's vocabulary rather than the provider's (A5)."""

    name = "demopms"

    def __init__(self, tenant: TenantConfig, source, spec_dir: pathlib.Path | str = SPEC_DIR):
        spec_dir = pathlib.Path(spec_dir)
        provider = json.loads(
            (spec_dir / "providers" / "demopms.json").read_text(encoding="utf-8"))
        self.mappings = {m["canonical"]: m for m in provider["mappings"]}
        self.registry = Registry.load(spec_dir)
        self.tenant = tenant
        # The transport. Injected rather than constructed, so this class cannot open a socket
        # and no test can make it (R8, criterion 11).
        self.source = source

    # ------------------------------------------------------------------ transport
    def fetch(self, request: Request) -> Record:
        return Record(request.endpoint, parse_document(self.source.fetch(request)))

    def records(self, response: Record, entity: str) -> list[Record]:
        """Cut a response into one record per entity, each knowing what encloses it."""
        return cut(response.node, response.endpoint, entity)

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

        # Walk outwards: this record first, then each object enclosing it. A path that belongs
        # to neither is skipped rather than read - `strip_prefix` is what says so.
        for prefix, node in record.lineage:
            raws = self._extract(mapping, prefix, node)
            if raws:
                return self._value(field_name, mapping, spec, raws[0], source)

        return self._absent(field_name, spec, source, present=False)

    def resolve_all(self, field_name: str, record: Record) -> list[Value]:
        """Every value of this field within one record - one per repeated element."""
        mapping, spec = self._spec_for(field_name)
        source = self.provenance(field_name)
        if record.endpoint != mapping["endpoint"]:
            return [Value.unknown("%s is not available from this call" % field_name,
                                  source=source)]
        raws = self._extract(mapping, record.prefix, record.node)
        if not raws:
            return [self._absent(field_name, spec, source, present=False)]
        return [self._value(field_name, mapping, spec, raw, source) for raw in raws]

    # ------------------------------------------------------------------ tokens for the layer above
    def provenance(self, field_name: str) -> str | None:
        """Where a field's evidence comes from, as it should read in an audit trail.

        This string is the one place a provider name crosses the canonical boundary, and it
        crosses as DATA: no field path is in it, and no layer above parses it. An auditor has to
        know which system and which call produced a number.
        """
        if field_name not in self.mappings:
            # Not an error here, unlike source_key: the honest provenance of a field this
            # provider cannot supply at all is that we looked nowhere.
            return None
        return "pms:%s/%s" % (self.name, self.mappings[field_name]["endpoint"])

    def source_key_for_request(self, request: Request) -> str:
        """The same opaque token, for a call rather than a field."""
        return request.endpoint

    def source_key(self, field_name: str) -> str:
        """An opaque token for "which call yields this field". Compared, never interpreted."""
        mapping, _ = self._spec_for(field_name)
        return mapping["endpoint"]

    def follow_up(self, field_name: str, record_id: str) -> Request | None:
        """The call fetching this field for ONE record, or None if its source answers for the
        whole property (R1)."""
        parameter = KEY_PARAM.get(self.source_key(field_name))
        if parameter is None:
            return None
        return Request(self.source_key(field_name), {parameter: record_id})

    def reference_request(self, entity: str) -> Request | None:
        """The call fetching the whole property's records of an entity, for a join."""
        return REFERENCE_REQUEST.get(entity)

    # ------------------------------------------------------------------ internals
    def _spec_for(self, field_name: str):
        try:
            mapping = self.mappings[field_name]
        except KeyError:
            raise SpecError("%r has no mapping for provider %r - a field the engine is asked "
                            "for but nobody told it where to find is a spec error, not an "
                            "evidence gap" % (field_name, self.name)) from None
        spec = self.registry.field(field_name)

        # THE TYPE AND THE TRANSFORM MUST AGREE, and the disagreement is a spec error rather
        # than an evidence gap. A money-typed field mapped to a transform that returns a string
        # would hand a control an amount with no currency - which is R9 happening again, one
        # layer further down, and it would look exactly like a working mapping.
        is_money_transform = mapping.get("transform") in MONEY_TRANSFORMS
        if spec.is_money != is_money_transform:
            raise SpecError(
                "%s is declared %s in the registry but mapped to the transform %r - a "
                "money-typed field needs a transform that produces an amount with its "
                "currency, and only such a field may have one (R9)"
                % (field_name, spec.type, mapping.get("transform")))
        return mapping, spec

    def _extract(self, mapping: dict[str, Any], prefix: str, node: Any) -> list[Any] | None:
        """Read a mapping's raw values out of one node, or None if the path is not readable
        from here at all.

        The path is written from the response root and the node may sit deep inside it, so it
        is anchored first. `strip_prefix` returning None means the path addresses a different
        branch entirely, which is a record being asked for a value that is not its to give.
        """
        relative = strip_prefix(mapping["path"], prefix)
        if relative is None:
            return None
        if relative == "":
            # The record IS the value this path addresses - a folio record cut at `ledger`.
            return [node]
        try:
            return find_all(node, relative)
        except PathError as exc:
            raise SpecError("the mapping for %s is unusable: %s"
                            % (mapping["canonical"], exc)) from None

    def _value(self, field_name, mapping, spec, raw, source) -> Value:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            # Present but empty. DemoPMS writes null where the other provider writes an empty
            # element, and both mean "there is a slot here and nobody filled it".
            return self._absent(field_name, spec, source, present=True)

        value = self._transform(mapping, raw, "count" if spec.type == "integer" else None)

        # Belt and braces on the money rule. `_spec_for` already refuses a money field mapped
        # to a non-money transform; this catches a money transform that somehow returned
        # something else, because a bare number reaching a control is the one outcome R9 is
        # about and it must not depend on two separate things both being right.
        if spec.is_money and value.is_known and not isinstance(value.payload, Money):
            raise SpecError(
                "%s resolved to %r rather than an amount with its currency (R9)"
                % (field_name, value.payload))

        risk = value.risk if value.risk is not None else (None if value.is_known else spec.risk)
        return Value(value.is_known, payload=value.payload, unit=value.unit,
                     reason=value.reason, risk=risk, source=source)

    def _transform(self, mapping, raw: Any, unit: str | None) -> Value:
        name = mapping.get("transform")
        try:
            function = TRANSFORMS[name]
        except KeyError:
            # An unapplied transform is a wrong value that looks right, so this raises rather
            # than passing the raw value through.
            raise SpecError("the provider map names an unknown transform %r" % (name,)) from None
        if name == "tenant_status_map":
            return function(raw, unit, mapping=self.tenant.status_map)
        if name == "tenant_department_map":
            return function(raw, unit, mapping=self.tenant.department_map)
        return function(raw, unit)

    def _absent(self, field_name: str, spec, source: str | None, present: bool) -> Value:
        """What the registry says this field's absence means. Never None."""
        if spec.absent_means == "false":
            return Value.known(False, source=source)
        if spec.absent_means == "not_applicable":
            return Value.known(NOT_APPLICABLE, source=source)
        where = "present but empty in" if present else "absent from"
        return Value.unknown("%s is %s the provider response" % (field_name, where),
                             risk=spec.risk, source=source)
