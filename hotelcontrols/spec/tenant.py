# -*- coding: utf-8 -*-
"""
TENANT CONFIGURATION - one hotel's vocabulary and policy, as data.

This module is the answer to v1's open question 1.4 and the fix for review finding F12. In v1
the reservation-status map and the folio-department map were dictionaries inside a provider
module, so onboarding a second property meant editing Python and deploying it.

But those maps are not the provider's API surface. MiniHotel lets each property customise its
own status codes and posting categories (A5). The provider map describes an API; this describes
a hotel. Keeping them apart is what lets one adapter serve every property on that PMS.

Also here: everything a control needs that only the hotel can supply - its timezone (F11), its
call budget (R1/R8), the rate codes it has nominated for control 15, and the rate-plan mapping
MiniHotel structurally cannot resolve (R13).

THE RULE THIS FILE EXISTS TO PROTECT
------------------------------------
A code that is not in the map resolves to UNKNOWN. Never a guess. Across every capture, 44 of
217 distinct reservations - one in five - carry a status documented nowhere (`OK4`, `WL`).
Silently mapping one of those to something plausible would include or exclude reservations from
a control's scope invisibly, which is the quietest possible way for this system to be wrong.

AND ITS TWIN, SINCE SLICE 21: A DECISION NOBODY MADE IS NOT "NONE"
------------------------------------------------------------------
A setting written `null` is NOT DECIDED. It stays declared (`has_setting`), but it is kept out
of `settings` - the dict the runner hands the evaluator - and listed in `undecided`. A predicate
reading it therefore answers UNKNOWN through the evaluator's existing "this property has not
supplied X" branch, naming the parameter, with no evaluator change. `[]` still means "decided:
none", which is a real answer a hotel can give. `spec/parameters.py` says why the two must
differ: in an exception, `[]` exempts nobody, so a missing answer would become an accusation.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..kernel import Clock, PropertyClock
from .errors import SpecError
from .parameters import ParameterSchema
from .registry import SPEC_DIR

_CURRENCY = re.compile(r"[A-Z]{3}")


@dataclass(frozen=True, slots=True)
class TenantConfig:
    """One property's configuration. Immutable once loaded."""

    tenant_id: str
    provider: str
    timezone: str
    name: str = ""
    call_budget: int = 101
    status_map: dict[str, str] = field(default_factory=dict)
    department_map: dict[str, str] = field(default_factory=dict)
    known_unmapped_statuses: tuple[str, ...] = ()
    # DECIDED values only - see "its twin" in the module docstring.
    settings: dict[str, Any] = field(default_factory=dict)
    # Declared as `null`: not decided. Never a value, never "none".
    undecided: tuple[str, ...] = ()
    # The currencies this property's money is in, as its evidence shows them. A Money parameter
    # in any other currency is refused at load, never converted (R9).
    currencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Validate the timezone AT LOAD rather than at first use. A typo here shifts every
        # population window by a few hours, and a run that quietly evaluated the wrong day is
        # worse than a run that refused to start.
        try:
            PropertyClock(self.timezone)
        except ValueError as exc:
            raise SpecError("tenant %r: %s" % (self.tenant_id, exc)) from None
        if self.call_budget < 1:
            raise SpecError(
                "tenant %r: a run needs at least one call to fetch its population"
                % (self.tenant_id,))
        # Freeze the mutable containers so a caller cannot teach a running engine a new status
        # code halfway through a run and change what a control applied to.
        object.__setattr__(self, "status_map", dict(self.status_map))
        object.__setattr__(self, "department_map", dict(self.department_map))
        object.__setattr__(self, "known_unmapped_statuses", tuple(self.known_unmapped_statuses))

        # Split "not decided" out of the values HERE, not only in `load`, so that no way of
        # building a tenant - a test, a tool, a future caller - can hand the evaluator a None
        # and have a predicate read it as an empty answer.
        nulls = {name for name, value in self.settings.items() if value is None}
        clash = set(self.undecided) & (set(self.settings) - nulls)
        if clash:
            raise SpecError("tenant %r: %s cannot be both decided and not decided"
                            % (self.tenant_id, ", ".join(sorted(clash))))
        object.__setattr__(self, "settings", {name: value for name, value
                                              in self.settings.items() if value is not None})
        object.__setattr__(self, "undecided", tuple(sorted(set(self.undecided) | nulls)))
        object.__setattr__(self, "currencies", _currency_codes(self.tenant_id, self.currencies))

        overlap = set(self.status_map) & set(self.known_unmapped_statuses)
        if overlap:
            # Declaring a code both mapped and deliberately-unmapped is a contradiction, and
            # whichever one wins would be an accident.
            raise SpecError(
                "tenant %r: %s appear in both status_map and known_unmapped_statuses"
                % (self.tenant_id, ", ".join(sorted(overlap))))

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, tenant_id: str, spec_dir: pathlib.Path | str = SPEC_DIR) -> TenantConfig:
        """One property, its settings TYPED against `spec/parameters.json` (slice 21).

        Every engine path reaches a tenant through here - the web app and `validate_spec` both
        do - so a wrong type, unit or currency is refused before any control runs.
        """
        path = pathlib.Path(spec_dir) / "tenants" / ("%s.json" % tenant_id)
        if not path.is_file():
            raise SpecError("no tenant configuration called %r in %s"
                            % (tenant_id, path.parent))
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")),
                             parameters=ParameterSchema.load(spec_dir))

    @classmethod
    def from_dict(cls, raw: dict[str, Any],
                  parameters: ParameterSchema | None = None) -> TenantConfig:
        """Build a tenant from its file's contents, typing its settings if given a schema.

        Untyped without one, which is what unit tests that build a tenant by hand rely on -
        and `null` is still "not decided" either way, because `__post_init__` enforces that.
        """
        try:
            tenant_id = raw["tenant_id"]
            settings = raw.get("settings", {})
            currencies = _currency_codes(tenant_id, raw.get("currencies", ()))
            if parameters is not None:
                settings = parameters.typed(settings, tenant_id=tenant_id,
                                            currencies=currencies)
            return cls(
                tenant_id=tenant_id,
                provider=raw["provider"],
                timezone=raw["timezone"],
                name=raw.get("name", ""),
                call_budget=raw.get("call_budget", 101),
                status_map=raw.get("status_map", {}),
                department_map=raw.get("department_map", {}),
                known_unmapped_statuses=tuple(raw.get("known_unmapped_statuses", ())),
                settings=settings,
                currencies=currencies,
            )
        except KeyError as exc:
            raise SpecError("tenant configuration is missing %s" % exc) from None

    # ------------------------------------------------------------------ vocabulary
    def status(self, code: str) -> str | None:
        """This property's spelling of a reservation status, as a canonical status.

        `None` means "we have not been told what this code means", and the caller turns that
        into UNKNOWN. It is deliberately not an exception: an unrecognised status is a fact
        about the hotel's data, not a broken specification.
        """
        return self.status_map.get((code or "").strip())

    def department(self, code: str) -> str | None:
        """This property's folio posting category. `None` until the hotel supplies a map."""
        return self.department_map.get((code or "").strip())

    def setting(self, name: str) -> Any:
        """A value the hotel supplies and the PMS cannot.

        Raises for an undeclared name rather than returning an empty default. An IR naming a
        setting nobody defined would otherwise evaluate against `[]` and silently exclude
        every record - a control reporting nothing to see, because it was misconfigured.

        Raises for an UNDECIDED one too, rather than returning None: a caller handed None
        can read it as empty, which is the exact confusion slice 21 removes.
        """
        if name in self.undecided:
            raise SpecError(
                "tenant %r: %r is not decided (null in its configuration). A control reading "
                "it answers UNKNOWN naming it; nothing may read it as empty"
                % (self.tenant_id, name))
        try:
            return self.settings[name]
        except KeyError:
            raise SpecError(
                "tenant %r declares no setting %r. A control referencing it cannot be "
                "evaluated - add it to the tenant configuration, as null if the hotel has not "
                "decided yet" % (self.tenant_id, name)) from None

    def has_setting(self, name: str) -> bool:
        """Declared - decided or not. Whether a control may NAME it, not whether it has a value."""
        return name in self.settings or name in self.undecided

    def is_decided(self, name: str) -> bool:
        """Has the hotel given an answer, even "none"? `[]` is decided; `null` is not."""
        return name in self.settings

    # ------------------------------------------------------------------ time
    def clock(self, instant=None) -> Clock:
        """This property's clock. Every relative date in a population query resolves through it.

        At 22:30 UTC on 7 July it is already 8 July in Jerusalem, so "who checked out today"
        has a different answer depending on which clock is asked - and the hotel's is the only
        one whose answer is correct (F11).
        """
        return PropertyClock(self.timezone, instant=instant)


def _currency_codes(tenant_id: str, codes: Any) -> tuple[str, ...]:
    """The property's currencies as sorted three-letter codes, or a refusal naming the bad one.

    Checked before any Money parameter is read against them, so a misspelt `usd` is reported as
    itself rather than as every fee being "in a currency the property does not use".
    """
    if isinstance(codes, str) or not isinstance(codes, (list, tuple)):
        raise SpecError("tenant %r: currencies must be a list of codes like [\"USD\"], not %r"
                        % (tenant_id, codes))
    for code in codes:
        if not isinstance(code, str) or not _CURRENCY.fullmatch(code):
            raise SpecError("tenant %r: currency %r is not a three-letter code like 'USD'"
                            % (tenant_id, code))
    return tuple(sorted(set(codes)))


def available(spec_dir: pathlib.Path | str = SPEC_DIR) -> tuple[str, ...]:
    """Every property this deployment knows about: whatever is in spec/tenants/, in id order.

    The index IS the directory listing, exactly as it is for controls. A page offering a hand-
    written list of properties would be a page that forgets the one somebody added yesterday.
    """
    return tuple(sorted(p.stem for p in (pathlib.Path(spec_dir) / "tenants").glob("*.json")))
