# -*- coding: utf-8 -*-
"""
REGISTRY - the canonical vocabulary a rule is allowed to use.

This is what makes "the rule never names a PMS" enforceable rather than aspirational. A control
may reference `folio.balance_due`. It may not reference whatever one vendor happens to call
that field, because that is one
vendor's spelling - and it may not reference `reservation.vip` either, because nobody has
defined what that would mean or where it would come from.

That second refusal is the guard rail `control_rule_architecture.docx` section 17 asks for, and
it is the reason a compiler can be added later without being dangerous. Fed the doc's own
example sentence - "All VIP arrivals should have an assigned room that is clean by 2 PM" - the
validator answers with the two canonical fields that do not exist, rather than producing a rule
that runs and quietly answers about nothing.

`absent_means` is the interesting column, and it is PER FIELD:

    unknown          the field should be there and is not - an evidence gap
    false            its absence IS the signal (control 15 tests exactly that)
    not_applicable   there genuinely is no such thing for this record (R7)

Getting it wrong in either direction is a wrong verdict. Treating an absent portal id as an
evidence gap makes every direct booking UNKNOWN; treating it as an empty string makes every
direct booking a duplicate of every other one.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Iterable

from .errors import SpecError

SPEC_DIR = pathlib.Path(__file__).resolve().parents[2] / "spec"

# What a missing value is allowed to mean. Three, and no more: a fourth would be a fourth
# thing every caller has to remember to handle.
ABSENT_MEANS = ("unknown", "false", "not_applicable")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One canonical field: what it is, and what its absence means."""

    field: str
    type: str
    absent_means: str = "unknown"
    description: str = ""
    risk: str | None = None
    resolvable: bool = True
    tenant_setting: str | None = None

    @property
    def entity(self) -> str:
        return self.field.split(".", 1)[0]

    @property
    def is_money(self) -> bool:
        """Money fields are the ones that must carry a currency or not exist (R9)."""
        return self.type == "money"


@dataclass(frozen=True, slots=True)
class Registry:
    """Every canonical field, indexed by name. Loaded once, then read-only."""

    _fields: dict[str, FieldSpec]
    version: int = 2

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, spec_dir: pathlib.Path | str = SPEC_DIR) -> Registry:
        path = pathlib.Path(spec_dir) / "canonical_fields.json"
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Registry:
        fields: dict[str, FieldSpec] = {}
        for entity, declared in raw.get("entities", {}).items():
            for item in declared:
                spec = FieldSpec(
                    field=item["field"],
                    type=item["type"],
                    absent_means=item.get("absent_means", "unknown"),
                    description=item.get("description", ""),
                    risk=item.get("risk"),
                    resolvable=item.get("resolvable", True),
                    tenant_setting=item.get("tenant_setting"),
                )
                if spec.absent_means not in ABSENT_MEANS:
                    raise SpecError(
                        "%s declares absent_means=%r, which is not one of %s - and what a "
                        "missing value means is a verdict-level decision, not a default"
                        % (spec.field, spec.absent_means, ", ".join(ABSENT_MEANS)))
                if spec.entity != entity:
                    raise SpecError(
                        "%s is declared under entity %r but its name says %r"
                        % (spec.field, entity, spec.entity))
                fields[spec.field] = spec
        return cls(_fields=fields, version=raw.get("version", 2))

    # ------------------------------------------------------------------ reading
    def field(self, name: str) -> FieldSpec:
        """One field's specification, or a SpecError naming what is missing.

        Raises rather than returning None: a field nobody declared is a broken rule, and a
        broken rule must not be able to masquerade as a hotel whose data is incomplete.
        """
        try:
            return self._fields[name]
        except KeyError:
            raise SpecError(
                "%r is not a canonical field. A control may reference only the declared "
                "vocabulary - if this field is real, declare it in canonical_fields.json and "
                "map it for at least one provider first" % (name,)) from None

    def has(self, name: str) -> bool:
        return name in self._fields

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(self._fields)

    @property
    def entities(self) -> frozenset[str]:
        return frozenset(spec.entity for spec in self._fields.values())

    def of_entity(self, entity: str) -> tuple[FieldSpec, ...]:
        return tuple(s for s in self._fields.values() if s.entity == entity)

    def unresolvable(self) -> tuple[FieldSpec, ...]:
        """Fields no provider we have can supply.

        A property of the vocabulary, not a discovery to be made mid-run. `rate_plan.*` is the
        live example: a reservation's rate code and the ARI price-list code are different key
        spaces (R13), so control 9's evidence has to come from the hotel or not at all.
        """
        return tuple(s for s in self._fields.values() if not s.resolvable)

    def __len__(self) -> int:
        return len(self._fields)

    def __iter__(self) -> Iterable[FieldSpec]:
        return iter(self._fields.values())


def provider_map(name: str, spec_dir: pathlib.Path | str = SPEC_DIR) -> dict[str, Any]:
    """One provider's canonical-field map, as data.

    Which fields a given PMS can supply is a question the readiness report asks and the page
    answers, and both live above the provider layer. The NAME arrives from the provider
    registry, which discovers adapters by import - so nothing here spells a vendor out, and a
    third PMS is readable from the moment its directory exists.
    """
    path = pathlib.Path(spec_dir) / "providers" / ("%s.json" % name)
    if not path.is_file():
        raise SpecError(
            "no provider map for %r in %s - an adapter without one can resolve nothing, and a "
            "readiness report about it would be a report about an empty dictionary"
            % (name, path.parent))
    return json.loads(path.read_text(encoding="utf-8"))
