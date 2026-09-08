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
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from ..kernel import Clock, PropertyClock
from .errors import SpecError
from .registry import SPEC_DIR


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
    settings: dict[str, Any] = field(default_factory=dict)

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
        object.__setattr__(self, "settings", dict(self.settings))
        object.__setattr__(self, "known_unmapped_statuses", tuple(self.known_unmapped_statuses))

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
        path = pathlib.Path(spec_dir) / "tenants" / ("%s.json" % tenant_id)
        if not path.is_file():
            raise SpecError("no tenant configuration called %r in %s"
                            % (tenant_id, path.parent))
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TenantConfig:
        try:
            return cls(
                tenant_id=raw["tenant_id"],
                provider=raw["provider"],
                timezone=raw["timezone"],
                name=raw.get("name", ""),
                call_budget=raw.get("call_budget", 101),
                status_map=raw.get("status_map", {}),
                department_map=raw.get("department_map", {}),
                known_unmapped_statuses=tuple(raw.get("known_unmapped_statuses", ())),
                settings=raw.get("settings", {}),
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
        """
        try:
            return self.settings[name]
        except KeyError:
            raise SpecError(
                "tenant %r declares no setting %r. A control referencing it cannot be "
                "evaluated - add it to the tenant configuration, with an empty value if the "
                "hotel has not decided yet" % (self.tenant_id, name)) from None

    def has_setting(self, name: str) -> bool:
        return name in self.settings

    # ------------------------------------------------------------------ time
    def clock(self, instant=None) -> Clock:
        """This property's clock. Every relative date in a population query resolves through it.

        At 22:30 UTC on 7 July it is already 8 July in Jerusalem, so "who checked out today"
        has a different answer depending on which clock is asked - and the hotel's is the only
        one whose answer is correct (F11).
        """
        return PropertyClock(self.timezone, instant=instant)
