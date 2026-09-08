# -*- coding: utf-8 -*-
"""
CONTROL IR - a rule, loaded and checked before anything tries to run it.

The IR is the pivot of the whole design: it is what a sentence compiles TO and what the engine
executes FROM, and it names no PMS. `control_rule_architecture.docx` section 17 is explicit
about why the intermediate step exists at all -

    Don't go: LLM -> executable JSON directly. That's risky.
    Use: Natural Language -> Control IR -> Validation -> Evidence Requirements
         -> Provider Mapping -> Executable Rule

- and this module is the Validation stage. It is the reason a compiler can be added in slice 9
without being dangerous: whatever writes an IR, a human or a model, it passes through exactly
these checks, and one that references vocabulary nobody defined is rejected NAMING the missing
fields rather than producing a rule that runs and quietly answers about nothing.

Six checks, beyond the schema itself. Each exists because skipping it lets a specific class of
broken rule through:

  1. Every field referenced anywhere is a declared canonical field.
  2. Everything used in references, scope, exceptions or the assertion is also declared as
     required evidence - so a rule cannot depend on data nobody planned to fetch.
  3. `group_by` is present exactly when the assertion is an aggregate, and absent otherwise.
  4. A predicate has exactly one right-hand side: a literal, another field, or a tenant
     setting. Two would mean the engine picks one, and the rule would be ambiguous.
  5. Interval operators carry an interval; aggregate operators appear only in aggregates.
  6. A reference carries the fields its kind needs, and any field it joins on is declared.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Iterator

from . import schema as jsonschema
from .errors import Problem, SpecError
from .registry import SPEC_DIR, Registry
from .tenant import TenantConfig

# Operators that compare a record against an interval of dates, and therefore need one.
INTERVAL_OPERATORS = frozenset({"within", "not_within", "no_overlap"})
# Operators that ask a question about a GROUP of records, and are meaningless on one record.
AGGREGATE_OPERATORS = frozenset({"count_lte", "no_overlap"})
# Operators that ask whether a declared reference resolved for this record.
REFERENCE_OPERATORS = frozenset({"reference_exists", "reference_missing"})
# Operators that need no right-hand side at all.
UNARY_OPERATORS = frozenset({"exists", "not_exists"}) | REFERENCE_OPERATORS

RIGHT_HAND_SIDES = ("value", "compare_to", "tenant_setting")


class ControlIR:
    """One control, validated on load.

    Backed by the raw dictionary rather than exploded into attributes, deliberately: the
    schema is the contract, `spec/` is data the engine reads at runtime, and a hand-written
    mirror of every field is a second place for the two to disagree.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    # ------------------------------------------------------------------ accessors
    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    @property
    def control_id(self) -> str:
        return self._raw["control_id"]

    @property
    def name(self) -> str:
        return self._raw["name"]

    @property
    def entity(self) -> str:
        return self._raw["entity"]

    @property
    def natural_language(self) -> str:
        return self._raw["natural_language"]

    @property
    def is_aggregate(self) -> bool:
        return self._raw["assertion"]["mode"] == "aggregate"

    @property
    def references(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._raw.get("references", ()))

    @property
    def evidence_fields(self) -> tuple[str, ...]:
        return tuple(e["field"] for e in self._raw["required_evidence"])

    def predicates(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """Every predicate in the rule, with the clause it came from."""
        for clause in ("scope", "exceptions"):
            for predicate in self._raw.get(clause, ()):
                yield clause, predicate
        for predicate in self._raw["assertion"]["predicates"]:
            yield "assertion", predicate

    def referenced_fields(self) -> frozenset[str]:
        """Every canonical field this rule mentions anywhere.

        Check 2 rests on this: whatever a rule reads, it must have declared it needs.
        """
        names: set[str] = set()
        for _, predicate in self.predicates():
            names.add(predicate["field"])
            if "compare_to" in predicate:
                names.add(predicate["compare_to"])
            interval = predicate.get("interval")
            if interval:
                names.update((interval["start"], interval["end"]))
        if self.is_aggregate:
            # `.get`, because this runs BEFORE the check that reports a missing group_by. An
            # aggregate without one is a real defect, but it should be reported by name rather
            # than as a KeyError from the vocabulary check that happens to run first.
            group_by = self._raw["assertion"].get("group_by")
            if group_by:
                names.add(group_by)
        for reference in self.references:
            names.update(x for x in (reference.get("local_field"),
                                     reference.get("remote_field"),
                                     reference.get("field")) if x)
        return frozenset(names)

    def __repr__(self) -> str:
        return "ControlIR(%s)" % self.control_id


# --------------------------------------------------------------------------- loading
def available(spec_dir: pathlib.Path | str = SPEC_DIR) -> tuple[str, ...]:
    """Every control the engine can run: whatever is in spec/ir/, in id order.

    The index IS the directory listing. That is what makes success criterion 6 - a twelfth
    control is a spec change, not a code change - true rather than claimed.
    """
    directory = pathlib.Path(spec_dir) / "ir"
    return tuple(sorted(p.stem for p in directory.glob("*.json")))


def load(control_id: str, spec_dir: pathlib.Path | str = SPEC_DIR) -> ControlIR:
    """Load one control by id.

    The id is checked against the directory listing rather than pasted into a path: this value
    arrives from a URL, and `../../etc/passwd` is a perfectly good control id as far as string
    formatting is concerned.
    """
    spec_dir = pathlib.Path(spec_dir)
    if control_id not in available(spec_dir):
        raise SpecError("no control %r in %s" % (control_id, spec_dir / "ir"))
    raw = json.loads((spec_dir / "ir" / ("%s.json" % control_id)).read_text(encoding="utf-8"))
    return ControlIR(raw)


def load_schema(spec_dir: pathlib.Path | str = SPEC_DIR) -> dict[str, Any]:
    return json.loads((pathlib.Path(spec_dir) / "ir_schema.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- validation
def validate(ir: ControlIR | dict[str, Any], registry: Registry,
             tenant: TenantConfig | None = None,
             ir_schema: dict[str, Any] | None = None,
             spec_dir: pathlib.Path | str = SPEC_DIR) -> list[Problem]:
    """Every way this IR is wrong, as a list. Empty means it is safe to run.

    Returns rather than raises, because the caller is often showing the list to whoever wrote
    the rule - a compiler's proposal, rejected with the missing vocabulary named, is far more
    useful than a stack trace about the first problem found.
    """
    raw = ir.raw if isinstance(ir, ControlIR) else ir
    control = ir if isinstance(ir, ControlIR) else ControlIR(raw)
    where = raw.get("control_id", "<unnamed control>")

    problems = jsonschema.validate(
        raw, ir_schema if ir_schema is not None else load_schema(spec_dir))
    for problem in problems:
        problem.where = "%s %s" % (where, problem.where)
    if problems:
        # Everything below assumes the shape the schema guarantees. Reporting "group_by is
        # missing" about a document that is not even an object is noise.
        return problems

    problems.extend(_check_vocabulary(control, registry, where))
    problems.extend(_check_evidence_declared(control, where))
    problems.extend(_check_assertion_shape(control, where))
    problems.extend(_check_predicates(control, where))
    problems.extend(_check_references(control, registry, where))
    if tenant is not None:
        problems.extend(_check_tenant_settings(control, tenant, where))
    return problems


def _check_vocabulary(ir: ControlIR, registry: Registry, where: str) -> list[Problem]:
    """Check 1 - every field named anywhere is declared vocabulary.

    This is the gate section 17 asks for. Fed the requirements doc's own example sentence,
    "All VIP arrivals should have an assigned room that is clean by 2 PM", it answers with
    `reservation.vip` and `room.housekeeping_status_at` by name - which is the difference
    between a rule that is rejected and a rule that runs and answers about nothing.
    """
    return [Problem(where, "references undeclared canonical field %r" % name)
            for name in sorted(ir.referenced_fields()) if not registry.has(name)]


def _check_evidence_declared(ir: ControlIR, where: str) -> list[Problem]:
    """Check 2 - whatever the rule reads, it declared it needs.

    Without this, a rule can depend on a field the evidence layer was never asked to fetch,
    and the failure appears at runtime as an UNKNOWN that looks like a hotel's data gap.
    """
    declared = set(ir.evidence_fields)
    return [Problem(where, "uses %r but does not declare it in required_evidence" % name)
            for name in sorted(ir.referenced_fields() - declared)]


def _check_assertion_shape(ir: ControlIR, where: str) -> list[Problem]:
    """Check 3 - group_by is present exactly when the assertion is an aggregate.

    v1 shipped two aggregate assertions with no grouping key at all, which is why duplicate
    detection could never be evaluated: the rule did not say what a duplicate was OF (F2).
    """
    assertion = ir["assertion"]
    problems: list[Problem] = []
    if ir.is_aggregate and "group_by" not in assertion:
        problems.append(Problem(
            where, "an aggregate assertion must declare group_by - a count is meaningless "
                   "until the rule says what the records are grouped by"))
    if not ir.is_aggregate and "group_by" in assertion:
        problems.append(Problem(
            where, "group_by is only meaningful for an aggregate assertion, not for mode %r"
                   % assertion["mode"]))
    return problems


def _check_predicates(ir: ControlIR, where: str) -> list[Problem]:
    """Checks 4 and 5 - one right-hand side, and operators used where they mean something."""
    problems: list[Problem] = []
    for clause, predicate in ir.predicates():
        operator = predicate["operator"]
        site = "%s predicate on %s" % (clause, predicate["field"])
        sides = [key for key in RIGHT_HAND_SIDES if key in predicate]

        # Three shapes of right-hand side, and each operator has exactly one of them.
        if operator in UNARY_OPERATORS:
            # `exists`, `not_exists`, `reference_exists`, `reference_missing` ask about the
            # left side alone.
            if sides:
                problems.append(Problem(
                    where, "%s: %r takes no value, but %s is given"
                           % (site, operator, " and ".join(sides))))
        elif operator in INTERVAL_OPERATORS:
            # An interval operator's right-hand side IS its interval - the two fields that
            # bound the window. A literal alongside it would be a second, contradictory
            # right-hand side, and the engine would have to pick one.
            if sides:
                problems.append(Problem(
                    where, "%s: %r is bounded by its interval and takes no %s"
                           % (site, operator, " or ".join(sides))))
        elif len(sides) != 1:
            problems.append(Problem(
                where, "%s: %r needs exactly one of value, compare_to or tenant_setting, "
                       "got %d" % (site, operator, len(sides))))

        if operator in INTERVAL_OPERATORS and "interval" not in predicate:
            problems.append(Problem(
                where, "%s: %r needs an interval naming the two fields that bound it"
                       % (site, operator)))
        if "interval" in predicate and operator not in INTERVAL_OPERATORS:
            problems.append(Problem(
                where, "%s: %r does not use an interval" % (site, operator)))

        if operator in AGGREGATE_OPERATORS and clause != "assertion":
            problems.append(Problem(
                where, "%s: %r asks a question about a group of records and cannot appear in "
                       "%s" % (site, operator, clause)))
        if operator in AGGREGATE_OPERATORS and not ir.is_aggregate:
            problems.append(Problem(
                where, "%s: %r requires assertion mode 'aggregate', not %r"
                       % (site, operator, ir["assertion"]["mode"])))
        if ir.is_aggregate and clause == "assertion" and operator not in AGGREGATE_OPERATORS:
            problems.append(Problem(
                where, "%s: an aggregate assertion's predicates must be aggregate operators, "
                       "and %r is not" % (site, operator)))
    return problems


def _check_references(ir: ControlIR, registry: Registry, where: str) -> list[Problem]:
    """Check 6 - a reference carries what its kind needs.

    A lookup or collection without both sides of its join would silently match nothing, and
    every record would come back UNKNOWN for a reason that named the data rather than the bug.
    """
    problems: list[Problem] = []
    declared_entities: set[str] = set()
    for reference in ir.references:
        kind, entity = reference["kind"], reference["entity"]
        site = "%s reference on %s" % (kind, entity)
        if entity in declared_entities:
            problems.append(Problem(
                where, "%s: %r is referenced twice, so a field of that entity would have two "
                       "possible sources" % (site, entity)))
        declared_entities.add(entity)

        if kind in ("lookup", "collection"):
            missing = [k for k in ("local_field", "remote_field") if k not in reference]
            if missing:
                problems.append(Problem(
                    where, "%s: needs %s to know what joins to what"
                           % (site, " and ".join(missing))))
            if "field" in reference:
                problems.append(Problem(where, "%s: `field` is for a set reference" % site))
            remote = reference.get("remote_field")
            if remote and registry.has(remote) and remote.split(".")[0] != entity:
                problems.append(Problem(
                    where, "%s: remote_field %r does not belong to entity %r"
                           % (site, remote, entity)))
        else:                                                                   # kind == set
            if "field" not in reference:
                problems.append(Problem(
                    where, "%s: needs `field`, naming the values that form the set" % site))
            for key in ("local_field", "remote_field"):
                if key in reference:
                    problems.append(Problem(
                        where, "%s: %s is for a lookup or collection" % (site, key)))
    return problems


def _check_tenant_settings(ir: ControlIR, tenant: TenantConfig, where: str) -> list[Problem]:
    """A rule naming a setting the hotel has not declared cannot be evaluated.

    Without this the setting resolves to an empty default, the scope predicate matches nothing,
    and the control reports a clean run over zero records - which is finding F5 arriving by a
    different route.
    """
    problems: list[Problem] = []
    for _, predicate in ir.predicates():
        name = predicate.get("tenant_setting")
        if name and not tenant.has_setting(name):
            problems.append(Problem(
                where, "names tenant setting %r, which tenant %r does not declare"
                       % (name, tenant.tenant_id)))
    for reference in ir.references:
        if reference.get("source") == "tenant":
            # A tenant-sourced reference needs the hotel to have supplied the mapping. An
            # empty one is legitimate - it means the control answers UNKNOWN, which is the
            # "connect this to enable the control" path rather than a spec error.
            continue
    return problems
