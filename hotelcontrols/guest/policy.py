# -*- coding: utf-8 -*-
"""
POLICY - one hotel's late-checkout policy, typed, with "not decided" kept as such.

    load_policy(template, tenant, spec_dir)                -> Policy
    policy_from_block(template, block, tenant_id=, currencies=) -> Policy

The six parameters are D15's, declared by the approved template in slice 21's vocabulary, and
TYPED BY SLICE 21'S OWN SCHEMA - `ParameterSchema.from_dict(template)` - so a time, an amount
with its currency and a choice mean here exactly what they mean for a control. Slice 22 may not
change `spec/parameters.json` or `hotelcontrols/spec/`, and does not need to.

Where they live: a `guest_services.LATE_CHECKOUT` block in the tenant file. `TenantConfig`
ignores keys it does not know, so the block is read here, from the same file, and the property's
own `currencies` (slice 21) decide which fee currencies it may state.

THREE RULES, ALL INHERITED
--------------------------
  1. `null` is NOT DECIDED. It stays None here - never "no fee", never "no maximum" - and every
     undecided parameter is a gap the decision names (LC1, V10).
  2. NO DEFAULTS. Every parameter is required to be STATED, as null if undecided, so "nobody
     wrote this down" is visible in the file. A missing one is refused at load.
  3. A wrong type, unit or currency is refused BY NAME, at load - a bare `25` is not money (R9).

And one this slice adds, from D2 §31 ("Validator checks: time ordering"): the four times must be
in order, checked when the policy loads, naming the two that disagree. Only DECIDED times are
compared - an undecided one is already a gap, and comparing it would be reading null as a time.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from datetime import time
from typing import Any

from ..kernel import Money
from ..spec import SpecError, TenantConfig
from ..spec.registry import SPEC_DIR
from .decision import PARAMETERS, Gap


@dataclass(frozen=True, slots=True)
class Policy:
    """Every parameter the template declares, typed - or None, which means not decided."""

    tenant_id: str
    values: dict[str, Any]

    def __post_init__(self) -> None:
        if set(self.values) != set(PARAMETERS):
            # Exactly the six. A policy missing one would leave the decision to read a KeyError
            # as an answer; one with a seventh would be a parameter nothing reads.
            raise ValueError("a late-checkout policy states exactly %s; this one states %s"
                             % (", ".join(PARAMETERS), ", ".join(sorted(self.values))))
        object.__setattr__(self, "values", dict(self.values))

    def __getitem__(self, name: str) -> Any:
        return self.values[name]

    @property
    def undecided(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.values.items() if value is None)

    def gaps(self) -> tuple[Gap, ...]:
        return tuple(Gap(name, "parameter",
                         "is not decided by this property (null in its configuration)")
                     for name in self.undecided)

    @property
    def digest(self) -> str:
        """The six values as they decide, hashed - part of a decision's identity, so the same
        request under a changed policy is a new decision rather than the old one replayed."""
        plain = {name: _plain(value) for name, value in sorted(self.values.items())}
        text = json.dumps(plain, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, Money):
        return {"amount": str(value.amount), "currency": value.currency}
    return value


def policy_from_block(template, block: Any, *, tenant_id: str,
                      currencies: tuple[str, ...] | list[str]) -> Policy:
    """Type one tenant's block against the template's declared parameters (slice 21's reader),
    then check the time ordering. Raises SpecError naming every problem."""
    typed = template.schema.typed(block, tenant_id=tenant_id, currencies=tuple(currencies))
    values = {name: typed.get(name) for name in template.schema.parameters}
    problems = []
    for earlier, later in template.order:
        first, second = values.get(earlier), values.get(later)
        if first is None or second is None:
            continue
        if first > second:
            problems.append(
                "tenant %r: %s (%s) is later than %s (%s); the late-checkout times must be in "
                "order (D2 §31)" % (tenant_id, earlier, _plain(first), later, _plain(second)))
    if problems:
        raise SpecError("; ".join(problems))
    return Policy(tenant_id=tenant_id, values=values)


def load_policy(template, tenant: TenantConfig,
                spec_dir: pathlib.Path | str = SPEC_DIR) -> Policy:
    """This property's policy for `template`, from its tenant file.

    A property that states no block at all is REFUSED rather than read as all-undecided. The
    two must not look alike (slice 21's rule): "this hotel has not decided" is a null it wrote
    down; a missing block is a property nobody configured for guest services.
    """
    path = pathlib.Path(spec_dir) / "tenants" / ("%s.json" % tenant.tenant_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    services = raw.get("guest_services")
    block = services.get(template.template_id) if isinstance(services, dict) else None
    if not isinstance(block, dict):
        raise SpecError(
            "tenant %r states no guest_services.%s block, so it has no late-checkout policy to "
            "apply. State each parameter there, as null if the hotel has not decided it"
            % (tenant.tenant_id, template.template_id))
    return policy_from_block(template, block, tenant_id=tenant.tenant_id,
                             currencies=tenant.currencies)
