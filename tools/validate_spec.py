# -*- coding: utf-8 -*-
"""
Validate everything in spec/ - the vocabulary, the rules, the provider maps, the tenants.

    python3 -m tools.validate_spec

Run after ANY change under spec/. It is not ceremony: v1's equivalent had already caught two
claims that were wrong about the data, and this one caught four rules whose joins read a field
they never declared, on its first real run.

It is also the gate that makes a natural-language compiler safe to add later
(control_rule_architecture.docx section 17). Whatever writes an IR - a person or a model - goes
through exactly these checks, and a rule referencing vocabulary nobody defined is rejected
NAMING the missing fields rather than running and quietly answering about nothing.

Exit code 0 means every check passed. Anything else means fix the spec, not the engine.
"""
from __future__ import annotations

import json
import pathlib
import sys

from hotelcontrols.spec import (Problem, Registry, TenantConfig, available, load, load_schema,
                                validate)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"


class Checker:
    """Runs the checks and counts them, so a green says how much was actually verified."""

    def __init__(self) -> None:
        self.checks = 0
        self.problems: list[Problem] = []

    def check(self, condition: bool, where: str, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.problems.append(Problem(where, message))
        return condition

    def extend(self, problems: list[Problem], count: int) -> None:
        self.checks += count
        self.problems.extend(problems)


def main() -> int:
    checker = Checker()
    registry = Registry.load(SPEC)
    ir_schema = load_schema(SPEC)

    tenants = _load_tenants(checker)
    providers = _check_providers(checker, registry)
    _check_registry(checker, registry, providers)
    _check_controls(checker, registry, ir_schema, tenants)

    return _report(checker, registry, providers, tenants)


# --------------------------------------------------------------------------- sections
def _load_tenants(checker: Checker) -> dict[str, TenantConfig]:
    tenants: dict[str, TenantConfig] = {}
    for path in sorted((SPEC / "tenants").glob("*.json")):
        try:
            tenant = TenantConfig.load(path.stem, SPEC)
        except Exception as exc:                       # a bad tenant file is a spec error
            checker.check(False, "tenant %s" % path.stem, str(exc))
            continue
        tenants[tenant.tenant_id] = tenant
        checker.check(tenant.tenant_id == path.stem, "tenant %s" % path.stem,
                      "tenant_id %r does not match its filename" % tenant.tenant_id)
        # A status code declared both mapped and deliberately-unmapped is a contradiction;
        # TenantConfig refuses it at load, so reaching here means it is consistent.
        checker.check(bool(tenant.timezone), "tenant %s" % path.stem,
                      "a property must declare its timezone (F11)")
    return tenants


def _check_providers(checker: Checker, registry: Registry) -> dict[str, dict]:
    providers: dict[str, dict] = {}
    for path in sorted((SPEC / "providers").glob("*.json")):
        provider = json.loads(path.read_text(encoding="utf-8"))
        providers[provider["provider"]] = provider
        where = "provider %s" % provider["provider"]

        seen: set[str] = set()
        for mapping in provider["mappings"]:
            canonical = mapping["canonical"]
            checker.check(registry.has(canonical), where,
                          "maps %r, which is not a declared canonical field" % canonical)
            checker.check(canonical not in seen, where,
                          "maps %r twice - two sources for one field is a coin toss"
                          % canonical)
            seen.add(canonical)
            for required in ("endpoint", "path", "probe"):
                checker.check(required in mapping, where,
                              "mapping for %r has no %r" % (canonical, required))
    return providers


def _check_registry(checker: Checker, registry: Registry, providers: dict[str, dict]) -> None:
    mapped: set[str] = set()
    for provider in providers.values():
        mapped.update(m["canonical"] for m in provider["mappings"])

    for spec in registry:
        where = "field %s" % spec.field
        checker.check("." in spec.field, where, "field names must be entity-qualified")
        checker.check(bool(spec.description), where,
                      "every field needs a description - this is the vocabulary a rule author "
                      "reads")
        # A field that is neither mapped nor declared unresolvable is a gap nobody decided
        # about: a control using it returns UNKNOWN for a reason no document explains.
        checker.check(spec.field in mapped or not spec.resolvable, where,
                      "is neither mapped by any provider nor marked resolvable: false")
        if not spec.resolvable:
            checker.check(spec.risk is not None, where,
                          "an unresolvable field must cite the risk that explains why")


def _check_controls(checker: Checker, registry: Registry, ir_schema: dict,
                    tenants: dict[str, TenantConfig]) -> None:
    for control_id in available(SPEC):
        ir = load(control_id, SPEC)
        checker.check(ir.control_id == control_id, "control %s" % control_id,
                      "control_id %r does not match its filename" % ir.control_id)

        for tenant in tenants.values() or [None]:
            found = validate(ir, registry, tenant=tenant, ir_schema=ir_schema)
            # Roughly one check per field referenced plus one per predicate - enough for the
            # count to mean something without pretending to a precision it does not have.
            checker.extend(found, len(ir.referenced_fields()) + len(list(ir.predicates())) + 6)


# --------------------------------------------------------------------------- reporting
def _report(checker: Checker, registry: Registry, providers: dict[str, dict],
            tenants: dict[str, TenantConfig]) -> int:
    if checker.problems:
        print("FAILED - %d of %d checks\n" % (len(checker.problems), checker.checks))
        for problem in checker.problems:
            print("   x %s" % problem)
        return 1

    print("PASSED - all %d checks\n" % checker.checks)
    print("  %d canonical fields across %d entities"
          % (len(registry), len(registry.entities)))
    print("  %d controls, all schema-valid, no dangling field references"
          % len(available(SPEC)))
    print("  %d provider map(s): %s" % (len(providers), ", ".join(sorted(providers))))
    print("  %d tenant(s): %s" % (len(tenants), ", ".join(sorted(tenants))))

    # Not a failure. These are what drives the UNKNOWN state and the readiness report - the
    # "connect this to enable the control" path rather than a wrong verdict.
    gaps = registry.unresolvable()
    if gaps:
        print("\n  Evidence gaps (these drive UNKNOWN, they are not validation failures):")
        for spec in gaps:
            print("    - %s (%s)" % (spec.field, spec.risk or "no risk id"))

    empty = [t.tenant_id for t in tenants.values()
             if not any(t.settings.get(k) for k in t.settings)]
    if empty:
        print("\n  Tenants with no settings supplied yet: %s" % ", ".join(empty))
        print("    Controls needing them answer UNKNOWN or exclude every record, honestly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
