# -*- coding: utf-8 -*-
"""
TEMPLATE - a guest-service decision table, approved by the owner, loaded and checked.

    load_template("LATE_CHECKOUT", spec_dir) -> Template     spec/guest/late_checkout.json

`spec/` is data the engine reads at runtime, and the decision table is where hotel policy turns
into behaviour - which is why plan-v3 §5 made it a file the owner approved BEFORE any code. This
module is the line between the two, and it refuses rather than guesses:

  - a table whose `status` is not `approved` is not read. A draft decides nothing;
  - a table whose rules - ids, order or decisions - differ from `decision.RULES` is refused,
    naming the first difference. The file says what the owner approved and the code says what
    runs; if they disagree, nobody can say which one a decision followed;
  - its parameters are read by slice 21's `ParameterSchema.from_dict`, so a `default`, an
    unknown type or a misspelt key is refused exactly as it is for a tenant setting - and every
    one must be `required`, because an optional parameter is a default by another name.

EDITING THE TABLE MAKES A NEW VERSION
-------------------------------------
Every stored decision names the template's `version` and the `digest` of its decision-bearing
content, the slice 16 pairing. The lock for controls (`spec/ir.lock.json`) is outside this
slice's reach, so the digest is pinned to the version in `tests/unit/test_guest_template.py`:
edit a rule without the bump and the suite fails. Prose (`note`, `why`, `description`) is not
hashed - rewording an explanation decides nothing, and a check that demands a version for a
typo is a check people learn to override.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any

from ..spec import ParameterSchema, SpecError
from ..spec.registry import SPEC_DIR
from .decision import DECISIONS, DENIED, EVIDENCE_FIELDS, PARAMETERS, RULES, UNAVAILABLE

APPROVED_STATUS = "approved"
DECISION_BEARING = ("template", "evidence", "parameters", "parameter_order", "rules", "fee",
                    "identity", "actions")
PROSE = frozenset({"note", "why", "description"})
SEVERITIES = frozenset({"high", "medium", "low"})


@dataclass(frozen=True, eq=False)
class Template:
    """One approved guest-service template."""

    raw: dict[str, Any] = field(repr=False)
    template_id: str
    name: str
    version: int
    digest: str
    schema: ParameterSchema = field(repr=False)
    order: tuple[tuple[str, str], ...]
    population: dict[str, Any] = field(repr=False)
    # Decision -> {"severity", "audience"}, or None for a decision that raises no task.
    actions: dict[str, Any] = field(repr=False)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Template:
        name = raw.get("template", "this template")
        if raw.get("status") != APPROVED_STATUS:
            raise SpecError(
                "the %s decision table is not approved (status: %r). A table decides nothing "
                "until the owner approves it (plan-v3 §5)" % (name, raw.get("status")))
        for position, (expected, found) in enumerate(
                zip_longest(RULES, [(r.get("rule"), r.get("decision"))
                                    for r in raw.get("rules", ())]), start=1):
            if expected != found:
                raise SpecError(
                    "the %s decision table and the engine disagree at rule %d: the engine "
                    "implements %s and the file says %s. Change both, in one reviewed edit, "
                    "with a new version" % (name, position, _rule(expected), _rule(found)))

        schema = ParameterSchema.from_dict(raw)
        if tuple(schema.parameters) != PARAMETERS:
            raise SpecError("the %s table must declare exactly %s, in that order; it declares %s"
                            % (name, ", ".join(PARAMETERS), ", ".join(schema.parameters)))
        optional = [p.name for p in schema.parameters.values() if not p.required]
        if optional:
            raise SpecError("the %s table declares %s optional. Every parameter is required - "
                            "stated, as null if undecided - because an optional parameter is a "
                            "default by another name (D15)" % (name, ", ".join(optional)))

        evidence = raw.get("evidence", {})
        if tuple(evidence.get("fields", ())) != EVIDENCE_FIELDS:
            raise SpecError("the %s table must read exactly %s" % (name,
                                                                  ", ".join(EVIDENCE_FIELDS)))
        population = evidence.get("population")
        if not isinstance(population, dict) or "provider_query" not in population \
                or "window" not in population:
            raise SpecError("the %s table declares no population to look a reservation up in"
                            % name)

        order = tuple(tuple(pair) for pair in raw.get("parameter_order", {}).get("rules", ()))
        for pair in order:
            if len(pair) != 2 or not set(pair) <= set(PARAMETERS):
                raise SpecError("the %s table orders %r, which is not two of its parameters"
                                % (name, list(pair)))

        actions = raw.get("actions", {})
        expected = set(DECISIONS) - {UNAVAILABLE}
        stated = set(actions) - PROSE
        if stated != expected:
            raise SpecError("the %s table must say, for each of %s, which task it raises (null "
                            "for none); it covers %s" % (name, ", ".join(sorted(expected)),
                                                         ", ".join(sorted(stated))))
        if actions[DENIED] is not None:
            raise SpecError("the %s table raises a task for DENIED; the owner decided a denial "
                            "raises none" % name)
        for decision in expected - {DENIED}:
            action = actions[decision]
            if not isinstance(action, dict) or action.get("severity") not in SEVERITIES:
                raise SpecError("the %s table's %s task needs a severity: high, medium or low"
                                % (name, decision))

        return cls(raw=raw, template_id=name, name=raw.get("name", name),
                   version=int(raw["version"]), digest=template_digest(raw), schema=schema,
                   order=order, population=population,
                   actions={d: actions[d] for d in expected})


def _rule(pair) -> str:
    return "nothing" if pair is None else "%s -> %s" % pair


def template_digest(raw: dict[str, Any]) -> str:
    """The table's decision-bearing content as a self-describing SHA-256 - canonical JSON, so
    key order and indentation are not the table; prose dropped at every depth."""
    content = {key: _without_prose(raw[key]) for key in DECISION_BEARING if key in raw}
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without_prose(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_prose(v) for k, v in value.items() if k not in PROSE}
    if isinstance(value, list):
        return [_without_prose(item) for item in value]
    return value


def load_template(template_id: str = "LATE_CHECKOUT",
                  spec_dir: pathlib.Path | str = SPEC_DIR) -> Template:
    """One template, from `spec/guest/<template_id lowercased>.json`, checked."""
    path = pathlib.Path(spec_dir) / "guest" / ("%s.json" % template_id.lower())
    if not path.is_file():
        raise SpecError("no guest-service template called %r in %s"
                        % (template_id, path.parent))
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("template") != template_id:
        raise SpecError("%s names itself %r, not %r" % (path.name, raw.get("template"),
                                                        template_id))
    return Template.from_dict(raw)
